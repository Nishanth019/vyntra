"""
Printable receipts for Vyntra subscription payments.

The app and website open a receipt in a browser, which can't send the login token, so each receipt link carries a
signed token for that one payment instead.
"""

from django.core import signing
from django.http import Http404
from django.shortcuts import render

from .models import BusinessAccount, SubscriptionPayment
from .subscriptions import SubscriptionService

SALT = "vyntra.receipt"

# What Razorpay calls each method, as a customer would say it.
METHODS = {"upi": "UPI", "card": "Card", "netbanking": "Net banking", "emandate": "Bank mandate",
           "nach": "Bank mandate", "wallet": "Wallet"}


def receipt_token(payment):
    return signing.dumps(payment.pk, salt=SALT)


def receipt_number(payment):
    return f"VYN-{payment.paid_at:%Y}-{payment.pk:05d}"


def payment_method(payment):
    """How the customer paid, from what the provider reported (None when it isn't known)."""
    if payment.provider == "GOOGLE_PLAY":
        return "Google Play"
    method = (payment.raw_response or {}).get("method")
    return METHODS.get(method, method.title() if method else None)


def receipt_view(request, token):
    try:
        payment_id = signing.loads(token, salt=SALT)
    except signing.BadSignature:
        raise Http404
    payment = (
        SubscriptionPayment.objects.select_related("plan", "subscription__business_admin")
        .filter(pk=payment_id).first()
    )
    if payment is None:
        raise Http404
    customer = payment.subscription.business_admin
    businesses = BusinessAccount.objects.filter(id__in=SubscriptionService.owned_account_ids(customer)).order_by("name")
    return render(request, "vyntra/receipt.html", {
        "payment": payment,
        "number": receipt_number(payment),
        "method": payment_method(payment),
        "customer": customer,
        "businesses": businesses,
    })
