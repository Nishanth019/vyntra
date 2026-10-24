from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import Member, PgBed, PgBill, PgBillItem, PgDepositEntry, PgProperty, PgRoom, PgTenancy, PgTenant
from .serializers import BusinessAccountQuerySerializer, MobileField, PaymentSerializer, _money

PAYMENT_METHODS = ["CASH", "UPI", "CARD", "BANK_TRANSFER"]
MONEY = {"max_digits": 12, "decimal_places": 2}


class PgPropertySerializer(serializers.ModelSerializer):
    property_type = serializers.ChoiceField(choices=["PG", "HOSTEL", "COLIVING"], required=False)
    gender = serializers.ChoiceField(choices=["MALE", "FEMALE", "COED"], required=False)
    facilities = serializers.ListField(child=serializers.CharField(max_length=30), required=False, allow_null=True)
    default_due_day = serializers.IntegerField(min_value=1, max_value=28, required=False)
    eb_unit_price = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0, required=False,
                                             allow_null=True)

    class Meta:
        model = PgProperty
        fields = [
            "property_type", "gender", "facilities", "default_due_day", "prorate_first_bill", "notice_period_days",
            "eb_unit_price", "upi_id", "house_rules",
        ]


# ---------------------------------------------------------------------------------------------------------------
# Rooms and beds


class RoomRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = PgRoom
        fields = ["id", "room_number", "floor", "is_ac"]


class BedRefSerializer(serializers.ModelSerializer):
    room = RoomRefSerializer(read_only=True)

    class Meta:
        model = PgBed
        fields = ["id", "label", "room"]


class PgBedSerializer(serializers.ModelSerializer):
    """A bed and who lives on it (context["occupants"]: {bed_id: tenancy})."""

    occupant = serializers.SerializerMethodField()

    class Meta:
        model = PgBed
        fields = ["id", "label", "occupant"]

    def get_occupant(self, bed):
        tenancy = self.context.get("occupants", {}).get(bed.id)
        if tenancy is None:
            return None
        return {
            "member_id": tenancy.member_id,
            "name": str(tenancy.member),
            "phone": tenancy.member.phone,
            "tenancy_status": tenancy.status,
            "expected_end_date": tenancy.expected_end_date,
            "rent": _money(tenancy.rent),
        }


class PgRoomSerializer(serializers.ModelSerializer):
    rent_per_bed = serializers.DecimalField(**MONEY, min_value=0)
    amenities = serializers.ListField(child=serializers.CharField(max_length=30), required=False, allow_null=True)
    bed_count = serializers.IntegerField(min_value=1, max_value=30, write_only=True)
    beds = serializers.SerializerMethodField()

    class Meta:
        model = PgRoom
        fields = ["id", "room_number", "floor", "is_ac", "rent_per_bed", "amenities", "notes", "bed_count", "beds",
                  "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_beds(self, room):
        beds = sorted((b for b in room.beds.all() if b.is_active), key=lambda b: (len(b.label), b.label))
        return PgBedSerializer(beds, many=True, context=self.context).data

    def validate_room_number(self, value):
        value = value.strip()
        rooms = PgRoom.objects.filter(business_account_id=self.context["business_account_id"], room_number__iexact=value,
                                      is_active=True)
        if self.instance:
            rooms = rooms.exclude(id=self.instance.id)
        if rooms.exists():
            raise serializers.ValidationError("A room with this number already exists.")
        return value


class RoomDetailQuerySerializer(BusinessAccountQuerySerializer):
    room_id = serializers.IntegerField()


# ---------------------------------------------------------------------------------------------------------------
# Tenants


class PgTenantDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PgTenant
        fields = [
            "occupation", "permanent_address", "id_type", "id_last4", "emergency_contact_name",
            "emergency_contact_phone", "emergency_contact_relation", "vehicle_number",
        ]


class PgTenancySerializer(serializers.ModelSerializer):
    bed = BedRefSerializer(read_only=True)

    class Meta:
        model = PgTenancy
        fields = [
            "id", "status", "bed", "rent", "billing_cycle_months", "due_day", "start_date", "notice_date",
            "expected_end_date", "end_date", "leave_reason", "deposit_amount", "advance_balance",
        ]


class PgTenantSerializer(serializers.ModelSerializer):
    """A tenant as the lists show them (members loaded by PgService.tenants + attach_tenancies)."""

    pg_details = PgTenantDetailsSerializer(read_only=True)
    tenancy = serializers.SerializerMethodField()
    total_due = serializers.SerializerMethodField()
    oldest_due_date = serializers.DateField(read_only=True)

    class Meta:
        model = Member
        fields = [
            "id", "member_code", "first_name", "last_name", "phone", "email", "gender", "date_of_birth",
            "is_active", "pg_details", "tenancy", "total_due", "oldest_due_date", "created_at",
        ]

    def get_tenancy(self, member):
        tenancy = getattr(member, "tenancy", None)
        return PgTenancySerializer(tenancy).data if tenancy else None

    def get_total_due(self, member):
        return _money(member.total_due)


PG_DETAIL_FIELDS = [
    "occupation", "permanent_address", "id_type", "id_last4", "emergency_contact_name", "emergency_contact_phone",
    "emergency_contact_relation", "vehicle_number",
]


class ChargeSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))


class RentPaymentSerializer(PaymentSerializer):
    payment_method = serializers.ChoiceField(choices=PAYMENT_METHODS)

    class Meta(PaymentSerializer.Meta):
        pass


class StayTermsSerializer(serializers.Serializer):
    """Rent and dates of a new stay (moving in, or coming back after leaving)."""

    bed_id = serializers.IntegerField()
    rent = serializers.DecimalField(**MONEY, min_value=0, required=False)
    billing_cycle_months = serializers.ChoiceField(choices=[1, 3, 6, 12], required=False)
    due_day = serializers.IntegerField(min_value=1, max_value=28, required=False)
    start_date = serializers.DateField(required=False)
    prorate_first_bill = serializers.BooleanField(required=False)
    deposit_amount = serializers.DecimalField(**MONEY, min_value=0, required=False)
    deposit_paid = serializers.DecimalField(**MONEY, min_value=0, required=False)
    charges = ChargeSerializer(many=True, required=False)
    payment = RentPaymentSerializer(required=False)

    def validate_bed_id(self, value):
        bed = PgBed.objects.select_related("room").filter(
            id=value, business_account_id=self.context["business_account_id"], is_active=True, room__is_active=True
        ).first()
        if bed is None:
            raise serializers.ValidationError("Bed not found.")
        return bed

    def validate(self, attrs):
        if attrs.get("deposit_paid") and attrs["deposit_paid"] > attrs.get("deposit_amount", Decimal("0")):
            raise serializers.ValidationError({"deposit_paid": "Deposit paid can't be more than the deposit."})
        return attrs


class PgTenantWriteSerializer(StayTermsSerializer):
    """Adds a tenant (with their stay) or, on update, edits their details and rent terms."""

    member_code = serializers.CharField(max_length=100, required=False)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    phone = MobileField()
    email = serializers.EmailField(max_length=255, required=False, allow_null=True, allow_blank=True)
    gender = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    occupation = serializers.CharField(max_length=200, required=False, allow_null=True, allow_blank=True)
    permanent_address = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)
    id_type = serializers.ChoiceField(choices=["AADHAAR", "PAN", "PASSPORT", "DL", "VOTER"], required=False,
                                      allow_null=True, allow_blank=True)
    id_last4 = serializers.RegexField(r"^[0-9A-Za-z]{4}$", required=False, allow_null=True, allow_blank=True,
                                      error_messages={"invalid": "Enter the last 4 characters of the ID."})
    emergency_contact_name = serializers.CharField(max_length=200, required=False, allow_null=True, allow_blank=True)
    emergency_contact_phone = MobileField(required=False, allow_null=True, allow_blank=True)
    emergency_contact_relation = serializers.CharField(max_length=50, required=False, allow_null=True,
                                                       allow_blank=True)
    vehicle_number = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.partial:
            # Editing: the bed changes through Shift, the first bill and payments are already done.
            for name in ["bed_id", "start_date", "prorate_first_bill", "deposit_paid", "charges", "payment"]:
                self.fields.pop(name)

    def validate_member_code(self, value):
        members = Member.objects.filter(business_account_id=self.context["business_account_id"], member_code=value)
        if self.context.get("member"):
            members = members.exclude(id=self.context["member"].id)
        if members.exists():
            raise serializers.ValidationError("A tenant with this ID already exists.")
        return value


class TenantDetailQuerySerializer(BusinessAccountQuerySerializer):
    member_id = serializers.IntegerField()


class TenantListQuerySerializer(BusinessAccountQuerySerializer):
    status = serializers.ChoiceField(choices=["living", "active", "notice", "past"], required=False)
    search = serializers.CharField(required=False)
    has_dues = serializers.BooleanField(required=False, allow_null=True, default=None)


class TenantActionSerializer(serializers.Serializer):
    """shift: another bed · notice: leaving on a date · cancel_notice · checkout: move out · move_in: come back."""

    action = serializers.ChoiceField(choices=["shift", "notice", "cancel_notice", "checkout", "move_in"])
    member_id = serializers.IntegerField()
    # shift (and move_in)
    bed_id = serializers.IntegerField(required=False)
    rent = serializers.DecimalField(**MONEY, min_value=0, required=False)
    # notice / checkout
    leave_date = serializers.DateField(required=False)
    notice_date = serializers.DateField(required=False)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    # checkout
    prorate_last_bill = serializers.BooleanField(required=False, default=False)
    dues_from_deposit = serializers.BooleanField(required=False, default=False)
    deduction = serializers.DecimalField(**MONEY, min_value=0, required=False)
    deduction_reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    refund_method = serializers.ChoiceField(choices=PAYMENT_METHODS, required=False)

    def validate_member_id(self, value):
        member = Member.objects.filter(id=value, business_account_id=self.context["business_account_id"]).first()
        if member is None:
            raise serializers.ValidationError("Tenant not found.")
        return member

    def validate(self, attrs):
        action = attrs["action"]
        if action == "shift":
            if "bed_id" not in attrs:
                raise serializers.ValidationError({"bed_id": "Choose the new bed."})
            attrs["bed"] = StayTermsSerializer(context=self.context).validate_bed_id(attrs["bed_id"])
        if action == "notice" and "leave_date" not in attrs:
            raise serializers.ValidationError({"leave_date": "Choose the leaving date."})
        if action == "move_in":
            terms = StayTermsSerializer(data=self.initial_data, context=self.context)
            terms.is_valid(raise_exception=True)
            attrs["terms"] = terms.validated_data
        return attrs


class CheckoutPreviewQuerySerializer(TenantDetailQuerySerializer):
    leave_date = serializers.DateField(required=False)
    prorate_last_bill = serializers.BooleanField(required=False, default=False)


# ---------------------------------------------------------------------------------------------------------------
# Bills, payments, deposits


class PgBillItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PgBillItem
        fields = ["id", "item_type", "description", "amount"]


class PgBillSerializer(serializers.ModelSerializer):
    items = PgBillItemSerializer(many=True, read_only=True)
    payments = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = PgBill
        fields = ["id", "period_start", "period_end", "due_date", "total", "discount", "paid", "balance", "status",
                  "is_overdue", "items", "payments"]

    def get_payments(self, bill):
        return PaymentSerializer([p for p in bill.payments.all() if p.is_active], many=True).data

    def get_balance(self, bill):
        return _money(bill.balance) if bill.status != PgBill.VOID else "0.00"

    def get_is_overdue(self, bill):
        return bill.status in (PgBill.UNPAID, PgBill.PARTIAL) and bill.due_date < timezone.localdate()


class BillDetailQuerySerializer(BusinessAccountQuerySerializer):
    bill_id = serializers.IntegerField()


class BillDiscountSerializer(serializers.Serializer):
    discount = serializers.DecimalField(**MONEY, min_value=0)


class TenantRefSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()

    def validate_member_id(self, value):
        tenancy = (
            PgTenancy.objects.select_related("member", "bed__room")
            .filter(member_id=value, business_account_id=self.context["business_account_id"])
            .order_by("-start_date", "-id")
            .first()
        )
        if tenancy is None:
            raise serializers.ValidationError("Tenant not found.")
        return tenancy


class ChargeCreateSerializer(TenantRefSerializer, ChargeSerializer):
    pass


class RentPaymentCreateSerializer(TenantRefSerializer):
    bill_id = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    payment_date = serializers.DateTimeField(required=False)
    payment_method = serializers.ChoiceField(choices=PAYMENT_METHODS)
    transaction_reference = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        tenancy = attrs["member_id"]
        if attrs.get("bill_id"):
            bill = tenancy.bills.filter(id=attrs["bill_id"]).exclude(status=PgBill.VOID).first()
            if bill is None:
                raise serializers.ValidationError({"bill_id": "Bill not found."})
            attrs["bill"] = bill
        attrs.pop("bill_id", None)
        return attrs


class DepositEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PgDepositEntry
        fields = ["id", "entry_type", "amount", "entry_date", "payment_method", "reason", "created_at"]


class DepositCreateSerializer(TenantRefSerializer):
    entry_type = serializers.ChoiceField(choices=[PgDepositEntry.COLLECT, PgDepositEntry.REFUND, PgDepositEntry.DEDUCT])
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    entry_date = serializers.DateField(required=False)
    payment_method = serializers.ChoiceField(choices=PAYMENT_METHODS, required=False)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["entry_type"] == PgDepositEntry.DEDUCT and not attrs.get("reason"):
            raise serializers.ValidationError({"reason": "Say why the money is kept."})
        return attrs
