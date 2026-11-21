"""Public marketing pages (the landing page at the site root)."""

from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
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


PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.manaze.app"
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content")


def get_app(request):
    """One link for ads and sharing (/get/): Android phones go to the Play Store, everyone else (iPhone,
    desktop) to the landing page, where they can sign up on the website."""
    utm = {key: request.GET[key] for key in UTM_KEYS if request.GET.get(key)}
    if "android" in request.META.get("HTTP_USER_AGENT", "").lower():
        url = PLAY_STORE_URL
        if utm:
            # Play passes this on to the install referrer, so installs can be traced back to the ad.
            url += "&" + urlencode({"referrer": urlencode(utm)})
        return HttpResponseRedirect(url)
    return HttpResponseRedirect("/" + ("?" + urlencode(utm) if utm else ""))
