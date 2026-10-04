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

    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "staff"
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
        constraints = [
            models.UniqueConstraint(
                fields=["member", "attendance_date"],
                name="uk_member_attendance_day",
            ),
        ]
