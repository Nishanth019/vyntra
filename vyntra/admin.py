"""
Django admin for the platform owner: browse and correct every table. The app's own rules (dues,
plan changes, notifications) live in services.py, so changes made here skip them — use with care.
"""

from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    WhatsAppMessage,
    WhatsAppSetting,
    BusinessAccount,
    BusinessAccountAdmin,
    BusinessAdmin,
    BusinessAdminDevice,
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
    Subscription,
    SubscriptionPayment,
    SubscriptionPlan,
)
from .billing import ProviderError, Razorpay
from .subscriptions import SubscriptionService

admin.site.site_header = "Vyntra Admin"
admin.site.site_title = "Vyntra Admin"
admin.site.index_title = "All tables"


class BaseAdmin(admin.ModelAdmin):
    list_per_page = 50
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-id",)


# --- Businesses and their admins ---------------------------------------------------------------


@admin.register(BusinessType)
class BusinessTypeAdmin(BaseAdmin):
    list_display = ("id", "name", "code", "is_active", "created_at")
    search_fields = ("name", "code")


class AccountAdminInline(admin.TabularInline):
    model = BusinessAccountAdmin
    extra = 0
    fields = ("business_admin", "role", "is_active", "created_at")
    readonly_fields = ("created_at",)
    raw_id_fields = ("business_admin",)


@admin.register(BusinessAccount)
class BusinessAccountAdminPage(BaseAdmin):
    list_display = ("id", "name", "business_type", "city", "contact_no", "members", "active_members", "plans", "is_active", "created_at")
    list_filter = ("is_active", "business_type", "city")
    search_fields = ("name", "city", "contact_no", "email")
    inlines = (AccountAdminInline,)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("business_type")
            .annotate(
                member_count=Count("members", distinct=True),
                active_member_count=Count("members", filter=Q(members__is_active=True), distinct=True),
                plan_count=Count("membership_plans", distinct=True),
            )
        )

    @admin.display(description="Members", ordering="member_count")
    def members(self, obj):
        return obj.member_count

    @admin.display(description="Active members", ordering="active_member_count")
    def active_members(self, obj):
        return obj.active_member_count

    @admin.display(description="Plans", ordering="plan_count")
    def plans(self, obj):
        return obj.plan_count


@admin.register(BusinessAdmin)
class BusinessAdminPage(BaseAdmin):
    list_display = ("id", "name", "email", "phone", "is_active", "last_login_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "email", "phone")
    # The password is a hash; it's changed from the app.
    exclude = ("password",)
    readonly_fields = BaseAdmin.readonly_fields + ("last_login_at",)


@admin.register(BusinessAccountAdmin)
class BusinessAccountAdminLink(BaseAdmin):
    list_display = ("id", "business_account", "business_admin", "role", "is_active", "created_at")
    list_filter = ("is_active", "role")
    search_fields = ("business_account__name", "business_admin__name", "business_admin__email")
    list_select_related = ("business_account", "business_admin")
    raw_id_fields = ("business_account", "business_admin")


# --- Plans, members and memberships ------------------------------------------------------------


@admin.register(DurationType)
class DurationTypeAdmin(BaseAdmin):
    list_display = ("id", "name", "code", "is_active")


@admin.register(MembershipPlan)
class MembershipPlanAdmin(BaseAdmin):
    list_display = ("id", "name", "business_account", "duration_value", "duration_type", "amount", "is_active", "created_at")
    list_filter = ("is_active", "duration_type", "business_account")
    search_fields = ("name", "business_account__name")
    list_select_related = ("business_account", "duration_type")
    raw_id_fields = ("business_account",)


class GymDetailsInline(admin.StackedInline):
    model = GymMember
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ("membership_plan", "start_date", "end_date", "amount", "discount", "is_active")
    raw_id_fields = ("membership_plan",)
    show_change_link = True


@admin.register(Member)
class MemberAdmin(BaseAdmin):
    list_display = ("id", "member_code", "first_name", "last_name", "phone", "business_account", "is_active", "created_at")
    list_filter = ("is_active", "gender", "business_account")
    search_fields = ("member_code", "first_name", "last_name", "phone", "email")
    list_select_related = ("business_account",)
    raw_id_fields = ("business_account", "created_by_business_admin")
    date_hierarchy = "created_at"
    inlines = (GymDetailsInline, MembershipInline)


@admin.register(GymMember)
class GymMemberAdmin(BaseAdmin):
    list_display = ("id", "member", "emergency_contact_name", "emergency_contact_phone")
    search_fields = ("member__first_name", "member__last_name", "emergency_contact_name", "emergency_contact_phone")
    raw_id_fields = ("member",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("amount", "payment_date", "payment_method", "transaction_reference", "is_active")
    show_change_link = True


@admin.register(Membership)
class MembershipAdmin(BaseAdmin):
    list_display = ("id", "member", "membership_plan", "start_date", "end_date", "amount", "discount", "is_active", "business_account")
    list_filter = ("is_active", "business_account", "membership_plan")
    search_fields = ("member__first_name", "member__last_name", "member__member_code", "membership_plan__name")
    list_select_related = ("member", "membership_plan", "business_account")
    raw_id_fields = ("business_account", "member", "membership_plan")
    date_hierarchy = "start_date"
    inlines = (PaymentInline,)


@admin.register(Payment)
class PaymentAdmin(BaseAdmin):
    list_display = ("id", "member", "amount", "payment_method", "payment_date", "membership", "is_active", "business_account")
    list_filter = ("is_active", "payment_method", "business_account")
    search_fields = ("member__first_name", "member__last_name", "member__member_code", "transaction_reference")
    list_select_related = ("member", "membership__membership_plan", "business_account")
    raw_id_fields = ("business_account", "member", "membership", "created_by_business_admin")
    date_hierarchy = "payment_date"


@admin.register(MemberAttendance)
class MemberAttendanceAdmin(BaseAdmin):
    list_display = ("id", "member", "attendance_date", "check_in_time", "check_out_time", "business_account")
    list_filter = ("business_account",)
    search_fields = ("member__first_name", "member__last_name", "member__member_code")
    list_select_related = ("member", "business_account")
    raw_id_fields = ("business_account", "member", "marked_by_admin")
    date_hierarchy = "attendance_date"


@admin.register(MemberActivity)
class MemberActivityAdmin(BaseAdmin):
    list_display = ("id", "member", "activity_type", "description", "created_by_business_admin", "created_at")
    list_filter = ("activity_type", "business_account")
    search_fields = ("member__first_name", "member__last_name", "description")
    list_select_related = ("member", "created_by_business_admin")
    raw_id_fields = ("business_account", "member", "membership", "payment", "created_by_business_admin")
    date_hierarchy = "created_at"


@admin.register(Staff)
class StaffAdmin(BaseAdmin):
    list_display = ("id", "employee_code", "first_name", "last_name", "role", "phone", "business_account", "is_active")
    list_filter = ("is_active", "role", "business_account")
    search_fields = ("employee_code", "first_name", "last_name", "phone", "email")
    list_select_related = ("business_account",)
    raw_id_fields = ("business_account", "created_by_business_admin")


# --- Notifications -----------------------------------------------------------------------------


@admin.register(Notification)
class NotificationAdmin(BaseAdmin):
    list_display = ("id", "title", "notification_type", "business_account", "business_admin", "notification_date", "is_read")
    list_filter = ("notification_type", "is_read", "business_account")
    search_fields = ("title", "message")
    list_select_related = ("business_account", "business_admin")
    raw_id_fields = ("business_account", "business_admin", "member")
    date_hierarchy = "notification_date"


@admin.register(NotificationSetting)
class NotificationSettingAdmin(BaseAdmin):
    list_display = ("id", "business_account", "morning_summary", "expiry_reminders", "dues_reminders", "evening_summary")
    raw_id_fields = ("business_account",)


@admin.register(BusinessAdminDevice)
class BusinessAdminDeviceAdmin(BaseAdmin):
    list_display = ("id", "business_admin", "platform", "is_active", "updated_at")
    list_filter = ("platform", "is_active")
    search_fields = ("business_admin__name", "business_admin__email")
    raw_id_fields = ("business_admin",)
    # Push tokens are credentials for sending notifications to that phone.
    exclude = ("push_token",)


# --- Vyntra subscriptions ----------------------------------------------------------------------


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(BaseAdmin):
    list_display = ("id", "name", "code", "months", "price", "razorpay_plan_id", "google_base_plan_id", "is_active")
    list_editable = ("price", "is_active")
    ordering = ("sort_order", "id")
    actions = ("create_razorpay_plans",)

    # Razorpay plans can't be edited, so a new price needs a new Razorpay plan. Existing subscribers stay on their
    # old plan and price; new subscribers get the new one.
    BILLING_FIELDS = ("price", "months", "currency")

    def save_model(self, request, obj, form, change):
        before = SubscriptionPlan.objects.filter(pk=obj.pk).first() if change else None
        billing_changed = before is None or any(
            getattr(before, field) != getattr(obj, field) for field in self.BILLING_FIELDS
        )
        if billing_changed and Razorpay.is_configured():
            try:
                obj.razorpay_plan_id = Razorpay.create_plan(obj)
                self.message_user(request, f"{obj.name}: new Razorpay plan {obj.razorpay_plan_id} at {obj.price}.")
            except ProviderError as error:
                # Never leave the old Razorpay plan linked: it would charge the old price.
                obj.razorpay_plan_id = None
                self.message_user(
                    request,
                    f"{obj.name}: saved, but Razorpay refused the new plan ({error}). Online payment for this plan "
                    "is off until you run “Create the selected plans in Razorpay”.",
                    messages.ERROR,
                )
        super().save_model(request, obj, form, change)

    @admin.action(description="Create the selected plans in Razorpay (needs Razorpay keys)")
    def create_razorpay_plans(self, request, queryset):
        if not Razorpay.is_configured():
            self.message_user(request, "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET first.", messages.ERROR)
            return
        for plan in queryset:
            if plan.razorpay_plan_id:
                self.message_user(request, f"{plan.name} already has {plan.razorpay_plan_id}.", messages.INFO)
                continue
            try:
                plan.razorpay_plan_id = Razorpay.create_plan(plan)
            except ProviderError as error:
                self.message_user(request, f"{plan.name}: Razorpay refused it ({error}).", messages.ERROR)
                continue
            plan.save()
            self.message_user(request, f"{plan.name} → {plan.razorpay_plan_id}")


class SubscriptionPaymentInline(admin.TabularInline):
    model = SubscriptionPayment
    extra = 0
    fields = ("paid_at", "provider", "provider_payment_id", "plan", "amount", "status", "period_end")
    readonly_fields = fields
    can_delete = False


class AccessFilter(admin.SimpleListFilter):
    title = "access"
    parameter_name = "access"

    def lookups(self, request, model_admin):
        return [("trial", "In free trial"), ("paid", "Paid plan running"), ("week", "Ending within 7 days"),
                ("ended", "Ended (read-only)")]

    def queryset(self, request, queryset):
        now = timezone.now()
        running = Q(trial_ends_at__gt=now) | Q(current_period_end__gt=now)
        if self.value() == "trial":
            return queryset.filter(trial_ends_at__gt=now).exclude(current_period_end__gt=now)
        if self.value() == "paid":
            return queryset.filter(current_period_end__gt=now)
        if self.value() == "week":
            soon = now + timedelta(days=7)
            return queryset.filter(running).exclude(trial_ends_at__gt=soon).exclude(current_period_end__gt=soon)
        if self.value() == "ended":
            return queryset.exclude(running)
        return queryset


@admin.register(Subscription)
class SubscriptionAdmin(BaseAdmin):
    list_display = ("id", "business_admin", "state", "plan", "trial_ends_at", "current_period_end", "provider",
                    "auto_renew")
    list_filter = (AccessFilter, "status", "provider", "plan", "auto_renew")
    search_fields = ("business_admin__name", "business_admin__email", "business_admin__phone",
                     "provider_subscription_id")
    list_select_related = ("business_admin", "plan")
    raw_id_fields = ("business_admin",)
    readonly_fields = ("state", "access_until", "created_at", "updated_at")
    inlines = [SubscriptionPaymentInline]
    actions = ("give_7_days", "give_15_days", "give_30_days")

    @admin.display(description="State")
    def state(self, subscription):
        return SubscriptionService.state(subscription)

    @admin.display(description="Access until")
    def access_until(self, subscription):
        return SubscriptionService.access_until(subscription)

    def _give(self, request, queryset, days):
        for subscription in queryset:
            SubscriptionService.extend(subscription, days)
        self.message_user(request, f"Gave {days} free days to {queryset.count()} login(s).")

    @admin.action(description="Give 7 free days")
    def give_7_days(self, request, queryset):
        self._give(request, queryset, 7)

    @admin.action(description="Give 15 free days")
    def give_15_days(self, request, queryset):
        self._give(request, queryset, 15)

    @admin.action(description="Give 30 free days")
    def give_30_days(self, request, queryset):
        self._give(request, queryset, 30)


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(BaseAdmin):
    list_display = ("id", "subscription", "provider", "plan", "amount", "status", "paid_at", "period_end")
    list_filter = ("provider", "status", "plan")
    search_fields = ("provider_payment_id", "subscription__business_admin__name",
                     "subscription__business_admin__email")
    list_select_related = ("subscription__business_admin", "plan")
    raw_id_fields = ("subscription",)
    date_hierarchy = "paid_at"


# --- WhatsApp to members ------------------------------------------------------------------------


@admin.register(WhatsAppSetting)
class WhatsAppSettingAdmin(BaseAdmin):
    list_display = ("id", "business_account", "enabled", "expiry_reminders", "expired_followups", "dues_reminders",
                    "payment_receipts", "birthday_wishes")
    list_filter = ("enabled",)
    raw_id_fields = ("business_account",)


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(BaseAdmin):
    list_display = ("id", "sent_date", "business_account", "member", "message_type", "phone", "status")
    list_filter = ("status", "message_type", "sent_date")
    search_fields = ("phone", "member__first_name", "business_account__name")
    raw_id_fields = ("business_account", "member")
