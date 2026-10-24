"""
Payment providers for Vyntra subscriptions.

- Razorpay Subscriptions on the website (UPI AutoPay, cards, net banking).
- Google Play Billing in the Android app (Google requires it for in-app digital subscriptions).

Both only report what was paid; SubscriptionService decides what that means for access.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import BusinessAdmin, Subscription, SubscriptionPlan
from .subscriptions import SubscriptionService, add_months

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """The payment provider refused a request or couldn't be reached."""


def _from_unix(seconds):
    return datetime.fromtimestamp(int(seconds), tz=dt_timezone.utc) if seconds else None


def _from_rfc3339(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _call(request, timeout=15):
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        logger.warning("%s %s failed: %s %s", request.get_method(), request.full_url, error.code, detail)
        raise ProviderError(detail) from error
    except urllib.error.URLError as error:
        raise ProviderError(str(error)) from error


# ==============================================================================================
# Razorpay
# ==============================================================================================


class Razorpay:
    API = "https://api.razorpay.com/v1"
    # Razorpay needs a fixed number of billing cycles; these cover ten years of renewals.
    YEARS_OF_RENEWALS = 10

    @classmethod
    def is_configured(cls):
        return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)

    @classmethod
    def _request(cls, method, path, body=None):
        credentials = f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()
        request = urllib.request.Request(
            f"{cls.API}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": f"Basic {base64.b64encode(credentials).decode()}",
                "Content-Type": "application/json",
            },
        )
        return _call(request)

    @classmethod
    def create_plan(cls, plan):
        """Creates the matching Razorpay plan (yearly plans bill every year, others every N months)."""
        period, interval = ("yearly", plan.months // 12) if plan.months % 12 == 0 else ("monthly", plan.months)
        created = cls._request("POST", "/plans", {
            "period": period,
            "interval": interval,
            "item": {
                "name": f"Vyntra {plan.name}",
                "amount": int(plan.price * 100),
                "currency": plan.currency,
            },
            "notes": {"code": plan.code},
        })
        return created["id"]

    @classmethod
    def create_subscription(cls, plan, admin):
        cycles = max(1, cls.YEARS_OF_RENEWALS * 12 // plan.months)
        return cls._request("POST", "/subscriptions", {
            "plan_id": plan.razorpay_plan_id,
            "total_count": cycles,
            "customer_notify": 1,
            "notes": {"business_admin_id": str(admin.id), "plan_code": plan.code},
        })

    @classmethod
    def fetch_subscription(cls, subscription_id):
        return cls._request("GET", f"/subscriptions/{urllib.parse.quote(subscription_id)}")

    @classmethod
    def fetch_payment(cls, payment_id):
        return cls._request("GET", f"/payments/{urllib.parse.quote(payment_id)}")

    @classmethod
    def cancel_subscription(cls, subscription_id):
        """Stops future charges right away; the days already paid for stay usable on our side."""
        return cls._request("POST", f"/subscriptions/{urllib.parse.quote(subscription_id)}/cancel",
                            {"cancel_at_cycle_end": 0})

    @staticmethod
    def _signature_matches(message, signature, secret):
        expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    @classmethod
    def checkout_signature_matches(cls, payment_id, subscription_id, signature):
        message = f"{payment_id}|{subscription_id}".encode()
        return cls._signature_matches(message, signature, settings.RAZORPAY_KEY_SECRET)

    @classmethod
    def webhook_signature_matches(cls, body, signature):
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        return bool(secret) and cls._signature_matches(body, signature, secret)


class RazorpayBilling:
    """Turns Razorpay subscription and payment entities into Vyntra subscription changes."""

    @classmethod
    def start_checkout(cls, admin, plan):
        if not Razorpay.is_configured() or not plan.razorpay_plan_id:
            raise ValidationError({"detail": "Online payment isn't set up yet. Please try again later."})
        subscription = SubscriptionService.for_admin(admin)
        if not SubscriptionService.can_purchase(subscription):
            raise ValidationError({"detail": "Your plan is already active and renews automatically."})
        try:
            created = Razorpay.create_subscription(plan, admin)
        except ProviderError:
            raise ValidationError({"detail": "Couldn't start the payment. Please try again."})
        return {
            "key_id": settings.RAZORPAY_KEY_ID,
            "subscription_id": created["id"],
            # Razorpay's hosted payment page for this subscription; the Android app opens it in a browser.
            "payment_url": created.get("short_url", ""),
            "plan": plan,
            "name": admin.name,
            "email": admin.email,
            "contact": admin.phone or "",
        }

    @classmethod
    def confirm_checkout(cls, admin, payment_id, subscription_id, signature):
        """Called by the website right after checkout succeeds, so access unlocks without waiting."""
        if not Razorpay.checkout_signature_matches(payment_id, subscription_id, signature):
            raise ValidationError({"detail": "Payment could not be verified."})
        try:
            entity = Razorpay.fetch_subscription(subscription_id)
            payment = Razorpay.fetch_payment(payment_id)
        except ProviderError:
            raise ValidationError({"detail": "Payment received, but we couldn't confirm it yet. "
                                             "It will show up in a few minutes."})
        if entity.get("notes", {}).get("business_admin_id") != str(admin.id):
            raise ValidationError({"detail": "This payment belongs to another account."})
        return cls.apply(entity, payment)

    @classmethod
    def handle_webhook(cls, event):
        payload = event.get("payload", {})
        entity = payload.get("subscription", {}).get("entity")
        if not entity:
            return
        payment = payload.get("payment", {}).get("entity")
        name = event.get("event", "")
        if name in ("subscription.activated", "subscription.charged", "subscription.resumed"):
            cls.apply(entity, payment)
        elif name in ("subscription.cancelled", "subscription.completed", "subscription.halted"):
            cls.stop(entity, expired=name == "subscription.halted")

    @classmethod
    def _owner(cls, entity):
        admin_id = entity.get("notes", {}).get("business_admin_id")
        return BusinessAdmin.objects.filter(id=admin_id).first() if admin_id else None

    @classmethod
    def apply(cls, entity, payment=None):
        """A Razorpay subscription is paid up to `current_end`."""
        admin = cls._owner(entity)
        # A price change links the plan to a new Razorpay plan, but existing subscribers keep renewing on the old
        # one; the plan code saved on the subscription still finds them.
        plan = (
            SubscriptionPlan.objects.filter(razorpay_plan_id=entity.get("plan_id")).first()
            or SubscriptionPlan.objects.filter(code=entity.get("notes", {}).get("plan_code") or None).first()
        )
        if admin is None or plan is None:
            logger.warning("Razorpay subscription %s has no matching login or plan", entity.get("id"))
            return None

        start = _from_unix(entity.get("current_start")) or timezone.now()
        end = _from_unix(entity.get("current_end")) or add_months(start, plan.months)
        renewing = entity.get("status") in ("active", "authenticated", "pending")
        subscription = SubscriptionService.start_period(
            admin, Subscription.RAZORPAY, plan, start, end, renewing, entity["id"]
        )
        if payment and payment.get("status") in ("captured", "authorized"):
            SubscriptionService.record_payment(
                subscription, Subscription.RAZORPAY, payment["id"],
                Decimal(payment["amount"]) / 100, plan=plan, currency=payment.get("currency", "INR"),
                period_start=start, period_end=end, paid_at=_from_unix(payment.get("created_at")), raw=payment,
            )
        return subscription

    @classmethod
    def stop(cls, entity, expired):
        admin = cls._owner(entity)
        if admin is None:
            return
        subscription = SubscriptionService.for_admin(admin)
        # Events from an older Razorpay subscription mustn't touch a newer plan.
        if subscription.provider == Subscription.RAZORPAY and subscription.provider_subscription_id == entity["id"]:
            SubscriptionService.stop_renewal(subscription, expired=expired)

    @classmethod
    def cancel(cls, subscription):
        try:
            Razorpay.cancel_subscription(subscription.provider_subscription_id)
        except ProviderError:
            raise ValidationError({"detail": "Couldn't cancel right now. Please try again."})
        SubscriptionService.stop_renewal(subscription)


# ==============================================================================================
# Google Play
# ==============================================================================================


class GooglePlay:
    API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
    SCOPE = "https://www.googleapis.com/auth/androidpublisher"
    _token = {"value": None, "expires": 0}

    @classmethod
    def is_configured(cls):
        return bool(settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON)

    @classmethod
    def _access_token(cls):
        """OAuth token for the service account linked in Play Console, cached until shortly before expiry."""
        if cls._token["value"] and cls._token["expires"] > time.time() + 60:
            return cls._token["value"]
        account = json.loads(settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON)
        now = int(time.time())
        assertion = jwt.encode(
            {"iss": account["client_email"], "scope": cls.SCOPE, "aud": account["token_uri"],
             "iat": now, "exp": now + 3600},
            account["private_key"],
            algorithm="RS256",
        )
        request = urllib.request.Request(
            account["token_uri"],
            data=urllib.parse.urlencode({
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            }).encode(),
            method="POST",
        )
        token = _call(request)
        cls._token = {"value": token["access_token"], "expires": now + int(token.get("expires_in", 3600))}
        return cls._token["value"]

    @classmethod
    def _request(cls, method, path):
        request = urllib.request.Request(
            f"{cls.API}/{settings.GOOGLE_PLAY_PACKAGE_NAME}{path}",
            data=b"{}" if method == "POST" else None,
            method=method,
            headers={"Authorization": f"Bearer {cls._access_token()}", "Content-Type": "application/json"},
        )
        return _call(request)

    @classmethod
    def fetch_subscription(cls, purchase_token):
        return cls._request("GET", f"/purchases/subscriptionsv2/tokens/{urllib.parse.quote(purchase_token)}")

    @classmethod
    def acknowledge(cls, product_id, purchase_token):
        cls._request(
            "POST",
            f"/purchases/subscriptions/{urllib.parse.quote(product_id)}/tokens/"
            f"{urllib.parse.quote(purchase_token)}:acknowledge",
        )


class GooglePlayBilling:
    """Turns Google Play subscription purchases into Vyntra subscription changes."""

    ACTIVE_STATES = ("SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD")
    ENDED_STATES = ("SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_PAUSED", "SUBSCRIPTION_STATE_EXPIRED")

    @classmethod
    def confirm_purchase(cls, admin, purchase_token):
        """Called by the app right after a purchase in Google Play."""
        if not GooglePlay.is_configured():
            raise ValidationError({"detail": "Google Play payments aren't set up yet."})
        try:
            purchase = GooglePlay.fetch_subscription(purchase_token)
        except ProviderError:
            raise ValidationError({"detail": "Couldn't confirm the purchase with Google Play. Please try again."})
        account_id = purchase.get("externalAccountIdentifiers", {}).get("obfuscatedExternalAccountId")
        if account_id and account_id != str(admin.id):
            raise ValidationError({"detail": "This purchase belongs to another account."})
        return cls.apply(admin, purchase_token, purchase)

    @classmethod
    def handle_notification(cls, message):
        """A Real-time developer notification (via Pub/Sub): re-read the purchase and sync it."""
        data = json.loads(base64.b64decode(message.get("data", "")) or b"{}")
        notification = data.get("subscriptionNotification")
        if not notification:
            return
        token = notification["purchaseToken"]
        purchase = GooglePlay.fetch_subscription(token)
        account_id = purchase.get("externalAccountIdentifiers", {}).get("obfuscatedExternalAccountId")
        admin = BusinessAdmin.objects.filter(id=account_id).first() if account_id else None
        if admin is None:
            admin = BusinessAdmin.objects.filter(
                subscription__provider=Subscription.GOOGLE_PLAY, subscription__provider_subscription_id=token
            ).first()
        if admin is None:
            logger.warning("Google Play notification for an unknown purchase")
            return
        cls.apply(admin, token, purchase)

    @classmethod
    def apply(cls, admin, purchase_token, purchase):
        state = purchase.get("subscriptionState")
        item = (purchase.get("lineItems") or [{}])[0]
        base_plan_id = item.get("offerDetails", {}).get("basePlanId")
        plan = SubscriptionPlan.objects.filter(google_base_plan_id=base_plan_id).first()
        end = _from_rfc3339(item.get("expiryTime"))
        subscription = SubscriptionService.for_admin(admin)

        if state in cls.ENDED_STATES:
            if subscription.provider_subscription_id == purchase_token:
                SubscriptionService.stop_renewal(subscription, expired=True)
            return subscription
        if plan is None or end is None or state not in cls.ACTIVE_STATES + ("SUBSCRIPTION_STATE_CANCELED",):
            logger.warning("Google Play purchase in state %s for plan %s ignored", state, base_plan_id)
            return subscription

        renewing = item.get("autoRenewingPlan", {}).get("autoRenewEnabled", False)
        start = add_months(end, -plan.months)
        subscription = SubscriptionService.start_period(
            admin, Subscription.GOOGLE_PLAY, plan, start, end, renewing, purchase_token
        )

        order_id = purchase.get("latestOrderId")
        if order_id:
            price = item.get("autoRenewingPlan", {}).get("recurringPrice") or {}
            amount = (Decimal(price["units"]) + Decimal(price.get("nanos", 0)) / 10**9) if price.get("units") \
                else plan.price
            SubscriptionService.record_payment(
                subscription, Subscription.GOOGLE_PLAY, order_id, amount, plan=plan,
                currency=price.get("currencyCode", "INR"), period_start=start, period_end=end, raw=purchase,
            )

        # Google refunds purchases that aren't acknowledged within three days.
        if purchase.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING":
            try:
                GooglePlay.acknowledge(item.get("productId", settings.GOOGLE_PLAY_PRODUCT_ID), purchase_token)
            except ProviderError:
                logger.exception("Acknowledging Google Play purchase failed")
        return subscription
