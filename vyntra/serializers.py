import re
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from . import receipts
from .services import MemberService
from .models import (
    BusinessAccount,
    BusinessAccountAdmin,
    BusinessAdmin,
    BusinessType,
    DurationType,
    GymMember,
    Member,
    MemberActivity,
    MemberAttendance,
    Membership,
    MembershipPlan,
    Notification,
    NotificationSetting,
    Payment,
    Staff,
    SubscriptionPayment,
    SubscriptionPlan,
)
from .subscriptions import SubscriptionService


def normalize_mobile(value):
    """Drops spaces, dashes and a +91 / 91 / 0 prefix, e.g. "+91 98765-43210" → "9876543210"."""
    return re.sub(r"^(\+91|91(?=\d{10}$)|0(?=\d{10}$))", "", re.sub(r"[\s-]", "", value))


class MobileField(serializers.CharField):
    """
    An Indian mobile number: 10 digits starting with 6–9. Spaces, dashes and a +91 / 91 / 0
    prefix are accepted and dropped, so it's always stored as the bare 10 digits.
    """

    default_error_messages = {"invalid_mobile": "Enter a valid 10-digit mobile number."}

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 20)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = normalize_mobile(super().to_internal_value(data))
        if not re.fullmatch(r"[6-9]\d{9}", value):
            self.fail("invalid_mobile")
        return value


def _money(value):
    """Format a Decimal as a 2-place string, matching how DecimalField fields serialize."""
    return str(Decimal(value).quantize(Decimal("0.01")))


class BusinessAdminSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="name")
    mobile_no = serializers.CharField(source="phone")

    class Meta:
        model = BusinessAdmin
        fields = ["id", "full_name", "mobile_no", "email", "is_active", "last_login_at", "created_at"]


class SignupSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    mobile_no = MobileField()
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(write_only=True, max_length=128)

    def validate_email(self, value):
        value = value.lower()
        if BusinessAdmin.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate_mobile_no(self, value):
        # phone isn't unique in the DB, but login by mobile requires it to be.
        if BusinessAdmin.objects.filter(phone=value).exists():
            raise serializers.ValidationError("An account with this mobile number already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value


class LoginSerializer(serializers.Serializer):
    login = serializers.CharField(max_length=255)
    password = serializers.CharField(write_only=True, max_length=128)


class BusinessTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessType
        fields = ["id", "name", "code", "description"]


class BusinessAccountSerializer(serializers.ModelSerializer):
    business_type = BusinessTypeSerializer(read_only=True)
    business_type_id = serializers.PrimaryKeyRelatedField(
        queryset=BusinessType.objects.filter(is_active=True),
        source="business_type",
        write_only=True,
        error_messages={"does_not_exist": "Business type not found or inactive."},
    )
    logo_url = serializers.URLField(max_length=500, required=False, allow_null=True, allow_blank=True)
    contact_no = MobileField(required=False, allow_null=True, allow_blank=True)
    email = serializers.EmailField(max_length=255, required=False, allow_null=True, allow_blank=True)
    website = serializers.URLField(max_length=500, required=False, allow_null=True, allow_blank=True)
    # Owner and read-only state for the logged-in admin (pass context={"admin": ...}).
    access = serializers.SerializerMethodField()

    class Meta:
        model = BusinessAccount
        fields = [
            "id", "business_type", "business_type_id", "name", "logo_url",
            "address", "city", "state", "country", "address_lat", "address_lng",
            "contact_no", "email", "website", "terms_and_conditions",
            "is_active", "access", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_access(self, account):
        admin = self.context.get("admin")
        return SubscriptionService.business_access(account.id, admin) if admin else None


class BusinessAccountUpdateSerializer(BusinessAccountSerializer):
    # business_type can't be changed for now; is_active is only changed by DELETE (soft delete).
    business_type_id = None

    class Meta(BusinessAccountSerializer.Meta):
        fields = [f for f in BusinessAccountSerializer.Meta.fields if f != "business_type_id"]
        read_only_fields = BusinessAccountSerializer.Meta.read_only_fields + ["is_active"]


class BusinessAccountQuerySerializer(serializers.Serializer):
    business_account_id = serializers.IntegerField()


class MemberListQuerySerializer(BusinessAccountQuerySerializer):
    search = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    email = serializers.CharField(required=False)
    member_code = serializers.CharField(required=False)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)
    # live: a membership covers today. expired: active member whose latest plan has ended.
    status = serializers.ChoiceField(choices=["live", "expired"], required=False)
    # Filter on the active membership's end_date (expired / expiring members).
    end_date_from = serializers.DateField(required=False)
    end_date_to = serializers.DateField(required=False)
    # Only members with an outstanding balance across their memberships (dues pending).
    has_dues = serializers.BooleanField(required=False, allow_null=True, default=None)


class MemberDetailQuerySerializer(BusinessAccountQuerySerializer):
    member_id = serializers.IntegerField()


class PaymentSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    payment_date = serializers.DateTimeField(required=False)

    class Meta:
        model = Payment
        fields = ["id", "amount", "payment_date", "payment_method", "transaction_reference", "notes", "created_at"]
        read_only_fields = ["id", "created_at"]


class PaymentDetailSerializer(serializers.ModelSerializer):
    """Read shape for the standalone payments endpoint (includes member/membership refs)."""

    class Meta:
        model = Payment
        fields = [
            "id", "member_id", "membership_id", "amount", "payment_date", "payment_method",
            "transaction_reference", "notes", "is_active", "created_at",
        ]


class PaymentCreateSerializer(serializers.ModelSerializer):
    member_id = serializers.IntegerField(write_only=True)
    membership_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    payment_date = serializers.DateTimeField(required=False)

    class Meta:
        model = Payment
        fields = [
            "member_id", "membership_id", "amount", "payment_date", "payment_method",
            "transaction_reference", "notes",
        ]

    def validate_member_id(self, value):
        member = Member.objects.filter(
            id=value, business_account_id=self.context["business_account_id"], is_active=True
        ).first()
        if member is None:
            raise serializers.ValidationError("Member not found or inactive.")
        return member

    def validate_membership_id(self, value):
        if value is None:
            return None
        membership = Membership.objects.filter(
            id=value, business_account_id=self.context["business_account_id"]
        ).first()
        if membership is None:
            raise serializers.ValidationError("Membership not found.")
        return membership

    def validate(self, attrs):
        membership = attrs.get("membership_id")
        member = attrs.get("member_id")
        if membership is not None and member is not None and membership.member_id != member.id:
            raise serializers.ValidationError({"membership_id": "Membership does not belong to this member."})
        return attrs


class PaymentListQuerySerializer(BusinessAccountQuerySerializer):
    member_id = serializers.IntegerField(required=False)
    payment_date_from = serializers.DateField(required=False)
    payment_date_to = serializers.DateField(required=False)


class PaymentDetailQuerySerializer(BusinessAccountQuerySerializer):
    payment_id = serializers.IntegerField()


class MembershipListQuerySerializer(BusinessAccountQuerySerializer):
    member_id = serializers.IntegerField()


class CollectionsQuerySerializer(BusinessAccountQuerySerializer):
    period_from = serializers.DateField(required=False)
    period_to = serializers.DateField(required=False)


class GymMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = GymMember
        fields = ["emergency_contact_name", "emergency_contact_phone", "emergency_contact_address"]


class MemberSerializer(serializers.ModelSerializer):
    phone = MobileField(required=False, allow_null=True, allow_blank=True)
    email = serializers.EmailField(max_length=255, required=False, allow_null=True, allow_blank=True)
    membership_plan_id = serializers.IntegerField(write_only=True)
    start_date = serializers.DateField(write_only=True, required=False)
    discount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, write_only=True
    )
    payment = PaymentSerializer(write_only=True, required=False)
    # Emergency contact / address live on the gym_member 1:1 table; written flat, read nested.
    emergency_contact_name = serializers.CharField(
        max_length=200, required=False, allow_null=True, allow_blank=True, write_only=True
    )
    emergency_contact_phone = MobileField(required=False, allow_null=True, allow_blank=True, write_only=True)
    emergency_contact_address = serializers.CharField(
        max_length=500, required=False, allow_null=True, allow_blank=True, write_only=True
    )
    gym_details = GymMemberSerializer(read_only=True)
    membership = serializers.SerializerMethodField()
    next_membership = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    total_due = serializers.SerializerMethodField()

    class Meta:
        model = Member
        fields = [
            "id", "member_code", "first_name", "last_name", "phone", "email",
            "date_of_birth", "gender", "is_active", "membership_plan_id", "start_date", "discount",
            "payment", "emergency_contact_name", "emergency_contact_phone", "emergency_contact_address",
            "gym_details", "membership", "next_membership", "status", "total_due", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_status(self, member):
        """live / upcoming / expired / no_plan / inactive (members are loaded with `is_live`)."""
        if not member.is_active:
            return "inactive"
        if member.is_live:
            return "live"
        if not member.active_memberships:
            return "no_plan"
        return "upcoming" if member.active_memberships[0].start_date > timezone.localdate() else "expired"

    def get_total_due(self, member):
        return _money(member.total_due)

    def get_membership(self, member):
        """The current plan (members are loaded by MemberService.get_members)."""
        current, _ = MemberService.current_and_next(member)
        return MembershipSerializer(current).data if current else None

    def get_next_membership(self, member):
        """A renewed-early plan that starts after the current one."""
        _, next_plan = MemberService.current_and_next(member)
        return MembershipSerializer(next_plan).data if next_plan else None

    def validate_membership_plan_id(self, value):
        plan = (
            MembershipPlan.objects.select_related("duration_type")
            .filter(id=value, business_account_id=self.context["business_account_id"], is_active=True)
            .first()
        )
        if plan is None:
            raise serializers.ValidationError("Membership plan not found or inactive.")
        return plan

    def validate_member_code(self, value):
        members = Member.objects.filter(business_account_id=self.context["business_account_id"], member_code=value)
        if self.instance:
            members = members.exclude(id=self.instance.id)
        if members.exists():
            raise serializers.ValidationError("A member with this code already exists in this business.")
        return value

    def validate(self, attrs):
        # Discount applies to the plan being assigned; it can't exceed the plan's price.
        plan = attrs.get("membership_plan_id")
        discount = attrs.get("discount")
        if plan is not None and discount is not None and discount > plan.amount:
            raise serializers.ValidationError({"discount": "Discount can't exceed the plan amount."})
        return attrs


class StaffListQuerySerializer(BusinessAccountQuerySerializer):
    search = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    employee_code = serializers.CharField(required=False)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)


class StaffDetailQuerySerializer(BusinessAccountQuerySerializer):
    staff_id = serializers.IntegerField()


class StaffSerializer(serializers.ModelSerializer):
    phone = MobileField(required=False, allow_null=True, allow_blank=True)
    email = serializers.EmailField(max_length=255, required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Staff
        fields = [
            "id", "employee_code", "first_name", "last_name", "phone", "email",
            "role", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_employee_code(self, value):
        staff = Staff.objects.filter(business_account_id=self.context["business_account_id"], employee_code=value)
        if self.instance:
            staff = staff.exclude(id=self.instance.id)
        if staff.exists():
            raise serializers.ValidationError("A staff member with this code already exists in this business.")
        return value


class DurationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DurationType
        fields = ["id", "name", "code"]


class MembershipPlanDetailQuerySerializer(BusinessAccountQuerySerializer):
    plan_id = serializers.IntegerField()


class MembershipPlanSerializer(serializers.ModelSerializer):
    duration_type = DurationTypeSerializer(read_only=True)
    duration_type_id = serializers.PrimaryKeyRelatedField(
        queryset=DurationType.objects.filter(is_active=True),
        source="duration_type",
        write_only=True,
        error_messages={"does_not_exist": "Duration type not found or inactive."},
    )
    duration_value = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)

    class Meta:
        model = MembershipPlan
        fields = [
            "id", "name", "duration_type", "duration_type_id", "duration_value",
            "amount", "description", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MembershipSerializer(serializers.ModelSerializer):
    membership_plan = MembershipPlanSerializer(read_only=True)
    # Prefetched as `active_payments` by MemberService.get_members / get_memberships.
    payments = PaymentSerializer(source="active_payments", many=True, read_only=True)
    net_payable = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id", "membership_plan", "start_date", "end_date", "amount", "discount",
            "net_payable", "amount_paid", "balance", "is_active", "payments",
        ]

    def _amount_paid(self, membership):
        return sum((p.amount for p in membership.active_payments), Decimal("0"))

    def get_amount_paid(self, membership):
        return _money(self._amount_paid(membership))

    def get_net_payable(self, membership):
        return _money(membership.amount - membership.discount)

    def get_balance(self, membership):
        return _money((membership.amount - membership.discount) - self._amount_paid(membership))


class AttendanceMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ["id", "member_code", "first_name", "last_name"]


class MemberAttendanceListQuerySerializer(BusinessAccountQuerySerializer):
    attendance_date = serializers.DateField(required=False)
    member_id = serializers.IntegerField(required=False)


class MemberAttendanceDetailQuerySerializer(BusinessAccountQuerySerializer):
    attendance_id = serializers.IntegerField()


class MemberAttendanceSerializer(serializers.ModelSerializer):
    member = AttendanceMemberSerializer(read_only=True)
    member_id = serializers.IntegerField(write_only=True)
    attendance_date = serializers.DateField(default=timezone.localdate)
    check_in_time = serializers.DateTimeField(default=timezone.now, allow_null=True)

    class Meta:
        model = MemberAttendance
        fields = [
            "id", "member", "member_id", "attendance_date", "check_in_time", "check_out_time",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_member_id(self, value):
        member = Member.objects.filter(
            id=value, business_account_id=self.context["business_account_id"], is_active=True
        ).first()
        if member is None:
            raise serializers.ValidationError("Member not found or inactive.")
        return member

    def validate(self, attrs):
        if "member_id" in attrs and MemberAttendance.objects.filter(
            member=attrs["member_id"], attendance_date=attrs["attendance_date"]
        ).exists():
            raise serializers.ValidationError("Attendance is already marked for this member on this date.")

        check_in = attrs.get("check_in_time", getattr(self.instance, "check_in_time", None))
        check_out = attrs.get("check_out_time", getattr(self.instance, "check_out_time", None))
        if check_in and check_out and check_out < check_in:
            raise serializers.ValidationError({"check_out_time": "Check-out time can't be before check-in time."})
        return attrs


class MemberAttendanceUpdateSerializer(MemberAttendanceSerializer):
    # Only the times can be corrected; member and date are fixed once marked.
    member_id = None
    attendance_date = serializers.DateField(read_only=True)

    class Meta(MemberAttendanceSerializer.Meta):
        fields = [f for f in MemberAttendanceSerializer.Meta.fields if f != "member_id"]


class BusinessAccountAdminSerializer(serializers.ModelSerializer):
    admin = BusinessAdminSerializer(source="business_admin", read_only=True)

    class Meta:
        model = BusinessAccountAdmin
        fields = ["admin", "role", "is_active", "created_at"]


class AdminDetailQuerySerializer(BusinessAccountQuerySerializer):
    admin_id = serializers.IntegerField()


class BusinessAdminUpdateSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="name", max_length=200)
    mobile_no = MobileField(source="phone")
    email = serializers.EmailField(max_length=255)
    # Applies to the admin's access to this business (business_account_admin), not the admin globally.
    is_active = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = BusinessAdmin
        fields = ["full_name", "mobile_no", "email", "is_active"]

    def validate_email(self, value):
        value = value.lower()
        if BusinessAdmin.objects.filter(email__iexact=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_mobile_no(self, value):
        if BusinessAdmin.objects.filter(phone=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("An account with this mobile number already exists.")
        return value

    def validate_is_active(self, value):
        if not value and self.instance == self.context["request_admin"]:
            raise serializers.ValidationError("You can't deactivate yourself.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    """A new password for yourself (you're already signed in) or, from Manage Admins, for another admin."""

    new_password = serializers.CharField(write_only=True, max_length=128)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class MembershipActionSerializer(serializers.Serializer):
    """Renew (rejoining), change plan (replaces the current one) or renew early (adds the next plan)."""

    action = serializers.ChoiceField(choices=["renew", "change_plan", "renew_early"])
    member_id = serializers.IntegerField()
    membership_plan_id = serializers.IntegerField()
    start_date = serializers.DateField(required=False)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    payment = PaymentSerializer(required=False)

    def validate_member_id(self, value):
        member = Member.objects.filter(id=value, business_account_id=self.context["business_account_id"]).first()
        if member is None:
            raise serializers.ValidationError("Member not found.")
        return member

    def validate_membership_plan_id(self, value):
        plan = (
            MembershipPlan.objects.select_related("duration_type")
            .filter(id=value, business_account_id=self.context["business_account_id"], is_active=True)
            .first()
        )
        if plan is None:
            raise serializers.ValidationError("Membership plan not found or inactive.")
        return plan

    def validate(self, attrs):
        discount = attrs.get("discount")
        if discount is not None and discount > attrs["membership_plan_id"].amount:
            raise serializers.ValidationError({"discount": "Discount can't exceed the plan amount."})
        return attrs


class MembershipUpdateSerializer(serializers.Serializer):
    """Correct the start date / discount, or extend (freeze) by some days."""

    start_date = serializers.DateField(required=False)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    extend_days = serializers.IntegerField(min_value=1, max_value=365, required=False)
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Nothing to update.")
        discount = attrs.get("discount")
        if discount is not None and discount > self.context["membership"].amount:
            raise serializers.ValidationError({"discount": "Discount can't exceed the plan amount."})
        return attrs


class MembershipDetailQuerySerializer(BusinessAccountQuerySerializer):
    membership_id = serializers.IntegerField()


class MemberActivitySerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by_business_admin.name", default=None)

    class Meta:
        model = MemberActivity
        fields = ["id", "activity_type", "description", "membership_id", "payment_id", "created_by", "created_at"]


class InsightsQuerySerializer(BusinessAccountQuerySerializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()

    def validate(self, attrs):
        if attrs["date_to"] < attrs["date_from"]:
            raise serializers.ValidationError({"date_to": "End date can't be before the start date."})
        if (attrs["date_to"] - attrs["date_from"]).days > 731:
            raise serializers.ValidationError({"date_to": "Choose a period of up to 2 years."})
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "notification_type", "title", "message", "member_filter", "member_id",
            "notification_date", "is_read", "created_at",
        ]


class NotificationReadSerializer(BusinessAccountQuerySerializer):
    # Omit to mark all as read.
    notification_id = serializers.IntegerField(required=False)


class NotificationSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSetting
        fields = [
            "morning_summary", "expiry_reminders", "expired_followups", "dues_reminders",
            "no_show_alerts", "birthday_alerts", "activity_alerts", "evening_summary",
        ]


class DeviceSerializer(serializers.Serializer):
    push_token = serializers.CharField(max_length=255)
    platform = serializers.CharField(max_length=20, required=False, allow_blank=True)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["code", "name", "months", "price", "currency", "google_base_plan_id"]


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", default=None)
    method = serializers.SerializerMethodField()
    receipt_number = serializers.SerializerMethodField()
    # Opens the printable receipt at /receipts/<token>/ without the login token.
    receipt_token = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPayment
        fields = ["id", "provider", "amount", "currency", "status", "plan_name", "period_start", "period_end",
                  "paid_at", "method", "receipt_number", "receipt_token"]

    def get_method(self, payment):
        return receipts.payment_method(payment)

    def get_receipt_number(self, payment):
        return receipts.receipt_number(payment)

    def get_receipt_token(self, payment):
        return receipts.receipt_token(payment)


class SubscriptionSummarySerializer(serializers.Serializer):
    state = serializers.CharField()
    has_access = serializers.BooleanField()
    can_purchase = serializers.BooleanField()
    trial_ends_at = serializers.DateTimeField()
    current_period_end = serializers.DateTimeField(allow_null=True)
    access_until = serializers.DateTimeField()
    days_left = serializers.IntegerField()
    auto_renew = serializers.BooleanField()
    provider = serializers.CharField(allow_null=True)
    plan = SubscriptionPlanSerializer(allow_null=True)
    owns_business = serializers.BooleanField()


class PlanChoiceSerializer(serializers.Serializer):
    plan_code = serializers.SlugRelatedField(
        slug_field="code",
        queryset=SubscriptionPlan.objects.filter(is_active=True),
        source="plan",
        error_messages={"does_not_exist": "Choose one of the available plans."},
    )


class RazorpaySyncSerializer(serializers.Serializer):
    subscription_id = serializers.CharField(max_length=100)


class RazorpayConfirmSerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_subscription_id = serializers.CharField(max_length=100)
    razorpay_signature = serializers.CharField(max_length=200)


class GooglePlayConfirmSerializer(serializers.Serializer):
    purchase_token = serializers.CharField(max_length=1000)
