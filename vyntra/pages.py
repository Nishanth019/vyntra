"""Public marketing pages (the landing page at the site root)."""

from django.conf import settings
from django.shortcuts import render

from .subscriptions import active_plans


def landing(request):
    plans = list(active_plans())
    monthly = next((plan for plan in plans if plan.months == 1), None)
    cards = []
    for plan in plans:
        per_month = plan.price / plan.months
        saving = round((1 - per_month / monthly.price) * 100) if monthly and plan.months > 1 else 0
        cards.append({"plan": plan, "per_month": round(per_month), "saving": saving})
    best = cards[-1]["plan"].code if len(cards) > 1 else None
    return render(request, "vyntra/landing.html", {
        "plans": cards,
        "best": best,
        "app_url": settings.WEB_APP_URL,
        "whatsapp": settings.SUPPORT_WHATSAPP,
    })
