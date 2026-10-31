# CORE: reusable — sign in / sign out. Telegram sign-in is added with the bot step.
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

import audit.models as audit
from accounts.middleware import EPOCH_KEY, SESSION_KEY
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
            request.session[EPOCH_KEY] = user.session_epoch
            from django.utils import timezone
            UserAccount.objects.filter(pk=user.pk).update(last_login_at=timezone.now())
            audit.write(user.username, "kirish", "user_account", user.pk)
            if user.must_change_password:
                return redirect("/parol/")
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
            me.must_change_password = False
            me.session_epoch += 1                      # other devices sign out; this one stays
            me.save(update_fields=["password_hash", "must_change_password", "session_epoch"])
            request.session[EPOCH_KEY] = me.session_epoch
            audit.write(me.username, "parol_ozgardi", "user_account", me.pk)
            messages.success(request, "Parol o'zgardi.")
            return redirect("/")
    return render(request, "accounts/password.html")


# ---- People page (bosh only) -------------------------------------------------------------------
from django.http import Http404  # noqa: E402

from accounts import people as ppl  # noqa: E402
from accounts.middleware import login_required  # noqa: E402
from config import values as cfg  # noqa: E402


def _people_ctx(extra=None):
    ctx = {"people_all": UserAccount.objects.order_by("-is_active", "created_at"),
           "roles": [(k, cfg.ROLE_LABELS.get(k, k)) for k in cfg.ROLES]}
    ctx.update(extra or {})
    return ctx


@login_required
@require_http_methods(["GET", "POST"])
def people_page(request):
    me = request.account
    if not me.sees_all:
        raise Http404
    if request.method == "POST":
        try:
            u, pw = ppl.add_person(me, request.POST.get("username"), request.POST.get("name"), request.POST.get("role"))
            return render(request, "accounts/people.html", _people_ctx({"shown": u, "shown_pw": pw, "shown_new": True}))
        except ppl.NotAllowed as e:
            messages.error(request, str(e))
    return render(request, "accounts/people.html", _people_ctx())


@login_required
@require_POST
def person_action(request, username: str, action: str):
    me = request.account
    if not me.sees_all:
        raise Http404
    target = UserAccount.objects.filter(username=username).first()
    if target is None:
        raise Http404
    try:
        if action == "parol":
            pw = ppl.reset_password(me, target)
            return render(request, "accounts/people.html", _people_ctx({"shown": target, "shown_pw": pw}))
        if action == "blok":
            ppl.set_active(me, target, False)
            messages.success(request, f"{target.name} bloklandi.")
        elif action == "faol":
            ppl.set_active(me, target, True)
            messages.success(request, f"{target.name} qayta faol.")
        elif action == "tahrir":
            ppl.edit_person(me, target, request.POST.get("name"), request.POST.get("role"))
            messages.success(request, "Saqlandi.")
        elif action == "telegram":
            ppl.unlink_telegram(me, target)
            messages.success(request, f"{target.name}ning Telegrami uzildi.")
        else:
            raise Http404
    except ppl.NotAllowed as e:
        messages.error(request, str(e))
    return redirect("/odamlar/")
