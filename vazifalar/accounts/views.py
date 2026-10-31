# CORE: reusable — sign in / sign out. Telegram sign-in is added with the bot step.
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

import audit.models as audit
from accounts.middleware import SESSION_KEY
from accounts.models import UserAccount


@require_http_methods(["GET", "POST"])
def login_view(request):
    nxt = request.GET.get("next") or request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip().lower()
        user = UserAccount.objects.filter(username=username, is_active=True).first()
        if user and user.check_password(request.POST.get("password") or ""):
            request.session.cycle_key()
            request.session[SESSION_KEY] = str(user.pk)
            audit.write(user.username, "kirish", "user_account", user.pk)
            return redirect(nxt)
        messages.error(request, "Login yoki parol noto'g'ri.")
    return render(request, "accounts/login.html", {"next": nxt})


@require_POST
def logout_view(request):
    request.session.flush()
    return redirect("/kirish/")


MIN_PASSWORD = 8   # CORE: reusable


@require_http_methods(["GET", "POST"])
def password_view(request):
    from accounts.middleware import login_required  # noqa: F401 (decorator applied below)
    me = getattr(request, "account", None)
    if me is None:
        return redirect("/kirish/")
    if request.method == "POST":
        old, new, again = (request.POST.get(k) or "" for k in ("old", "new", "again"))
        if not me.check_password(old):
            messages.error(request, "Hozirgi parol noto'g'ri.")
        elif len(new) < MIN_PASSWORD:
            messages.error(request, f"Yangi parol kamida {MIN_PASSWORD} belgi bo'lsin.")
        elif new != again:
            messages.error(request, "Yangi parollar bir xil emas.")
        else:
            me.set_password(new)
            me.save(update_fields=["password_hash"])
            audit.write(me.username, "parol_ozgardi", "user_account", me.pk)
            messages.success(request, "Parol o'zgardi.")
            return redirect("/")
    return render(request, "accounts/password.html")
