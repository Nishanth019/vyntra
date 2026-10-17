"""
Django admin for the platform owner: browse and correct every table. The app's own rules (dues,
plan changes, notifications) live in services.py, so changes made here skip them — use with care.
"""

from django.contrib import admin
from django.db.models import Count, Q

from .models import (
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
)

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
