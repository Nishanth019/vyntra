from django.urls import path

from . import views

urlpatterns = [
    path("auth/signup/", views.SignupView.as_view(), name="auth-signup"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("business-types/", views.BusinessTypeListView.as_view(), name="business-type-list"),
    path("duration-types/", views.DurationTypeListView.as_view(), name="duration-type-list"),
    path("business-accounts/", views.BusinessAccountListView.as_view(), name="business-account-list"),
    path("business-accounts/<int:id>/", views.BusinessAccountDetailView.as_view(), name="business-account-detail"),
    path("members/", views.MemberView.as_view(), name="members"),
    path("staff/", views.StaffView.as_view(), name="staff"),
    path("membership-plans/", views.MembershipPlanView.as_view(), name="membership-plans"),
    path("member-attendance/", views.MemberAttendanceView.as_view(), name="member-attendance"),
    path("admins/", views.AdminView.as_view(), name="admins"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/password/", views.ChangePasswordView.as_view(), name="me-password"),
]
