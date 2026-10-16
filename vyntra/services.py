import calendar
import time
from datetime import timedelta
from decimal import Decimal

import jwt
from django.conf import settings
from django.db.models import DecimalField, F, OuterRef, Prefetch, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import PermissionDenied

from .models import BusinessAccount, BusinessAdmin, Member, Membership, Payment

_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Value(Decimal("0"), output_field=_MONEY)


def _membership_paid_expr():
    """Sum of a membership's active payments, as a correlated subquery (0 when none)."""
    return Coalesce(
        Subquery(
            Payment.objects.filter(membership_id=OuterRef("pk"), is_active=True)
            .values("membership_id")
            .annotate(s=Sum("amount"))
            .values("s"),
            output_field=_MONEY,
        ),
        _ZERO,
    )


class BusinessAdminAuthService:
    ACCESS_TOKEN_MAX_AGE = 180 * 24 * 60 * 60  # seconds

    @classmethod
    def generate_access_token(cls, business_admin):
        current_time = time.time()
        token_exp = int(current_time) + int(cls.ACCESS_TOKEN_MAX_AGE)
        payload = {"admin_id": business_admin.id, "time": current_time, "exp": token_exp}

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
    def check_admin_access(cls, business_admin, business_account_id):
        """Raise 403 unless the admin has an active mapping to this business account."""
        if not cls.get_accounts_for_admin(business_admin).filter(id=business_account_id).exists():
            raise PermissionDenied("You do not have access to this business account.")


class MemberService:
    @classmethod
    def get_members(cls, business_account_id):
        """
        Members of the business, with their active membership (plan + payments) prefetched as
        `active_memberships` and each membership's payments as `active_payments`.
        """
        active_payments = Payment.objects.filter(is_active=True).order_by("-payment_date")
        active_memberships = (
            Membership.objects.filter(is_active=True)
            .select_related("membership_plan__duration_type")
            .prefetch_related(Prefetch("payments", queryset=active_payments, to_attr="active_payments"))
        )
        return (
            Member.objects.filter(business_account_id=business_account_id)
            .select_related("gym_details")
            .prefetch_related(
                Prefetch("memberships", queryset=active_memberships, to_attr="active_memberships")
            )
        )

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
    def member_ids_with_dues(cls, business_account_id):
        """Member ids whose active membership still has an outstanding balance (> 0)."""
        return (
            Membership.objects.filter(business_account_id=business_account_id, is_active=True)
            .annotate(paid=_membership_paid_expr())
            .annotate(due=F("amount") - F("discount") - F("paid"))
            .filter(due__gt=0)
            .values_list("member_id", flat=True)
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


class PaymentService:
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
            "outstanding_dues": str(cls._outstanding_dues(business_account_id).quantize(Decimal("0.01"))),
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
    def _outstanding_dues(cls, business_account_id):
        """Σ over active memberships of max(0, amount − discount − paid), computed in the DB."""
        return (
            Membership.objects.filter(business_account_id=business_account_id, is_active=True)
            .annotate(paid=_membership_paid_expr())
            .annotate(due=Greatest(F("amount") - F("discount") - F("paid"), _ZERO, output_field=_MONEY))
            .aggregate(total=Coalesce(Sum("due"), _ZERO))["total"]
        )


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

        return admin, payload

    def authenticate_header(self, request):
        return "Bearer"
