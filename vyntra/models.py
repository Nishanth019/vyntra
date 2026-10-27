from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BusinessType(TimeStampedModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "business_type"

    def __str__(self):
        return self.name


class BusinessAccount(TimeStampedModel):
    business_type = models.ForeignKey(
        BusinessType,
        on_delete=models.PROTECT,
        db_column="business_type_id",
        related_name="business_accounts",
    )

    name = models.CharField(max_length=200)
    logo_url = models.CharField(max_length=500, null=True, blank=True)

    address = models.CharField(max_length=500, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    address_lat = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    address_lng = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)

    contact_no = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    website = models.CharField(max_length=500, null=True, blank=True)

    terms_and_conditions = models.CharField(max_length=10000, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "business_account"

    def __str__(self):
        return self.name


class BusinessAdmin(TimeStampedModel):
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=255, unique=True)
    phone = models.CharField(max_length=20, null=True, blank=True)

    password = models.CharField(max_length=255)

    is_active = models.BooleanField(default=True)

    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "business_admin"

    def __str__(self):
        return self.name

    # Lets DRF treat an admin as request.user (e.g. for IsAuthenticated).
    @property
    def is_authenticated(self):
        return True


class BusinessAccountAdmin(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="account_admins",
    )
    business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="business_admin_id",
        related_name="account_admins",
    )

    role = models.CharField(max_length=30, default="ADMIN")

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "business_account_admin"
        constraints = [
            models.UniqueConstraint(
                fields=["business_account", "business_admin"],
                name="uk_business_account_admin",
            ),
        ]


class Member(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="members",
    )

    member_code = models.CharField(max_length=100)

    created_by_business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="created_by_business_admin_id",
        related_name="created_members",
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, null=True, blank=True)

    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)

    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "member"
        constraints = [
            models.UniqueConstraint(
                fields=["business_account", "member_code"],
                name="uk_member_account_code",
            ),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name or ''}".strip()


class GymMember(TimeStampedModel):
    member = models.OneToOneField(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="gym_details",
    )

    emergency_contact_name = models.CharField(max_length=200, null=True, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, null=True, blank=True)
    emergency_contact_address = models.CharField(max_length=500, null=True, blank=True)

    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    fitness_goal = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "gym_member"


class Staff(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="staff",
    )

    employee_code = models.CharField(max_length=100)

    created_by_business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="created_by_business_admin_id",
        related_name="created_staff",
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, null=True, blank=True)

    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)

    role = models.CharField(max_length=100, null=True, blank=True)

    # Monthly salary; used by Staff → Salaries.
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    joining_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "staff"
        verbose_name_plural = "staff"
        constraints = [
            models.UniqueConstraint(
                fields=["business_account", "employee_code"],
                name="uk_staff_account_code",
            ),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name or ''}".strip()


class DurationType(TimeStampedModel):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, unique=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "duration_type"

    def __str__(self):
        return self.name


class MembershipPlan(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="membership_plans",
    )

    name = models.CharField(max_length=200)

    duration_type = models.ForeignKey(
        DurationType,
        on_delete=models.PROTECT,
        db_column="duration_type_id",
        related_name="membership_plans",
    )
    duration_value = models.IntegerField()

    amount = models.DecimalField(max_digits=12, decimal_places=2)

    description = models.CharField(max_length=1000, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "membership_plan"

    def __str__(self):
        return self.name


class Membership(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="memberships",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="memberships",
    )
    membership_plan = models.ForeignKey(
        MembershipPlan,
        on_delete=models.PROTECT,
        db_column="membership_plan_id",
        related_name="memberships",
    )

    start_date = models.DateField()
    end_date = models.DateField()

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "membership"


class Payment(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="payments",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="payments",
    )
    membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        db_column="membership_id",
        related_name="payments",
        null=True,
        blank=True,
    )
    # PG rent payments are made against a bill (NULL for gym payments and PG advance).
    pg_bill = models.ForeignKey(
        "PgBill",
        on_delete=models.PROTECT,
        db_column="pg_bill_id",
        related_name="payments",
        null=True,
        blank=True,
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)

    payment_date = models.DateTimeField()

    payment_method = models.CharField(max_length=30)

    transaction_reference = models.CharField(max_length=255, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    notes = models.CharField(max_length=1000, null=True, blank=True)

    created_by_business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="created_by_business_admin_id",
        related_name="created_payments",
    )

    class Meta:
        managed = False
        db_table = "payment"


class MemberAttendance(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="member_attendances",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="attendances",
    )

    attendance_date = models.DateField()

    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)

    marked_by_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="marked_by_admin_id",
        related_name="marked_attendances",
    )

    class Meta:
        managed = False
        db_table = "member_attendance"
        verbose_name_plural = "member attendance"
        constraints = [
            models.UniqueConstraint(
                fields=["member", "attendance_date"],
                name="uk_member_attendance_day",
            ),
        ]


class MemberActivity(TimeStampedModel):
    """One line of a member's history: joined, renewed, plan changed, paid, deactivated…"""

    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="member_activities",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="activities",
    )
    membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        db_column="membership_id",
        related_name="activities",
        null=True,
        blank=True,
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        db_column="payment_id",
        related_name="activities",
        null=True,
        blank=True,
    )

    activity_type = models.CharField(max_length=30)
    description = models.CharField(max_length=1000)

    # Null when the system did it (e.g. auto-inactive after expiry).
    created_by_business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="created_by_business_admin_id",
        related_name="member_activities",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "member_activity"
        verbose_name_plural = "member activity"


class BusinessAdminDevice(TimeStampedModel):
    """An admin's phone, registered for push notifications."""

    business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="business_admin_id",
        related_name="devices",
    )

    push_token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "business_admin_device"


class Notification(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="notifications",
    )
    business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="business_admin_id",
        related_name="notifications",
    )

    notification_type = models.CharField(max_length=30)
    title = models.CharField(max_length=200)
    message = models.CharField(max_length=1000)

    # What to open on tap: a member list filter, or one member.
    member_filter = models.CharField(max_length=30, null=True, blank=True)
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="notifications",
        null=True,
        blank=True,
    )

    # India date the notification is for; daily notifications are sent once per date.
    notification_date = models.DateField()

    is_read = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = "notification"


class NotificationSetting(TimeStampedModel):
    business_account = models.OneToOneField(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="notification_setting",
    )

    morning_summary = models.BooleanField(default=True)
    expiry_reminders = models.BooleanField(default=True)
    expired_followups = models.BooleanField(default=True)
    dues_reminders = models.BooleanField(default=True)
    no_show_alerts = models.BooleanField(default=True)
    birthday_alerts = models.BooleanField(default=True)
    activity_alerts = models.BooleanField(default=True)
    evening_summary = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "notification_setting"


class SubscriptionPlan(TimeStampedModel):
    """What Manaze sells: Monthly / Quarterly / Yearly access for one login and the businesses it owns."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    months = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")

    razorpay_plan_id = models.CharField(max_length=100, null=True, blank=True)
    google_base_plan_id = models.CharField(max_length=100, null=True, blank=True)

    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "subscription_plan"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class Subscription(TimeStampedModel):
    """One login's free trial and paid plan. Every business that login owns follows it."""

    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    STATUS_CHOICES = [(TRIAL, "Trial"), (ACTIVE, "Active"), (CANCELLED, "Cancelled"), (EXPIRED, "Expired")]

    RAZORPAY = "RAZORPAY"
    GOOGLE_PLAY = "GOOGLE_PLAY"
    APPLE = "APPLE"
    MANUAL = "MANUAL"
    PROVIDER_CHOICES = [(RAZORPAY, "Razorpay"), (GOOGLE_PLAY, "Google Play"), (APPLE, "Apple"), (MANUAL, "Manual")]

    business_admin = models.OneToOneField(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="business_admin_id",
        related_name="subscription",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        db_column="subscription_plan_id",
        related_name="subscriptions",
        null=True,
        blank=True,
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=TRIAL)
    trial_ends_at = models.DateTimeField()
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, null=True, blank=True)
    provider_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "subscription"

    def __str__(self):
        return f"{self.business_admin} · {self.get_status_display()}"


class SubscriptionPayment(TimeStampedModel):
    """Every charge (first payment and each renewal) from any provider."""

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        db_column="subscription_id",
        related_name="payments",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        db_column="subscription_plan_id",
        related_name="payments",
        null=True,
        blank=True,
    )

    provider = models.CharField(max_length=20, choices=Subscription.PROVIDER_CHOICES)
    provider_payment_id = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=20, default="PAID")

    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField()
    raw_response = models.JSONField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "subscription_payment"
        ordering = ["-paid_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_payment_id"],
                name="uk_subscription_payment_provider_ref",
            ),
        ]


class Expense(TimeStampedModel):
    """Money the business spends (rent, electricity, salaries, repairs…), for gyms and PGs alike."""

    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="expenses",
    )

    category = models.CharField(max_length=30)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField()
    description = models.CharField(max_length=255)
    vendor = models.CharField(max_length=200, null=True, blank=True)
    payment_method = models.CharField(max_length=30, null=True, blank=True)
    notes = models.CharField(max_length=1000, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_by_business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="created_by_business_admin_id",
        related_name="created_expenses",
    )

    class Meta:
        managed = False
        db_table = "expense"


class StaffSalary(TimeStampedModel):
    """A staff member's salary paid for one month; paying it creates one SALARY expense."""

    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="staff_salaries",
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.PROTECT,
        db_column="staff_id",
        related_name="salaries",
    )

    salary_month = models.DateField()  # first day of the month
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=30, null=True, blank=True)

    expense = models.ForeignKey(
        Expense,
        on_delete=models.PROTECT,
        db_column="expense_id",
        related_name="staff_salaries",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "staff_salary"
        verbose_name_plural = "staff salaries"
        constraints = [
            models.UniqueConstraint(fields=["staff", "salary_month"], name="uk_staff_salary_month"),
        ]


class PgProperty(TimeStampedModel):
    """Settings of a PG business account (one row per PG)."""

    business_account = models.OneToOneField(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="pg_property",
    )

    property_type = models.CharField(max_length=20, default="PG")
    gender = models.CharField(max_length=10, default="COED")
    facilities = models.JSONField(null=True, blank=True)
    default_due_day = models.PositiveSmallIntegerField(default=1)
    prorate_first_bill = models.BooleanField(default=True)
    notice_period_days = models.PositiveIntegerField(default=30)
    eb_unit_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    upi_id = models.CharField(max_length=100, null=True, blank=True)
    house_rules = models.CharField(max_length=5000, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "pg_property"
        verbose_name_plural = "PG properties"


class PgRoom(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="pg_rooms",
    )

    room_number = models.CharField(max_length=30)
    floor = models.CharField(max_length=30, null=True, blank=True)
    is_ac = models.BooleanField(default=False)
    rent_per_bed = models.DecimalField(max_digits=12, decimal_places=2)
    amenities = models.JSONField(null=True, blank=True)
    notes = models.CharField(max_length=500, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "pg_room"
        constraints = [
            models.UniqueConstraint(fields=["business_account", "room_number"], name="uk_pg_room_number"),
        ]

    def __str__(self):
        return f"Room {self.room_number}"


class PgBed(TimeStampedModel):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="pg_beds",
    )
    room = models.ForeignKey(
        PgRoom,
        on_delete=models.PROTECT,
        db_column="pg_room_id",
        related_name="beds",
    )

    label = models.CharField(max_length=20)

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "pg_bed"
        constraints = [
            models.UniqueConstraint(fields=["room", "label"], name="uk_pg_bed_label"),
        ]

    def __str__(self):
        return f"Room {self.room.room_number} · Bed {self.label}"


class PgTenant(TimeStampedModel):
    """PG-only details of a tenant (a `member` of a PG business), like GymMember for gyms."""

    member = models.OneToOneField(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="pg_details",
    )

    occupation = models.CharField(max_length=200, null=True, blank=True)
    permanent_address = models.CharField(max_length=500, null=True, blank=True)
    id_type = models.CharField(max_length=20, null=True, blank=True)
    id_last4 = models.CharField(max_length=4, null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=200, null=True, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, null=True, blank=True)
    emergency_contact_relation = models.CharField(max_length=50, null=True, blank=True)
    vehicle_number = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "pg_tenant"


class PgTenancy(TimeStampedModel):
    """A tenant's stay on a bed: rent, due day and dates. The PG version of a membership."""

    ACTIVE = "ACTIVE"
    NOTICE = "NOTICE"
    ENDED = "ENDED"
    LIVING = (ACTIVE, NOTICE)  # occupying a bed

    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="pg_tenancies",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="pg_tenancies",
    )
    bed = models.ForeignKey(
        PgBed,
        on_delete=models.PROTECT,
        db_column="pg_bed_id",
        related_name="tenancies",
    )

    rent = models.DecimalField(max_digits=12, decimal_places=2)
    billing_cycle_months = models.PositiveSmallIntegerField(default=1)
    due_day = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    status = models.CharField(max_length=10, default=ACTIVE)
    notice_date = models.DateField(null=True, blank=True)
    expected_end_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    leave_reason = models.CharField(max_length=500, null=True, blank=True)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    advance_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_by_business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="created_by_business_admin_id",
        related_name="created_pg_tenancies",
    )

    class Meta:
        managed = False
        db_table = "pg_tenancy"
        verbose_name_plural = "PG tenancies"


class PgBill(TimeStampedModel):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    VOID = "VOID"

    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="pg_bills",
    )
    tenancy = models.ForeignKey(
        PgTenancy,
        on_delete=models.PROTECT,
        db_column="pg_tenancy_id",
        related_name="bills",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        db_column="member_id",
        related_name="pg_bills",
    )

    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=10, default=UNPAID)

    class Meta:
        managed = False
        db_table = "pg_bill"
        constraints = [
            models.UniqueConstraint(fields=["tenancy", "period_start"], name="uk_pg_bill_period"),
        ]

    @property
    def balance(self):
        return self.total - self.discount - self.paid


class PgBillItem(models.Model):
    RENT = "RENT"
    CHARGE = "CHARGE"
    ADJUSTMENT = "ADJUSTMENT"

    bill = models.ForeignKey(
        PgBill,
        on_delete=models.CASCADE,
        db_column="pg_bill_id",
        related_name="items",
    )

    item_type = models.CharField(max_length=20)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "pg_bill_item"


class PgDepositEntry(models.Model):
    COLLECT = "COLLECT"
    REFUND = "REFUND"
    DEDUCT = "DEDUCT"

    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.PROTECT,
        db_column="business_account_id",
        related_name="pg_deposit_entries",
    )
    tenancy = models.ForeignKey(
        PgTenancy,
        on_delete=models.PROTECT,
        db_column="pg_tenancy_id",
        related_name="deposit_entries",
    )

    entry_type = models.CharField(max_length=10)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    entry_date = models.DateField()
    payment_method = models.CharField(max_length=30, null=True, blank=True)
    reason = models.CharField(max_length=500, null=True, blank=True)

    created_by_business_admin = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.PROTECT,
        db_column="created_by_business_admin_id",
        related_name="created_pg_deposit_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "pg_deposit_entry"
        verbose_name_plural = "PG deposit entries"
