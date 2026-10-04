from decimal import Decimal

from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from .models import (
    BusinessAccount,
    BusinessAccountAdmin,
    BusinessAdmin,
    BusinessType,
    DurationType,
    Member,
    MemberAttendance,
    Membership,
    MembershipPlan,
    Payment,
    Staff,
)


class BusinessAdminSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="name")
    mobile_no = serializers.CharField(source="phone")

    class Meta:
        model = BusinessAdmin
        fields = ["id", "full_name", "mobile_no", "email", "is_active", "last_login_at", "created_at"]


class SignupSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    mobile_no = serializers.RegexField(r"^\d{10,15}$", error_messages={"invalid": "Enter a valid mobile number."})
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
    email = serializers.EmailField(max_length=255, required=False, allow_null=True, allow_blank=True)
    website = serializers.URLField(max_length=500, required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = BusinessAccount
        fields = [
            "id", "business_type", "business_type_id", "name", "logo_url",
            "address", "city", "state", "country", "address_lat", "address_lng",
            "contact_no", "email", "website", "terms_and_conditions",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
    member_code = serializers.CharField(required=False)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)
    # Filter on the active membership's end_date (expired / expiring members).
    end_date_from = serializers.DateField(required=False)
    end_date_to = serializers.DateField(required=False)


class MemberDetailQuerySerializer(BusinessAccountQuerySerializer):
    member_id = serializers.IntegerField()


class PaymentSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    payment_date = serializers.DateTimeField(required=False)

    class Meta:
        model = Payment
        fields = ["id", "amount", "payment_date", "payment_method", "transaction_reference", "notes", "created_at"]
        read_only_fields = ["id", "created_at"]


class MemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=255, required=False, allow_null=True, allow_blank=True)
    membership_plan_id = serializers.IntegerField(write_only=True)
    start_date = serializers.DateField(write_only=True, required=False)
    payment = PaymentSerializer(write_only=True, required=False)
    membership = serializers.SerializerMethodField()

    class Meta:
        model = Member
        fields = [
            "id", "member_code", "first_name", "last_name", "phone", "email",
            "date_of_birth", "gender", "is_active", "membership_plan_id", "start_date", "payment",
            "membership", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_membership(self, member):
        # Members are loaded with their active membership prefetched as `active_memberships`.
        memberships = member.active_memberships
        return MembershipSerializer(memberships[0]).data if memberships else None

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


class StaffListQuerySerializer(BusinessAccountQuerySerializer):
    search = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    employee_code = serializers.CharField(required=False)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)


class StaffDetailQuerySerializer(BusinessAccountQuerySerializer):
    staff_id = serializers.IntegerField()


class StaffSerializer(serializers.ModelSerializer):
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
    # Prefetched by MemberService.get_members.
    payments = PaymentSerializer(source="active_payments", many=True, read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "membership_plan", "start_date", "end_date", "amount", "is_active", "payments"]


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
    mobile_no = serializers.RegexField(
        r"^\d{10,15}$", source="phone", error_messages={"invalid": "Enter a valid mobile number."}
    )
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
    current_password = serializers.CharField(write_only=True, max_length=128)
    new_password = serializers.CharField(write_only=True, max_length=128)

    def validate_current_password(self, value):
        if not check_password(value, self.context["request_admin"].password):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        validate_password(value)
        return value
