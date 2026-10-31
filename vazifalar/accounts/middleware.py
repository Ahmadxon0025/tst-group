# CORE: reusable — session → UserAccount on every request; a page needs a signed-in, active person.
from functools import wraps

from django.shortcuts import redirect

SESSION_KEY = "user_account_id"


class UserMiddleware:  # CORE: reusable
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from accounts.models import UserAccount

        request.account = None
        uid = request.session.get(SESSION_KEY)
        if uid:
            request.account = UserAccount.objects.filter(pk=uid, is_active=True).first()
            if request.account is None:
                request.session.flush()
        return self.get_response(request)


def login_required(view):  # CORE: reusable
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if getattr(request, "account", None) is None:
            return redirect(f"/kirish/?next={request.path}")
        return view(request, *args, **kwargs)
    return wrapper


def user_context(request):  # CORE: reusable — templates see `me` and the sidebar counts
    from django.db.models import Count, Q

    from config import values as cfg
    from core import dates
    from vazifalar import services as sv

    me = getattr(request, "account", None)
    ctx = {"me": me, "product_title": cfg.PRODUCT_TITLE, "companies": cfg.COMPANIES}
    if me is None:
        return ctx
    today = dates.today()
    ctx["today_iso"] = today.isoformat()
    ctx["my_open"] = me.vazifalar.filter(status="yangi").count()
    vis = sv.visible_tasks(me).filter(status="yangi")
    counts = {r["assignee"]: r for r in vis.values("assignee").annotate(
        open_n=Count("id"), late_n=Count("id", filter=Q(due_date__lt=today)))}
    people = list(sv.assignable_people())
    for p in people:
        r = counts.get(p.pk, {})
        p.open_n, p.late_n = r.get("open_n", 0), r.get("late_n", 0)
    ctx["side_people"] = people
    ctx["side_kim"] = (request.GET.get("kim") or "all") if request.path == "/" else ""
    ctx["side_k"] = (request.GET.get("k") or "") if request.path in ("/", "/shtab/") else ""
    return ctx
