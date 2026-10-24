import calendar
import hashlib
import hmac
import json
import logging
import time
import urllib.request
from datetime import timedelta
from decimal import Decimal

import jwt
from django.conf import settings
from django.db.models import Count, DecimalField, Exists, F, OuterRef, Prefetch, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import SAFE_METHODS

from .models import (
    BusinessAccount,
    BusinessAdmin,
    BusinessAdminDevice,
    Member,
    MemberActivity,
    MemberAttendance,
    Membership,
    Notification,
    NotificationSetting,
    Payment,
)
from .subscriptions import SubscriptionService

logger = logging.getLogger(__name__)

_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Value(Decimal("0"), output_field=_MONEY)

# Expired members are moved to inactive this many days after their plan ends.
AUTO_INACTIVE_AFTER_DAYS = 7


def rupees(amount):
    """₹ with Indian digit grouping, e.g. ₹1,25,000 or ₹499.50."""
    amount = Decimal(amount).quantize(Decimal("0.01"))
    whole, paise = divmod(abs(amount), 1)
    digits = str(int(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        digits = f"{head},{tail}"
    sign = "-" if amount < 0 else ""
    return f"{sign}₹{digits}" + (f".{int(paise * 100):02d}" if paise else "")


def _current_membership_expr():
    """
    A member's current plan: the active one once it has started, else the latest one that has
    started (e.g. while a future plan waits), else their only plan when it hasn't started yet.
    """
    today = timezone.localdate()
    active = Membership.objects.filter(member_id=OuterRef("pk"), is_active=True)
    started = Membership.objects.filter(member_id=OuterRef("pk"), start_date__lte=today).order_by("-start_date", "-id")
    return Coalesce(
        Subquery(active.filter(start_date__lte=today).values("id")[:1]),
        Subquery(started.values("id")[:1]),
        Subquery(active.values("id")[:1]),
    )


def _member_due_expr():
    """Dues on the member's current plan: amount − discount − its active payments."""
    payable = Subquery(
        Membership.objects.filter(id=OuterRef("current_membership_id"))
        .annotate(net=F("amount") - F("discount"))
        .values("net")[:1],
        output_field=_MONEY,
    )
    paid = Subquery(
        Payment.objects.filter(membership_id=OuterRef("current_membership_id"), is_active=True)
        .values("membership_id")
        .annotate(s=Sum("amount"))
        .values("s")[:1],
        output_field=_MONEY,
    )
    return Coalesce(payable, _ZERO) - Coalesce(paid, _ZERO)


class BusinessAdminAuthService:
    ACCESS_TOKEN_MAX_AGE = 180 * 24 * 60 * 60  # seconds

    @staticmethod
    def password_stamp(business_admin):
        """Changes whenever the password changes, so tokens issued before a password change stop working."""
        return hmac.new(settings.SECRET_KEY.encode(), business_admin.password.encode(), hashlib.sha256).hexdigest()[:16]

    @classmethod
    def generate_access_token(cls, business_admin):
        current_time = time.time()
        token_exp = int(current_time) + int(cls.ACCESS_TOKEN_MAX_AGE)
        payload = {"admin_id": business_admin.id, "time": current_time, "exp": token_exp,
                   "pw": cls.password_stamp(business_admin)}

        token = jwt.encode(
            payload=payload,
            key=settings.BUSINESS_ADMIN_AUTH_JWT_CONFIG["KEY"],
            algorithm=settings.BUSINESS_ADMIN_AUTH_JWT_CONFIG["ALGORITHM"],
        )

        if isinstance(token, bytes):
            token = token.decode("utf-8")

        return token

    @classmethod
    def decode_access_token(cls, token):
        """Return the payload of a valid access token, else None."""
        try:
            return jwt.decode(
                token,
                key=settings.BUSINESS_ADMIN_AUTH_JWT_CONFIG["KEY"],
                algorithms=[settings.BUSINESS_ADMIN_AUTH_JWT_CONFIG["ALGORITHM"]],
            )
        except jwt.InvalidTokenError:
            return None


class BusinessAccountService:
    @classmethod
    def get_accounts_for_admin(cls, business_admin):
        """Active business accounts the admin is mapped to through business_account_admin (the tenant boundary)."""
        return BusinessAccount.objects.select_related("business_type").filter(
            is_active=True,
            account_admins__business_admin=business_admin,
            account_admins__is_active=True,
        )

    @classmethod
    def check_admin_access(cls, request, business_account_id, allow_read_only=False):
        """
        Raise 403 unless the logged-in admin has an active mapping to this business account, and 402 for
        changes (anything but GET) once the business owner's subscription has ended. `allow_read_only`
        lets harmless personal changes, like marking notifications read, through anyway.
        """
        if not cls.get_accounts_for_admin(request.user).filter(id=business_account_id).exists():
            raise PermissionDenied("You do not have access to this business account.")
        if request.method not in SAFE_METHODS and not allow_read_only:
            SubscriptionService.check_write_access(business_account_id, request.user)

    @classmethod
    def get_admins(cls, business_account_id):
        """Active admins with active access to the business."""
        return BusinessAdmin.objects.filter(
            is_active=True,
            account_admins__business_account_id=business_account_id,
            account_admins__is_active=True,
        )


class MemberService:
    """
    A member has one `is_active` membership: their latest (current, next, or last expired).
    Their *current* plan is the one that has started (see _current_membership_expr); a
    renewed-early next plan becomes current on its start date. Dues come from the current plan.
    """

    # Renew Early is offered in the last days of a running plan.
    RENEW_EARLY_DAYS = 7

    @classmethod
    def get_members(cls, business_account_id):
        """
        Members of the business, with their active membership (latest plan) prefetched as
        `active_memberships` and the plan running today as `running_memberships`, annotated with
        `is_live` (a plan covers today), `current_membership_id` and `total_due`.
        """
        today = timezone.localdate()
        active_payments = Payment.objects.filter(is_active=True).order_by("-payment_date")
        memberships = Membership.objects.select_related("membership_plan__duration_type").prefetch_related(
            Prefetch("payments", queryset=active_payments, to_attr="active_payments")
        )
        covering_today = Membership.objects.filter(
            member_id=OuterRef("pk"), start_date__lte=today, end_date__gte=today
        )
        return (
            Member.objects.filter(business_account_id=business_account_id)
            .select_related("gym_details")
            .prefetch_related(
                Prefetch("memberships", queryset=memberships.filter(is_active=True), to_attr="active_memberships"),
                Prefetch(
                    "memberships",
                    queryset=memberships.filter(start_date__lte=today, end_date__gte=today).order_by("-start_date"),
                    to_attr="running_memberships",
                ),
            )
            .annotate(is_live=Exists(covering_today), current_membership_id=_current_membership_expr())
            .annotate(total_due=_member_due_expr())
        )

    @classmethod
    def current_and_next(cls, member):
        """(current plan, future plan or None) for a member loaded by get_members."""
        active = member.active_memberships[0] if member.active_memberships else None
        running = member.running_memberships[0] if member.running_memberships else None
        if running and active and active.id != running.id and active.start_date > running.end_date:
            return running, active
        if active and active.start_date <= timezone.localdate():
            return active, None
        return running or active, None

    @classmethod
    def filter_members(cls, members, params):
        """Applies the member list filters (shared by the list and the dashboard counts)."""
        today = timezone.localdate()
        if params.get("is_active") is not None:
            members = members.filter(is_active=params["is_active"])

        status = params.get("status")
        if status == "live":
            members = members.filter(is_active=True, is_live=True)
        elif status == "expired":
            members = members.filter(
                is_active=True, is_live=False, memberships__is_active=True, memberships__end_date__lt=today
            )

        # One filter() call so both dates apply to the same (active) membership.
        end_date_filters = {}
        if params.get("end_date_from"):
            end_date_filters["memberships__end_date__gte"] = params["end_date_from"]
        if params.get("end_date_to"):
            end_date_filters["memberships__end_date__lte"] = params["end_date_to"]
        if end_date_filters:
            members = members.filter(memberships__is_active=True, **end_date_filters)

        if params.get("has_dues") is not None:
            members = members.filter(total_due__gt=0) if params["has_dues"] else members.filter(total_due__lte=0)
        return members

    @classmethod
    def get_counts(cls, business_account_id):
        """Member counts for the dashboard tiles and member list chips, in one place."""
        today = timezone.localdate()
        members = cls.get_members(business_account_id)
        filters = {
            "all": {},
            "live": {"status": "live"},
            "expired": {"status": "expired"},
            "expiring3": {"is_active": True, "end_date_from": today, "end_date_to": today + timedelta(days=3)},
            "expiring7": {
                "is_active": True,
                "end_date_from": today + timedelta(days=4),
                "end_date_to": today + timedelta(days=7),
            },
            "expiring15": {
                "is_active": True,
                "end_date_from": today + timedelta(days=8),
                "end_date_to": today + timedelta(days=15),
            },
            "dues": {"has_dues": True},
            "inactive": {"is_active": False},
        }
        return {key: cls.filter_members(members, params).count() for key, params in filters.items()}

    @classmethod
    def get_memberships(cls, business_account_id, member_id):
        """All memberships (active + past) of a member, newest first, with plan and payments."""
        active_payments = Payment.objects.filter(is_active=True).order_by("-payment_date")
        return (
            Membership.objects.filter(business_account_id=business_account_id, member_id=member_id)
            .select_related("membership_plan__duration_type")
            .prefetch_related(Prefetch("payments", queryset=active_payments, to_attr="active_payments"))
            .order_by("-start_date", "-id")
        )

    @classmethod
    def calculate_end_date(cls, start_date, plan):
        """Last valid day of a plan starting on start_date, e.g. 1 MONTH from Jan 10 ends Feb 9."""
        value = plan.duration_value
        code = plan.duration_type.code

        if code == "DAY":
            return start_date + timedelta(days=value - 1)

        months = value * 12 if code == "YEAR" else value
        year, month = divmod(start_date.month - 1 + months, 12)
        year, month = start_date.year + year, month + 1
        day = min(start_date.day, calendar.monthrange(year, month)[1])
        return start_date.replace(year=year, month=month, day=day) - timedelta(days=1)


class ActivityService:
    @classmethod
    def log(cls, member, activity_type, description, admin=None, membership=None, payment=None):
        MemberActivity.objects.create(
            business_account_id=member.business_account_id,
            member=member,
            membership=membership,
            payment=payment,
            activity_type=activity_type,
            description=description,
            created_by_business_admin=admin,
        )


class MembershipService:
    @classmethod
    def describe(cls, membership):
        """e.g. "Quarterly (1 Nov 2026 – 31 Jan 2027), ₹3,000 − ₹500 discount"."""
        text = (
            f"{membership.membership_plan.name} ({membership.start_date:%d %b %Y} – "
            f"{membership.end_date:%d %b %Y}), {rupees(membership.amount)}"
        )
        if membership.discount:
            text += f" − {rupees(membership.discount)} discount"
        return text

    @classmethod
    def create(cls, member, plan, start_date, discount=Decimal("0"), active=True):
        """
        A new membership. Normally it becomes the active (latest) one and the previous one is history;
        `active=False` keeps a waiting future plan as the active one.
        """
        if active:
            Membership.objects.filter(member=member, is_active=True).update(is_active=False)
        return Membership.objects.create(
            business_account_id=member.business_account_id,
            member=member,
            membership_plan=plan,
            start_date=start_date,
            end_date=MemberService.calculate_end_date(start_date, plan),
            amount=plan.amount,
            discount=discount,
            is_active=active,
        )

    @classmethod
    def push_later_plans(cls, membership):
        """Moves any later plan of the member to start after `membership` ends, so plans never overlap."""
        # Only a waiting future plan (it's the active one) moves; closed plans are history.
        later = Membership.objects.filter(
            member_id=membership.member_id, is_active=True, start_date__gt=membership.start_date
        ).exclude(id=membership.id)
        for plan in later:
            if plan.start_date <= membership.end_date:
                shift = (membership.end_date + timedelta(days=1)) - plan.start_date
                plan.start_date += shift
                plan.end_date += shift
                plan.save()

    @classmethod
    def renew(cls, member, plan, start_date, discount, admin):
        """Rejoining: a new plan for an expired / inactive member (or one without a plan)."""
        membership = cls.create(member, plan, start_date, discount)
        ActivityService.log(
            member, "MEMBERSHIP_RENEWED", f"Renewed: {cls.describe(membership)}", admin, membership=membership
        )
        return membership

    @classmethod
    def renew_early(cls, member, current, plan, start_date, discount, admin):
        """Adds a future plan after the running one; it becomes current on `start_date`."""
        membership = cls.create(member, plan, start_date, discount)
        ActivityService.log(
            member,
            "MEMBERSHIP_RENEWED",
            f"Future plan added (after {current.membership_plan.name} ending {current.end_date:%d %b %Y}): "
            f"{cls.describe(membership)}",
            admin,
            membership=membership,
        )
        return membership

    @classmethod
    def discard(cls, membership, admin):
        """
        Removes a plan as if it never existed: its payments are deleted (they stop counting in
        collections and dues) and stay only as voided records; the timeline keeps the story.
        """
        for payment in Payment.objects.filter(membership=membership, is_active=True):
            PaymentService.void(payment, admin)
        Payment.objects.filter(membership=membership).update(membership=None)
        MemberActivity.objects.filter(membership=membership).update(membership=None)
        membership.delete()

    @classmethod
    def cancel_next(cls, member, current, next_plan, admin):
        """Removes a future plan; its payments are deleted with it (e.g. refunded). `current` is active again."""
        description = f"Future plan cancelled: {cls.describe(next_plan)}"
        cls.discard(next_plan, admin)
        current.is_active = True
        current.save()
        ActivityService.log(member, "PLAN_CHANGED", description, admin, membership=current)

    @classmethod
    def change_plan(cls, member, current, next_plan, plan, start_date, discount, admin):
        """
        Replaces the current plan with a brand-new one from `start_date`. The old plan is removed
        with its payments, so it no longer counts anywhere (collections, dues, plans sold, renewals).
        A future plan stays the active one and moves later if the new plan would overlap it.
        """
        old = cls.describe(current)
        paid = Payment.objects.filter(membership=current, is_active=True).aggregate(
            total=Coalesce(Sum("amount"), _ZERO)
        )["total"]
        cls.discard(current, admin)

        membership = cls.create(member, plan, start_date, discount, active=next_plan is None)
        cls.push_later_plans(membership)
        ActivityService.log(
            member,
            "PLAN_CHANGED",
            f"Plan changed to {cls.describe(membership)}. Previous plan removed: {old}"
            + (f", its {rupees(paid)} payments deleted" if paid else ""),
            admin,
            membership=membership,
        )
        return membership

    @classmethod
    def extend(cls, membership, days, admin, reason=""):
        old_end = membership.end_date
        membership.end_date = old_end + timedelta(days=days)
        membership.save()
        # A future plan moves out so the plans never overlap.
        cls.push_later_plans(membership)
        text = f"Extended by {days} day{'' if days == 1 else 's'}: {old_end:%d %b %Y} → {membership.end_date:%d %b %Y}"
        ActivityService.log(
            membership.member, "MEMBERSHIP_EXTENDED", text + (f" ({reason})" if reason else ""), admin,
            membership=membership,
        )
        return membership

    @classmethod
    def update(cls, membership, admin, start_date=None, discount=None):
        """Corrects the start date (end date follows the plan) and/or the discount."""
        changes = []
        if start_date is not None and start_date != membership.start_date:
            changes.append(f"start {membership.start_date:%d %b %Y} → {start_date:%d %b %Y}")
            membership.start_date = start_date
            membership.end_date = MemberService.calculate_end_date(start_date, membership.membership_plan)
        if discount is not None and discount != membership.discount:
            changes.append(f"discount {rupees(membership.discount)} → {rupees(discount)}")
            membership.discount = discount
        if changes:
            membership.save()
            cls.push_later_plans(membership)
            ActivityService.log(
                membership.member,
                "MEMBERSHIP_UPDATED",
                f"{membership.membership_plan.name} updated: " + ", ".join(changes),
                admin,
                membership=membership,
            )
        return membership


class PaymentService:
    METHOD_LABELS = {"CASH": "Cash", "UPI": "UPI", "CARD": "Card", "BANK_TRANSFER": "Bank"}

    @classmethod
    def create(cls, member, membership, data, admin):
        """Records a payment; it can't be more than what's still due on the plan."""
        if membership is not None:
            due = cls.balance(membership)
            if data["amount"] > due:
                raise ValidationError(
                    {"amount": f"Amount can't be more than the {rupees(due)} due on this plan."}
                    if due > 0
                    else {"amount": "Nothing is due on this plan."}
                )
        data.setdefault("payment_date", timezone.now())
        payment = Payment.objects.create(
            **data,
            business_account_id=member.business_account_id,
            member=member,
            membership=membership,
            created_by_business_admin=admin,
            is_active=True,
        )
        ActivityService.log(
            member,
            "PAYMENT_ADDED",
            f"Paid {rupees(payment.amount)} by {cls.METHOD_LABELS.get(payment.payment_method, payment.payment_method)}"
            + (f" (ref {payment.transaction_reference})" if payment.transaction_reference else ""),
            admin,
            membership=membership,
            payment=payment,
        )
        return payment

    @classmethod
    def balance(cls, membership):
        """What's still to be paid on a plan: amount − discount − active payments."""
        paid = Payment.objects.filter(membership=membership, is_active=True).aggregate(
            total=Coalesce(Sum("amount"), _ZERO)
        )["total"]
        return membership.amount - membership.discount - paid

    @classmethod
    def void(cls, payment, admin):
        payment.is_active = False
        payment.save()
        ActivityService.log(
            payment.member,
            "PAYMENT_DELETED",
            f"Payment of {rupees(payment.amount)} from {timezone.localtime(payment.payment_date):%d %b %Y} deleted",
            admin,
            membership=payment.membership,
            payment=payment,
        )

    @classmethod
    def get_collections_summary(cls, business_account_id, period_from=None, period_to=None):
        """
        Money metrics the member-count tiles can't provide (they need SUMs):
        today's / this-month's / optional-period collections, and outstanding dues.
        """
        today = timezone.localdate()
        payments = Payment.objects.filter(business_account_id=business_account_id, is_active=True)

        def total(qs):
            amount = qs.aggregate(total=Coalesce(Sum("amount"), _ZERO))["total"]
            return str(amount.quantize(Decimal("0.01")))

        summary = {
            "today_collection": total(payments.filter(payment_date__date=today)),
            "month_collection": total(
                payments.filter(payment_date__year=today.year, payment_date__month=today.month)
            ),
            "outstanding_dues": str(cls.outstanding_dues(business_account_id).quantize(Decimal("0.01"))),
        }

        if period_from or period_to:
            period = payments
            if period_from:
                period = period.filter(payment_date__date__gte=period_from)
            if period_to:
                period = period.filter(payment_date__date__lte=period_to)
            summary["period_collection"] = total(period)

        return summary

    @classmethod
    def outstanding_dues(cls, business_account_id):
        """Σ of every member's positive dues on their current plan."""
        dues = MemberService.get_members(business_account_id).filter(total_due__gt=0)
        return dues.aggregate(total=Coalesce(Sum("total_due"), _ZERO))["total"]


class InsightsService:
    @classmethod
    def get_insights(cls, business_account_id, date_from, date_to):
        days = (date_to - date_from).days + 1
        previous_to = date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=days - 1)
        buckets = cls._buckets(date_from, date_to)

        current = cls._period(business_account_id, date_from, date_to, buckets)
        previous = cls._period(business_account_id, previous_from, previous_to, [])

        def summary(key):
            return {"value": current["totals"][key], "previous": previous["totals"][key]}

        payments = Payment.objects.filter(
            business_account_id=business_account_id,
            is_active=True,
            payment_date__date__gte=date_from,
            payment_date__date__lte=date_to,
        )
        methods = payments.values("payment_method").annotate(total=Sum("amount")).order_by("-total")
        plans = (
            Membership.objects.filter(
                business_account_id=business_account_id, start_date__gte=date_from, start_date__lte=date_to
            )
            .values("membership_plan__name")
            .annotate(count=Count("id"), revenue=Sum(F("amount") - F("discount")))
            .order_by("-count")
        )
        top_dues = (
            MemberService.get_members(business_account_id).filter(total_due__gt=0).order_by("-total_due")[:5]
        )

        return {
            "date_from": date_from,
            "date_to": date_to,
            "summary": {
                key: summary(key)
                for key in ["collections", "new_members", "renewals", "expired", "attendance"]
            },
            "renewal_rate": current["renewal_rate"],
            "previous_renewal_rate": previous["renewal_rate"],
            "live_members": MemberService.get_counts(business_account_id)["live"],
            "outstanding_dues": str(PaymentService.outstanding_dues(business_account_id)),
            "series": current["series"],
            "payment_methods": [
                {"method": row["payment_method"], "total": str(row["total"])} for row in methods
            ],
            "plans": [
                {"name": row["membership_plan__name"], "count": row["count"], "revenue": str(row["revenue"])}
                for row in plans
            ],
            "top_dues": [
                {
                    "member_id": member.id,
                    "name": f"{member.first_name} {member.last_name or ''}".strip(),
                    "amount": str(member.total_due),
                }
                for member in top_dues
            ],
        }

    @classmethod
    def _buckets(cls, date_from, date_to):
        """Days for up to a month, weeks for up to ~4 months, months beyond."""
        days = (date_to - date_from).days + 1
        buckets = []
        start = date_from
        while start <= date_to:
            if days <= 31:
                end, label = start, f"{start:%d %b}"
            elif days <= 120:
                end, label = min(start + timedelta(days=6), date_to), f"{start:%d %b}"
            else:
                last_day = calendar.monthrange(start.year, start.month)[1]
                end, label = min(start.replace(day=last_day), date_to), f"{start:%b %y}"
            buckets.append({"label": label, "start": start, "end": end})
            start = end + timedelta(days=1)
        return buckets

    @classmethod
    def _period(cls, business_account_id, date_from, date_to, buckets):
        """Totals for a date range, plus per-bucket series when buckets are given."""
        payments = [
            (timezone.localtime(p.payment_date).date(), p.amount)
            for p in Payment.objects.filter(
                business_account_id=business_account_id,
                is_active=True,
                payment_date__date__gte=date_from,
                payment_date__date__lte=date_to,
            ).only("payment_date", "amount")
        ]
        new_members = [
            timezone.localtime(created_at).date()
            for created_at in Member.objects.filter(
                business_account_id=business_account_id,
                created_at__date__gte=date_from,
                created_at__date__lte=date_to,
            ).values_list("created_at", flat=True)
        ]

        memberships = Membership.objects.filter(business_account_id=business_account_id)
        # A renewal is any membership that isn't the member's first.
        earlier = Membership.objects.filter(member_id=OuterRef("member_id"), start_date__lt=OuterRef("start_date"))
        renewals = list(
            memberships.filter(start_date__gte=date_from, start_date__lte=date_to)
            .filter(Exists(earlier))
            .values_list("start_date", flat=True)
        )
        # A membership that ended in the period was renewed if another one starts on/after its last day
        # (on it when a plan is changed the same day it started).
        later = Membership.objects.filter(
            member_id=OuterRef("member_id"), start_date__gte=OuterRef("end_date")
        ).exclude(pk=OuterRef("pk"))
        ended = memberships.filter(end_date__gte=date_from, end_date__lte=date_to).annotate(renewed=Exists(later))
        ended_rows = list(ended.values_list("end_date", "renewed"))
        expired = [end_date for end_date, renewed in ended_rows if not renewed]

        attendance = list(
            MemberAttendance.objects.filter(
                business_account_id=business_account_id, attendance_date__gte=date_from, attendance_date__lte=date_to
            ).values_list("attendance_date", flat=True)
        )

        def in_range(day, start, end):
            return start <= day <= end

        series = [
            {
                "label": bucket["label"],
                "collections": str(sum((a for d, a in payments if in_range(d, bucket["start"], bucket["end"])), Decimal("0"))),
                "new_members": sum(1 for d in new_members if in_range(d, bucket["start"], bucket["end"])),
                "renewals": sum(1 for d in renewals if in_range(d, bucket["start"], bucket["end"])),
                "expired": sum(1 for d in expired if in_range(d, bucket["start"], bucket["end"])),
                "attendance": sum(1 for d in attendance if in_range(d, bucket["start"], bucket["end"])),
            }
            for bucket in buckets
        ]
        renewed_count = sum(1 for _, renewed in ended_rows if renewed)
        return {
            "totals": {
                "collections": str(sum((a for _, a in payments), Decimal("0"))),
                "new_members": len(new_members),
                "renewals": len(renewals),
                "expired": len(expired),
                "attendance": len(attendance),
            },
            "renewal_rate": round(100 * renewed_count / len(ended_rows)) if ended_rows else None,
            "series": series,
        }


class NotificationService:
    EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

    @classmethod
    def get_setting(cls, business_account_id):
        setting, _ = NotificationSetting.objects.get_or_create(business_account_id=business_account_id)
        return setting

    @classmethod
    def notify(cls, business_account_id, notification_type, title, message, push=True,
               member_filter=None, member=None, exclude_admin=None):
        """Saves the notification for every admin of the business and pushes it to their phones."""
        admins = BusinessAccountService.get_admins(business_account_id)
        if exclude_admin is not None:
            admins = admins.exclude(id=exclude_admin.id)
        admins = list(admins)
        today = timezone.localdate()
        Notification.objects.bulk_create(
            Notification(
                business_account_id=business_account_id,
                business_admin=admin,
                notification_type=notification_type,
                title=title,
                message=message,
                member_filter=member_filter,
                member=member,
                notification_date=today,
            )
            for admin in admins
        )
        if push and admins:
            tokens = BusinessAdminDevice.objects.filter(business_admin__in=admins, is_active=True).values_list(
                "push_token", flat=True
            )
            data = {"business_account_id": business_account_id, "member_filter": member_filter,
                    "member_id": member.id if member else None}
            cls.send_push(list(tokens), title, message, data)

    @classmethod
    def send_push(cls, tokens, title, body, data):
        """Sends through Expo's free push service; tokens Expo reports as dead are switched off."""
        if not tokens:
            return
        messages = [{"to": token, "title": title, "body": body, "data": data, "sound": "default"} for token in tokens]
        request = urllib.request.Request(
            cls.EXPO_PUSH_URL,
            data=json.dumps(messages).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                tickets = json.load(response).get("data", [])
        except Exception:
            logger.exception("Expo push failed")
            return
        dead = [
            token
            for token, ticket in zip(tokens, tickets)
            if ticket.get("details", {}).get("error") == "DeviceNotRegistered"
        ]
        if dead:
            BusinessAdminDevice.objects.filter(push_token__in=dead).update(is_active=False)

    @classmethod
    def notify_activity(cls, business_account_id, admin, title, message, member):
        """Real-time alert to the business's *other* admins, e.g. a payment recorded at the front desk."""
        if cls.get_setting(business_account_id).activity_alerts:
            cls.notify(business_account_id, "ACTIVITY", title, message, member=member, exclude_admin=admin)

    @classmethod
    def run_daily(cls, run):
        """`morning`: auto-inactive, reminders and summary. `evening`: today's collection summary."""
        today = timezone.localdate()
        if run == "morning":
            cls._subscription_reminders(today)
        accounts = BusinessAccount.objects.filter(is_active=True).values_list("id", flat=True)
        for business_account_id in accounts:
            try:
                if run == "morning":
                    cls._morning(business_account_id, today)
                else:
                    cls._evening(business_account_id, today)
            except Exception:
                logger.exception("Daily %s notifications failed for business %s", run, business_account_id)
        return len(accounts)

    @classmethod
    def _subscription_reminders(cls, today):
        """Tells business owners their trial or plan is about to end; saved under their first business."""
        for owner, title, message in SubscriptionService.reminders(today):
            try:
                already = Notification.objects.filter(
                    business_admin=owner, notification_type="SUBSCRIPTION", notification_date=today
                ).exists()
                business_account_id = SubscriptionService.owned_account_ids(owner).first()
                if already or business_account_id is None:
                    continue
                Notification.objects.create(
                    business_account_id=business_account_id, business_admin=owner, notification_type="SUBSCRIPTION",
                    title=title, message=message, notification_date=today,
                )
                tokens = BusinessAdminDevice.objects.filter(business_admin=owner, is_active=True).values_list(
                    "push_token", flat=True
                )
                cls.send_push(list(tokens), title, message, {"open": "subscription"})
            except Exception:
                logger.exception("Subscription reminder failed for admin %s", owner.id)

    @classmethod
    def _sent(cls, business_account_id, notification_type, today):
        return Notification.objects.filter(
            business_account_id=business_account_id, notification_type=notification_type, notification_date=today
        ).exists()

    @classmethod
    def _names(cls, members, limit=5):
        names = [f"{m.first_name} {m.last_name or ''}".strip() for m in members[:limit]]
        more = len(members) - limit
        return ", ".join(names) + (f" +{more} more" if more > 0 else "")

    @classmethod
    def _ending_on(cls, members, day):
        return [m for m in members if m.active_memberships and m.active_memberships[0].end_date == day]

    @classmethod
    def _morning(cls, business_account_id, today):
        if cls._sent(business_account_id, "MORNING_SUMMARY", today):
            return
        setting = cls.get_setting(business_account_id)
        members = list(MemberService.get_members(business_account_id).filter(is_active=True))

        # 1. Expired more than a week ago → inactive.
        cutoff = today - timedelta(days=AUTO_INACTIVE_AFTER_DAYS)
        stale = [
            m for m in members
            if not m.is_live and m.active_memberships and m.active_memberships[0].end_date < cutoff
        ]
        for member in stale:
            member.is_active = False
            member.save(update_fields=["is_active", "updated_at"])
            ActivityService.log(
                member,
                "MEMBER_DEACTIVATED",
                f"Moved to inactive automatically ({AUTO_INACTIVE_AFTER_DAYS} days after the plan expired)",
            )
        members = [m for m in members if m not in stale]
        # Detail notifications go to the inbox; only the summary is pushed, unless it's turned off.
        push_details = not setting.morning_summary
        if stale:
            cls.notify(
                business_account_id, "AUTO_INACTIVE", f"{len(stale)} expired member(s) moved to inactive",
                f"{cls._names(stale)}. Reactivate them anytime when they come back.",
                push=push_details, member_filter="inactive",
            )

        # 2. Plans ending today / tomorrow / in 3 days. Renewed members aren't included: their
        # active membership is the new one.
        ending = {label: cls._ending_on(members, today + timedelta(days=offset))
                  for label, offset in [("Today", 0), ("Tomorrow", 1), ("In 3 days", 3)]}
        if setting.expiry_reminders and any(ending.values()):
            lines = [f"{label}: {cls._names(group)}" for label, group in ending.items() if group]
            cls.notify(business_account_id, "EXPIRING", "Plans ending soon", "\n".join(lines),
                       push=push_details, member_filter="expiring3")

        # 3. Expired yesterday, and a last call 2 days before they turn inactive.
        expired_yesterday = [m for m in cls._ending_on(members, today - timedelta(days=1)) if not m.is_live]
        last_call_day = today - timedelta(days=AUTO_INACTIVE_AFTER_DAYS - 1)
        last_call = [m for m in cls._ending_on(members, last_call_day) if not m.is_live]
        if setting.expired_followups and (expired_yesterday or last_call):
            lines = []
            if expired_yesterday:
                lines.append(f"Expired yesterday: {cls._names(expired_yesterday)}")
            if last_call:
                lines.append(f"Not renewed, moving to inactive in 2 days: {cls._names(last_call)}")
            cls.notify(business_account_id, "EXPIRED", "Expired plans", "\n".join(lines),
                       push=push_details, member_filter="expired")

        # 4. Weekly (Mondays): dues and members who stopped coming.
        dues = [m for m in members if m.total_due > 0]
        if setting.dues_reminders and today.weekday() == 0 and dues:
            total = sum((m.total_due for m in dues), Decimal("0"))
            cls.notify(business_account_id, "DUES", f"{rupees(total)} dues pending",
                       f"{len(dues)} member(s): {cls._names(dues)}", push=push_details, member_filter="dues")

        if setting.no_show_alerts and today.weekday() == 0:
            week_ago = today - timedelta(days=7)
            uses_attendance = MemberAttendance.objects.filter(
                business_account_id=business_account_id, attendance_date__gte=today - timedelta(days=30)
            ).exists()
            if uses_attendance:
                seen = set(
                    MemberAttendance.objects.filter(
                        business_account_id=business_account_id, attendance_date__gte=week_ago
                    ).values_list("member_id", flat=True)
                )
                missing = [
                    m for m in members
                    if m.is_live and m.id not in seen and m.active_memberships
                    and m.active_memberships[0].start_date <= week_ago
                ]
                if missing:
                    cls.notify(business_account_id, "NO_SHOW", f"{len(missing)} active member(s) not seen this week",
                               cls._names(missing), push=push_details, member_filter="live")

        # 5. Birthdays.
        birthdays = [
            m for m in members
            if m.date_of_birth and (m.date_of_birth.month, m.date_of_birth.day) == (today.month, today.day)
        ]
        if setting.birthday_alerts and birthdays:
            cls.notify(business_account_id, "BIRTHDAY", "🎂 Birthdays today", cls._names(birthdays),
                       push=push_details, member=birthdays[0] if len(birthdays) == 1 else None)

        # 6. The one push admins get each morning.
        parts = []
        if ending["Today"]:
            parts.append(f"{len(ending['Today'])} plan(s) end today")
        soon = len(ending["Tomorrow"]) + len(ending["In 3 days"])
        if soon:
            parts.append(f"{soon} ending in the next 3 days")
        if expired_yesterday:
            parts.append(f"{len(expired_yesterday)} expired yesterday")
        if dues:
            parts.append(f"{rupees(sum((m.total_due for m in dues), Decimal('0')))} dues pending")
        if birthdays:
            parts.append(f"{len(birthdays)} birthday(s)")
        if stale:
            parts.append(f"{len(stale)} moved to inactive")
        # Recorded even when switched off, so the job doesn't run twice in a day.
        Notification.objects.bulk_create(
            Notification(
                business_account_id=business_account_id,
                business_admin=admin,
                notification_type="MORNING_SUMMARY",
                title="Good morning! Today at your gym",
                message=" · ".join(parts) if parts else "All clear: nothing needs your attention today.",
                notification_date=today,
                is_read=not setting.morning_summary,
            )
            for admin in BusinessAccountService.get_admins(business_account_id)
        )
        if setting.morning_summary and parts:
            tokens = BusinessAdminDevice.objects.filter(
                business_admin__in=BusinessAccountService.get_admins(business_account_id), is_active=True
            ).values_list("push_token", flat=True)
            cls.send_push(list(tokens), "Good morning! Today at your gym", " · ".join(parts),
                          {"business_account_id": business_account_id, "member_filter": None, "member_id": None})

    @classmethod
    def _evening(cls, business_account_id, today):
        setting = cls.get_setting(business_account_id)
        if not setting.evening_summary or cls._sent(business_account_id, "EVENING_SUMMARY", today):
            return
        payments = Payment.objects.filter(
            business_account_id=business_account_id, is_active=True, payment_date__date=today
        )
        total = payments.aggregate(total=Coalesce(Sum("amount"), _ZERO))["total"]
        methods = payments.values("payment_method").annotate(total=Sum("amount")).order_by("-total")
        joined = Member.objects.filter(business_account_id=business_account_id, created_at__date=today).count()
        present = MemberAttendance.objects.filter(business_account_id=business_account_id, attendance_date=today).count()

        message = f"Collected {rupees(total)}"
        if methods:
            message += " (" + ", ".join(
                f"{PaymentService.METHOD_LABELS.get(row['payment_method'], row['payment_method'])} {rupees(row['total'])}"
                for row in methods
            ) + ")"
        message += f" · {joined} new member(s) · {present} check-in(s)"
        cls.notify(business_account_id, "EVENING_SUMMARY", "Today's summary", message)


class BusinessAdminJWTAuthentication(BaseAuthentication):
    """Reads the JWT from the access-token cookie or `Authorization: Bearer <jwt>` header."""

    def authenticate(self, request):
        token = request.COOKIES.get(settings.JWT_COOKIE_NAME)
        auth = get_authorization_header(request).split()
        if len(auth) == 2 and auth[0].lower() == b"bearer":
            token = auth[1].decode()

        payload = BusinessAdminAuthService.decode_access_token(token) if token else None
        if payload is None:
            return None

        admin = BusinessAdmin.objects.filter(id=payload.get("admin_id"), is_active=True).first()
        if admin is None:
            return None
        # Tokens from before this check have no stamp and stay valid until they expire.
        if "pw" in payload and payload["pw"] != BusinessAdminAuthService.password_stamp(admin):
            return None

        return admin, payload

    def authenticate_header(self, request):
        return "Bearer"
