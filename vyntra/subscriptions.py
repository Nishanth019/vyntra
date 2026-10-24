"""
Vyntra's own subscription: a 15-day free trial per login, then a paid plan.

A business account follows the subscription of its OWNER (the login that created it). While the owner
has access, every admin of that business can work normally; once it ends, the business is read-only.
"""

import calendar
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from .models import BusinessAccountAdmin, Subscription, SubscriptionPayment, SubscriptionPlan

TRIAL_DAYS = 15
# A failed renewal keeps access this long while the provider retries the charge.
GRACE_DAYS = 3
# Reminders go out this many days before access ends (0 = the day it ends).
REMINDER_DAYS = (3, 1, 0)

OWNER = "OWNER"


class SubscriptionRequired(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = "subscription_required"
    default_detail = "Your subscription has ended. Renew it to make changes."


def add_months(moment, months):
    """The same day and time `months` later, clamped to the month's last day (31 Jan + 1 → 28/29 Feb)."""
    month_index = moment.month - 1 + months
    year, month = moment.year + month_index // 12, month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


class SubscriptionService:
    # ---- Reading ------------------------------------------------------------------------------

    @classmethod
    def for_admin(cls, admin):
        """The login's subscription; logins from before subscriptions existed start their trial now."""
        subscription, _ = Subscription.objects.select_related("plan").get_or_create(
            business_admin=admin,
            defaults={"trial_ends_at": timezone.now() + timedelta(days=TRIAL_DAYS)},
        )
        return subscription

    @classmethod
    def access_until(cls, subscription):
        ends = [subscription.trial_ends_at]
        if subscription.current_period_end:
            grace = timedelta(days=GRACE_DAYS if subscription.auto_renew else 0)
            ends.append(subscription.current_period_end + grace)
        return max(ends)

    @classmethod
    def has_access(cls, subscription):
        return timezone.now() < cls.access_until(subscription)

    @classmethod
    def state(cls, subscription):
        """
        TRIAL      free trial running, nothing paid
        ACTIVE     paid and renewing
        CANCELLED  paid, won't renew; works until the period ends
        GRACE      renewal failed; works for a few more days while it is retried
        EXPIRED    read-only
        """
        now = timezone.now()
        end = subscription.current_period_end
        if end and now < end:
            return "ACTIVE" if subscription.auto_renew else "CANCELLED"
        if now < subscription.trial_ends_at:
            return "TRIAL"
        if cls.has_access(subscription):
            return "GRACE"
        return "EXPIRED"

    @classmethod
    def can_purchase(cls, subscription):
        """A new plan can be bought unless one is already paid and renewing."""
        return cls.state(subscription) != "ACTIVE"

    @classmethod
    def summary(cls, admin):
        subscription = cls.for_admin(admin)
        until = cls.access_until(subscription)
        days_left = (timezone.localdate(until) - timezone.localdate()).days
        return {
            "state": cls.state(subscription),
            "has_access": cls.has_access(subscription),
            "can_purchase": cls.can_purchase(subscription),
            "trial_ends_at": subscription.trial_ends_at,
            "current_period_end": subscription.current_period_end,
            "access_until": until,
            "days_left": max(days_left, 0),
            "auto_renew": subscription.auto_renew,
            "provider": subscription.provider,
            "plan": subscription.plan,
            "owns_business": cls.owned_account_ids(admin).exists(),
        }

    # ---- Owners and the read-only rule --------------------------------------------------------

    @classmethod
    def owned_account_ids(cls, admin):
        return BusinessAccountAdmin.objects.filter(
            business_admin=admin, role=OWNER, is_active=True, business_account__is_active=True
        ).values_list("business_account_id", flat=True)

    @classmethod
    def owner_of(cls, business_account_id):
        """The OWNER login, else (for older data) the earliest active admin of the business."""
        links = BusinessAccountAdmin.objects.select_related("business_admin").filter(
            business_account_id=business_account_id, is_active=True, business_admin__is_active=True
        )
        link = links.filter(role=OWNER).first() or links.order_by("id").first()
        return link.business_admin if link else None

    @classmethod
    def business_access(cls, business_account_id, admin):
        """What the app needs to show a business as editable or read-only."""
        owner = cls.owner_of(business_account_id)
        read_only = owner is not None and not cls.has_access(cls.for_admin(owner))
        return {
            "is_owner": owner is not None and owner.id == admin.id,
            "owner_name": owner.name if owner else None,
            "read_only": read_only,
        }

    @classmethod
    def check_write_access(cls, business_account_id, admin):
        """Raise 402 when the business's owner has no trial or plan left."""
        access = cls.business_access(business_account_id, admin)
        if not access["read_only"]:
            return
        if access["is_owner"]:
            raise SubscriptionRequired("Your subscription has ended. Renew it to make changes.")
        raise SubscriptionRequired(
            f"{access['owner_name']}'s subscription has ended, so this business is read-only. "
            "Ask them to renew it."
        )

    @classmethod
    def check_can_create_business(cls, admin):
        if not cls.has_access(cls.for_admin(admin)):
            raise SubscriptionRequired("Your subscription has ended. Renew it to add a business.")

    # ---- Changes from payments ----------------------------------------------------------------

    @classmethod
    @transaction.atomic
    def start_period(cls, admin, provider, plan, period_start, period_end, auto_renew, provider_subscription_id):
        """A paid period begins (first payment, renewal, or a switch to another provider or plan)."""
        subscription = Subscription.objects.select_for_update().get(pk=cls.for_admin(admin).pk)
        subscription.plan = plan
        subscription.status = Subscription.ACTIVE if auto_renew else Subscription.CANCELLED
        subscription.current_period_start = period_start
        subscription.current_period_end = period_end
        subscription.auto_renew = auto_renew
        subscription.provider = provider
        subscription.provider_subscription_id = provider_subscription_id
        subscription.cancelled_at = None if auto_renew else subscription.cancelled_at or timezone.now()
        subscription.save()
        return subscription

    @classmethod
    def renewal_start(cls, subscription):
        """When a plan bought now should start: after the paid days left (so none are lost), otherwise now."""
        if cls.state(subscription) == "CANCELLED":
            return subscription.current_period_end
        return None

    @classmethod
    def schedule_renewal(cls, admin, provider, plan, provider_subscription_id):
        """A new plan takes over when the paid period ends; it is first charged then."""
        subscription = Subscription.objects.select_for_update().get(pk=cls.for_admin(admin).pk)
        subscription.plan = plan
        subscription.status = Subscription.ACTIVE
        subscription.auto_renew = True
        subscription.provider = provider
        subscription.provider_subscription_id = provider_subscription_id
        subscription.cancelled_at = None
        subscription.save()
        return subscription

    @classmethod
    def stop_renewal(cls, subscription, expired=False):
        """The plan won't renew (cancelled, or the provider gave up charging). Paid days are kept."""
        subscription.auto_renew = False
        subscription.status = Subscription.EXPIRED if expired else Subscription.CANCELLED
        subscription.cancelled_at = subscription.cancelled_at or timezone.now()
        subscription.save()

    @classmethod
    def extend(cls, subscription, days):
        """Free days given from Django admin, added on top of whatever access is left."""
        start = max(cls.access_until(subscription), timezone.now())
        subscription.current_period_start = subscription.current_period_start or timezone.now()
        subscription.current_period_end = start + timedelta(days=days)
        if subscription.provider is None:
            subscription.provider = Subscription.MANUAL
        if not subscription.auto_renew:
            subscription.status = Subscription.CANCELLED
        subscription.save()

    @classmethod
    def record_payment(cls, subscription, provider, provider_payment_id, amount, plan=None, currency="INR",
                       period_start=None, period_end=None, paid_at=None, raw=None):
        """Saves a charge once; the same payment reported again (e.g. by a webhook) is ignored."""
        payment, _ = SubscriptionPayment.objects.get_or_create(
            provider=provider,
            provider_payment_id=provider_payment_id,
            defaults={
                "subscription": subscription,
                "plan": plan,
                "amount": amount,
                "currency": currency,
                "period_start": period_start,
                "period_end": period_end,
                "paid_at": paid_at or timezone.now(),
                "raw_response": raw,
            },
        )
        return payment

    # ---- Reminders ----------------------------------------------------------------------------

    @classmethod
    def reminders(cls, today):
        """(owner, title, message) for every business owner whose trial or plan ends in 3, 1 or 0 days."""
        owner_ids = BusinessAccountAdmin.objects.filter(
            role=OWNER, is_active=True, business_account__is_active=True
        ).values_list("business_admin_id", flat=True)
        subscriptions = Subscription.objects.select_related("business_admin").filter(
            business_admin_id__in=owner_ids, business_admin__is_active=True, auto_renew=False
        )
        for subscription in subscriptions:
            days_left = (timezone.localdate(cls.access_until(subscription)) - today).days
            if days_left not in REMINDER_DAYS:
                continue
            what = "free trial" if cls.state(subscription) == "TRIAL" else "subscription"
            if days_left == 0:
                title = f"Your {what} ends today"
                message = "Subscribe to keep adding members, payments and attendance. Your data stays safe."
            else:
                title = f"Your {what} ends in {days_left} day{'s' if days_left > 1 else ''}"
                message = "Choose a plan so your business keeps running without a break."
            yield subscription.business_admin, title, message


def active_plans():
    return SubscriptionPlan.objects.filter(is_active=True)


def hand_over_ownership(admin):
    """When an owner deletes their login, the next admin of each of their businesses becomes the owner."""
    owned = BusinessAccountAdmin.objects.filter(business_admin=admin, role=OWNER)
    for link in owned:
        successor = (
            BusinessAccountAdmin.objects.filter(
                business_account_id=link.business_account_id, is_active=True, business_admin__is_active=True
            )
            .exclude(business_admin=admin)
            .order_by("id")
            .first()
        )
        if successor:
            successor.role = OWNER
            successor.save()
    owned.update(role="ADMIN")
