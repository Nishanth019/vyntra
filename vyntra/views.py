import hmac
import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    Payment,
    Staff,
    Subscription,
)
from .billing import GooglePlay, GooglePlayBilling, ProviderError, Razorpay, RazorpayBilling
from .serializers import (
    AdminDetailQuerySerializer,
    BusinessAccountAdminSerializer,
    BusinessAccountSerializer,
    BusinessAccountUpdateSerializer,
    BusinessAdminSerializer,
    BusinessAdminUpdateSerializer,
    ChangePasswordSerializer,
    BusinessTypeSerializer,
    DurationTypeSerializer,
    BusinessAccountQuerySerializer,
    CollectionsQuerySerializer,
    DeviceSerializer,
    InsightsQuerySerializer,
    LoginSerializer,
    MemberActivitySerializer,
    MemberAttendanceDetailQuerySerializer,
    MemberAttendanceListQuerySerializer,
    MemberAttendanceSerializer,
    MemberAttendanceUpdateSerializer,
    MemberDetailQuerySerializer,
    MemberListQuerySerializer,
    MemberSerializer,
    MembershipActionSerializer,
    MembershipDetailQuerySerializer,
    MembershipListQuerySerializer,
    MembershipPlanDetailQuerySerializer,
    MembershipPlanSerializer,
    MembershipSerializer,
    MembershipUpdateSerializer,
    NotificationReadSerializer,
    NotificationSerializer,
    NotificationSettingSerializer,
    PaymentCreateSerializer,
    PaymentDetailQuerySerializer,
    PaymentDetailSerializer,
    PaymentListQuerySerializer,
    SignupSerializer,
    StaffDetailQuerySerializer,
    StaffListQuerySerializer,
    StaffSerializer,
    GooglePlayConfirmSerializer,
    PlanChoiceSerializer,
    RazorpayConfirmSerializer,
    RazorpaySyncSerializer,
    SubscriptionPaymentSerializer,
    SubscriptionPlanSerializer,
    SubscriptionSummarySerializer,
    normalize_mobile,
)
from .services import (
    ActivityService,
    BusinessAccountService,
    BusinessAdminAuthService,
    InsightsService,
    MemberService,
    MembershipService,
    NotificationService,
    PaymentService,
    rupees,
)
from .subscriptions import OWNER, SubscriptionService, active_plans, hand_over_ownership


def set_access_token_cookie(response, access_token):
    response.set_cookie(
        settings.JWT_COOKIE_NAME,
        access_token,
        max_age=BusinessAdminAuthService.ACCESS_TOKEN_MAX_AGE,
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
    )


class SignupView(APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        admin = BusinessAdmin.objects.create(
            name=data["full_name"],
            phone=data["mobile_no"],
            email=data["email"],
            password=make_password(data["password"]),
        )
        SubscriptionService.for_admin(admin)  # starts the free trial
        access_token = BusinessAdminAuthService.generate_access_token(admin)

        response = Response(
            {"admin": BusinessAdminSerializer(admin).data, "access_token": access_token},
            status=status.HTTP_201_CREATED,
        )
        set_access_token_cookie(response, access_token)
        return response


class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login = serializer.validated_data["login"].strip()
        password = serializer.validated_data["password"]

        # Mobile numbers may be typed with +91, spaces or dashes; they're stored as 10 digits.
        admin = BusinessAdmin.objects.filter(
            Q(email__iexact=login) | Q(phone=login) | Q(phone=normalize_mobile(login))
        ).first()
        if admin is None or not check_password(password, admin.password):
            return Response({"detail": "Invalid login or password."}, status=status.HTTP_401_UNAUTHORIZED)
        if not admin.is_active:
            return Response({"detail": "Account is inactive."}, status=status.HTTP_403_FORBIDDEN)

        admin.last_login_at = timezone.now()
        admin.save()
        access_token = BusinessAdminAuthService.generate_access_token(admin)

        response = Response({"admin": BusinessAdminSerializer(admin).data, "access_token": access_token})
        set_access_token_cookie(response, access_token)
        return response


class LogoutView(APIView):
    def post(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.JWT_COOKIE_NAME, samesite=settings.JWT_COOKIE_SAMESITE)
        return response


class BusinessTypeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business_types = BusinessType.objects.filter(is_active=True)
        return Response({"results": BusinessTypeSerializer(business_types, many=True).data})


class DurationTypeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        duration_types = DurationType.objects.filter(is_active=True)
        return Response({"results": DurationTypeSerializer(duration_types, many=True).data})


class BusinessAccountListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        accounts = BusinessAccountService.get_accounts_for_admin(request.user)
        return Response(
            {"results": BusinessAccountSerializer(accounts, many=True, context={"admin": request.user}).data}
        )

    def post(self, request):
        serializer = BusinessAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        SubscriptionService.check_can_create_business(request.user)

        with transaction.atomic():
            account = BusinessAccount.objects.create(**serializer.validated_data)
            BusinessAccountAdmin.objects.create(
                business_account=account,
                business_admin=request.user,
                role=OWNER,
                is_active=True,
            )

        data = BusinessAccountSerializer(account, context={"admin": request.user}).data
        return Response(data, status=status.HTTP_201_CREATED)


class BusinessAccountDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        account = self.get_account(request, id)
        return Response(BusinessAccountSerializer(account, context={"admin": request.user}).data)

    def put(self, request, id):
        account = self.get_account(request, id)

        serializer = BusinessAccountUpdateSerializer(account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(BusinessAccountSerializer(account, context={"admin": request.user}).data)

    def delete(self, request, id):
        account = self.get_account(request, id)

        account.is_active = False
        account.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_account(self, request, id):
        account = get_object_or_404(BusinessAccountService.get_accounts_for_admin(request.user), id=id)
        BusinessAccountService.check_admin_access(request, account.id)
        return account


class MemberView(APIView):
    permission_classes = [IsAuthenticated]

    # Personal fields whose changes are written to the member's history.
    TRACKED_FIELDS = {
        "member_code": "Member ID", "first_name": "First name", "last_name": "Last name", "phone": "Mobile",
        "email": "Email", "date_of_birth": "Date of birth", "gender": "Gender",
        "emergency_contact_name": "Emergency contact", "emergency_contact_phone": "Emergency mobile",
        "emergency_contact_address": "Address",
    }

    def get(self, request):
        if "member_id" in request.query_params:
            member = self.get_member(request)
            return Response(MemberSerializer(member).data)

        query = MemberListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        members = MemberService.get_members(params["business_account_id"]).order_by("-id")
        if params.get("search"):
            search = params["search"]
            members = members.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
                | Q(member_code__icontains=search)
            )
        if params.get("phone"):
            members = members.filter(phone=params["phone"])
        if params.get("email"):
            members = members.filter(email__iexact=params["email"])
        if params.get("member_code"):
            members = members.filter(member_code=params["member_code"])
        members = MemberService.filter_members(members, params).distinct()

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(members, request, view=self)
        return paginator.get_paginated_response(MemberSerializer(page, many=True).data)

    def post(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        serializer = MemberSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = data.pop("membership_plan_id")
        start_date = data.pop("start_date", timezone.localdate())
        discount = data.pop("discount", Decimal("0"))
        payment = data.pop("payment", None)
        gym_details = self.pop_gym_details(data)

        with transaction.atomic():
            member = Member.objects.create(
                **data,
                business_account_id=business_account_id,
                created_by_business_admin=request.user,
                is_active=True,
            )
            self.upsert_gym_details(member, gym_details)
            membership = MembershipService.create(member, plan, start_date, discount)
            ActivityService.log(
                member, "MEMBER_CREATED", f"Joined: {MembershipService.describe(membership)}", request.user,
                membership=membership,
            )
            if payment:
                PaymentService.create(member, membership, payment, request.user)

        NotificationService.notify_activity(
            business_account_id, request.user, "New member added",
            f"{request.user.name} added {member} on {plan.name}", member,
        )
        member = MemberService.get_members(business_account_id).get(id=member.id)
        return Response(MemberSerializer(member).data, status=status.HTTP_201_CREATED)

    def put(self, request):
        member = self.get_member(request)

        serializer = MemberSerializer(
            member, data=request.data, partial=True, context={"business_account_id": member.business_account_id}
        )
        serializer.is_valid(raise_exception=True)
        # Plan changes now go through /memberships/; kept here for older app versions.
        plan = serializer.validated_data.pop("membership_plan_id", None)
        start_date = serializer.validated_data.pop("start_date", timezone.localdate())
        discount = serializer.validated_data.pop("discount", Decimal("0"))
        payment = serializer.validated_data.pop("payment", None)
        gym_details = self.pop_gym_details(serializer.validated_data)
        changes = self.describe_changes(member, {**serializer.validated_data, **gym_details})
        reactivated = serializer.validated_data.get("is_active") is True and not member.is_active

        with transaction.atomic():
            serializer.save()
            self.upsert_gym_details(member, gym_details)
            if changes:
                ActivityService.log(member, "MEMBER_UPDATED", "Details updated: " + "; ".join(changes), request.user)
            if reactivated:
                ActivityService.log(member, "MEMBER_REACTIVATED", "Reactivated", request.user)
            membership = member.active_memberships[0] if member.active_memberships else None
            if plan and (membership is None or membership.membership_plan_id != plan.id):
                membership = MembershipService.renew(member, plan, start_date, discount, request.user)
            if payment:
                PaymentService.create(member, membership, payment, request.user)

        member = MemberService.get_members(member.business_account_id).get(id=member.id)
        return Response(MemberSerializer(member).data)

    def delete(self, request):
        member = self.get_member(request)

        with transaction.atomic():
            member.is_active = False
            member.save()
            ActivityService.log(member, "MEMBER_DEACTIVATED", "Deactivated", request.user)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_member(self, request):
        query = MemberDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        return get_object_or_404(MemberService.get_members(params["business_account_id"]), id=params["member_id"])

    def describe_changes(self, member, data):
        """e.g. ["Mobile: 98480… → 91214…"] for the tracked fields that actually change."""
        gym = getattr(member, "gym_details", None)
        changes = []
        for field, label in self.TRACKED_FIELDS.items():
            if field not in data:
                continue
            source = gym if field.startswith("emergency_") else member
            old = getattr(source, field, None) if source else None
            new = data[field]
            if (old or None) != (new or None):
                changes.append(f"{label}: {old or '—'} → {new or '—'}")
        return changes

    def pop_gym_details(self, data):
        """Pull the gym_member (emergency contact / address) fields out of member data."""
        keys = ["emergency_contact_name", "emergency_contact_phone", "emergency_contact_address"]
        return {k: data.pop(k) for k in keys if k in data}

    def upsert_gym_details(self, member, gym_details):
        if gym_details:
            GymMember.objects.update_or_create(member=member, defaults=gym_details)


class StaffView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if "staff_id" in request.query_params:
            staff = self.get_staff(request)
            return Response(StaffSerializer(staff).data)

        query = StaffListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        staff = Staff.objects.filter(business_account_id=params["business_account_id"]).order_by("-id")
        if params.get("search"):
            search = params["search"]
            staff = staff.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
                | Q(employee_code__icontains=search)
            )
        if params.get("phone"):
            staff = staff.filter(phone=params["phone"])
        if params.get("employee_code"):
            staff = staff.filter(employee_code=params["employee_code"])
        if params["is_active"] is not None:
            staff = staff.filter(is_active=params["is_active"])

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(staff, request, view=self)
        return paginator.get_paginated_response(StaffSerializer(page, many=True).data)

    def post(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        serializer = StaffSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        staff = serializer.save(
            business_account_id=business_account_id,
            created_by_business_admin=request.user,
            is_active=True,
        )

        return Response(StaffSerializer(staff).data, status=status.HTTP_201_CREATED)

    def put(self, request):
        staff = self.get_staff(request)

        serializer = StaffSerializer(
            staff, data=request.data, partial=True, context={"business_account_id": staff.business_account_id}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    def get_staff(self, request):
        query = StaffDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        return get_object_or_404(Staff, id=params["staff_id"], business_account_id=params["business_account_id"])


class MembershipPlanView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if "plan_id" in request.query_params:
            plan = self.get_plan(request)
            return Response(MembershipPlanSerializer(plan).data)

        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        plans = (
            MembershipPlan.objects.select_related("duration_type")
            .filter(business_account_id=business_account_id)
            .order_by("-id")
        )

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(plans, request, view=self)
        return paginator.get_paginated_response(MembershipPlanSerializer(page, many=True).data)

    def post(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        serializer = MembershipPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save(business_account_id=business_account_id, is_active=True)

        return Response(MembershipPlanSerializer(plan).data, status=status.HTTP_201_CREATED)

    def put(self, request):
        plan = self.get_plan(request)

        serializer = MembershipPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    def get_plan(self, request):
        query = MembershipPlanDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        return get_object_or_404(
            MembershipPlan.objects.select_related("duration_type"),
            id=params["plan_id"],
            business_account_id=params["business_account_id"],
        )


class MemberAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if "attendance_id" in request.query_params:
            attendance = self.get_attendance(request)
            return Response(MemberAttendanceSerializer(attendance).data)

        query = MemberAttendanceListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        attendances = (
            MemberAttendance.objects.select_related("member")
            .filter(business_account_id=params["business_account_id"])
            .order_by("-attendance_date", "-id")
        )
        if params.get("attendance_date"):
            attendances = attendances.filter(attendance_date=params["attendance_date"])
        if params.get("member_id"):
            attendances = attendances.filter(member_id=params["member_id"])

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(attendances, request, view=self)
        return paginator.get_paginated_response(MemberAttendanceSerializer(page, many=True).data)

    def post(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        serializer = MemberAttendanceSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        attendance = MemberAttendance.objects.create(
            business_account_id=business_account_id,
            member=data["member_id"],
            attendance_date=data["attendance_date"],
            check_in_time=data["check_in_time"],
            check_out_time=data.get("check_out_time"),
            marked_by_admin=request.user,
        )

        return Response(MemberAttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)

    def put(self, request):
        attendance = self.get_attendance(request)

        serializer = MemberAttendanceUpdateSerializer(attendance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    def get_attendance(self, request):
        query = MemberAttendanceDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        return get_object_or_404(
            MemberAttendance.objects.select_related("member"),
            id=params["attendance_id"],
            business_account_id=params["business_account_id"],
        )


class PaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if "payment_id" in request.query_params:
            payment = self.get_payment(request)
            return Response(PaymentDetailSerializer(payment).data)

        query = PaymentListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        payments = (
            Payment.objects.select_related("membership")
            .filter(business_account_id=params["business_account_id"], is_active=True)
            .order_by("-payment_date", "-id")
        )
        if params.get("member_id"):
            payments = payments.filter(member_id=params["member_id"])
        if params.get("payment_date_from"):
            payments = payments.filter(payment_date__date__gte=params["payment_date_from"])
        if params.get("payment_date_to"):
            payments = payments.filter(payment_date__date__lte=params["payment_date_to"])

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(payments, request, view=self)
        return paginator.get_paginated_response(PaymentDetailSerializer(page, many=True).data)

    def post(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        serializer = PaymentCreateSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        member = data.pop("member_id")
        membership = data.pop("membership_id", None)
        # Default to the current plan (where dues count); once it's paid up, a waiting future plan.
        if membership is None:
            loaded = MemberService.get_members(business_account_id).get(id=member.id)
            current, next_plan = MemberService.current_and_next(loaded)
            membership = next_plan if next_plan and current and PaymentService.balance(current) <= 0 else current
        with transaction.atomic():
            payment = PaymentService.create(member, membership, data, request.user)

        NotificationService.notify_activity(
            business_account_id, request.user, "Payment recorded",
            f"{request.user.name} recorded {rupees(payment.amount)} from {member}", member,
        )
        return Response(PaymentDetailSerializer(payment).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        payment = self.get_payment(request)
        with transaction.atomic():
            PaymentService.void(payment, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_payment(self, request):
        query = PaymentDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])
        return get_object_or_404(
            Payment.objects.select_related("membership", "member"),
            id=params["payment_id"],
            business_account_id=params["business_account_id"],
        )


class MembershipView(APIView):
    """Membership history (GET), renew / change plan (POST), correct or extend the current one (PUT)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = MembershipListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        memberships = MemberService.get_memberships(params["business_account_id"], params["member_id"])
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(memberships, request, view=self)
        return paginator.get_paginated_response(MembershipSerializer(page, many=True).data)

    def post(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        serializer = MembershipActionSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        member, plan = data["member_id"], data["membership_plan_id"]
        loaded = MemberService.get_members(business_account_id).get(id=member.id)
        current, next_plan = MemberService.current_and_next(loaded)
        error = self.action_error(data, loaded, current, next_plan)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        discount = data.get("discount", Decimal("0"))

        with transaction.atomic():
            if not member.is_active:
                member.is_active = True
                member.save()
                ActivityService.log(member, "MEMBER_REACTIVATED", "Reactivated", request.user)
            if data["action"] == "renew_early":
                start_date = data.get("start_date") or current.end_date + timedelta(days=1)
                membership = MembershipService.renew_early(
                    member, current, plan, start_date, discount, request.user
                )
            elif data["action"] == "renew":
                start_date = data.get("start_date") or timezone.localdate()
                membership = MembershipService.renew(member, plan, start_date, discount, request.user)
            else:
                start_date = data.get("start_date") or timezone.localdate()
                membership = MembershipService.change_plan(
                    member, current, next_plan, plan, start_date, discount, request.user
                )
            if data.get("payment"):
                PaymentService.create(member, membership, data["payment"], request.user)

        member = MemberService.get_members(business_account_id).get(id=member.id)
        return Response(MemberSerializer(member).data, status=status.HTTP_201_CREATED)

    def action_error(self, data, member, current, next_plan):
        """Why a renew / change plan / future plan request isn't allowed for this member, or None."""
        today = timezone.localdate()
        start_date = data.get("start_date")
        running = member.is_live  # a plan covers today (even if the member was deactivated)
        upcoming = current is not None and current.start_date > today

        if data["action"] == "renew":
            if running and member.is_active:
                return "This member already has an active plan. Use Change Plan or Extend instead."
            if running:
                return "This member's plan is still running. Reactivate them instead of renewing."
            if upcoming:
                return f"This member's plan starts {current.start_date:%d %b %Y}. Use Change Plan to replace it."
            return None

        if data["action"] == "change_plan":
            if not member.is_active or current is None or not (running or upcoming):
                return "Change Plan is for members with an active plan. Use Renew instead."
            earliest, latest = min(today, current.start_date), max(today, current.start_date)
            if start_date and not earliest <= start_date <= latest:
                return (
                    f"The new plan must start between {earliest:%d %b %Y} and {latest:%d %b %Y}. "
                    "To add a plan after the current one, use Add Future Plan."
                )
            return None

        # Add Future Plan (renew early).
        if not member.is_active or not running or current is None:
            return "Add Future Plan is for members with an active plan. Use Renew instead."
        if next_plan:
            return f"This member already has a future plan starting {next_plan.start_date:%d %b %Y}."
        if (current.end_date - today).days > MemberService.RENEW_EARLY_DAYS:
            return (
                f"A future plan can be added in the last {MemberService.RENEW_EARLY_DAYS} days of the current "
                f"plan (this one ends {current.end_date:%d %b %Y})."
            )
        if start_date and start_date <= current.end_date:
            return f"The future plan must start after the current one ends ({current.end_date:%d %b %Y})."
        return None

    def delete(self, request):
        """Cancels a member's future plan (its payments are deleted with it)."""
        membership = self.get_membership(request)
        loaded = MemberService.get_members(membership.business_account_id).get(id=membership.member_id)
        current, next_plan = MemberService.current_and_next(loaded)
        if next_plan is None or next_plan.id != membership.id:
            return Response({"detail": "Only a future plan can be cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            MembershipService.cancel_next(loaded, current, next_plan, request.user)
        return Response(MemberSerializer(MemberService.get_members(membership.business_account_id).get(id=loaded.id)).data)

    def get_membership(self, request):
        query = MembershipDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])
        return get_object_or_404(
            Membership.objects.select_related("membership_plan__duration_type", "member"),
            id=params["membership_id"],
            business_account_id=params["business_account_id"],
        )

    def put(self, request):
        query = MembershipDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])
        membership = get_object_or_404(
            Membership.objects.select_related("membership_plan__duration_type", "member"),
            id=params["membership_id"],
            business_account_id=params["business_account_id"],
        )

        serializer = MembershipUpdateSerializer(data=request.data, context={"membership": membership})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # A next plan can't be moved to start before the current one ends.
        if data.get("start_date") and membership.start_date > timezone.localdate():
            running = Membership.objects.filter(
                member_id=membership.member_id,
                start_date__lte=timezone.localdate(),
                end_date__gte=timezone.localdate(),
            ).exclude(id=membership.id).first()
            if running and data["start_date"] <= running.end_date:
                return Response(
                    {"start_date": [f"Must be after the current plan ends ({running.end_date:%d %b %Y})."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            MembershipService.update(
                membership, request.user, start_date=data.get("start_date"), discount=data.get("discount")
            )
            if data.get("extend_days"):
                MembershipService.extend(membership, data["extend_days"], request.user, data.get("reason", ""))

        member = MemberService.get_members(params["business_account_id"]).get(id=membership.member_id)
        return Response(MemberSerializer(member).data)


class MemberActivityView(APIView):
    """A member's full history, newest first."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = MembershipListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        activities = (
            MemberActivity.objects.select_related("created_by_business_admin")
            .filter(business_account_id=params["business_account_id"], member_id=params["member_id"])
            .order_by("-created_at", "-id")
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(activities, request, view=self)
        return paginator.get_paginated_response(MemberActivitySerializer(page, many=True).data)


class DashboardView(APIView):
    """Everything the home screen needs in one request."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        return Response({
            "members": MemberService.get_counts(business_account_id),
            "collections": PaymentService.get_collections_summary(business_account_id),
            "checked_in_today": MemberAttendance.objects.filter(
                business_account_id=business_account_id, attendance_date=timezone.localdate()
            ).count(),
            "plans": MembershipPlan.objects.filter(business_account_id=business_account_id, is_active=True).count(),
            "unread_notifications": Notification.objects.filter(
                business_account_id=business_account_id, business_admin=request.user, is_read=False
            ).count(),
        })


class InsightsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = InsightsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        return Response(
            InsightsService.get_insights(params["business_account_id"], params["date_from"], params["date_to"])
        )


class NotificationView(APIView):
    """The logged-in admin's notifications for a business (GET), mark read (PUT)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        notifications = Notification.objects.filter(
            business_account_id=business_account_id, business_admin=request.user
        ).order_by("-created_at", "-id")
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(notifications, request, view=self)
        return paginator.get_paginated_response(NotificationSerializer(page, many=True).data)

    def put(self, request):
        query = NotificationReadSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"], allow_read_only=True)

        notifications = Notification.objects.filter(
            business_account_id=params["business_account_id"], business_admin=request.user, is_read=False
        )
        if params.get("notification_id"):
            notifications = notifications.filter(id=params["notification_id"])
        notifications.update(is_read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationSettingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        setting = self.get_setting(request)
        return Response(NotificationSettingSerializer(setting).data)

    def put(self, request):
        setting = self.get_setting(request)
        serializer = NotificationSettingSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def get_setting(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id, allow_read_only=True)
        return NotificationService.get_setting(business_account_id)


class DeviceView(APIView):
    """Registers (POST) or removes (DELETE) the admin's phone for push notifications."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # A phone moves to whoever logged in on it last.
        BusinessAdminDevice.objects.update_or_create(
            push_token=data["push_token"],
            defaults={"business_admin": request.user, "platform": data.get("platform") or None, "is_active": True},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        serializer = DeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        BusinessAdminDevice.objects.filter(
            push_token=serializer.validated_data["push_token"], business_admin=request.user
        ).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceTestView(APIView):
    """Sends a test push to the logged-in admin's own phones."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        tokens = list(
            BusinessAdminDevice.objects.filter(business_admin=request.user, is_active=True).values_list(
                "push_token", flat=True
            )
        )
        NotificationService.send_push(
            tokens, "Test notification ✅", "Push notifications are working on this phone.", {}
        )
        return Response({"devices": len(tokens)})


class DailyJobView(APIView):
    """
    Called by the scheduler (GitHub Actions) at 8 AM and 9 PM IST with ?run=morning|evening.
    Safe to call more than once: each business gets each daily notification once per date.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if settings.CRON_SECRET and request.headers.get("X-Cron-Secret") != settings.CRON_SECRET:
            return Response(status=status.HTTP_403_FORBIDDEN)
        run = request.query_params.get("run")
        if run not in ("morning", "evening"):
            return Response({"run": ["Use morning or evening."]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"run": run, "businesses": NotificationService.run_daily(run)})


class CollectionsView(APIView):
    """Collection totals (today / this month / optional period) and outstanding dues."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = CollectionsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        summary = PaymentService.get_collections_summary(
            params["business_account_id"],
            period_from=params.get("period_from"),
            period_to=params.get("period_to"),
        )
        return Response(summary)


class AdminView(APIView):
    """Admins of a business account."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if "admin_id" in request.query_params:
            account_admin = self.get_account_admin(request)
            return Response(BusinessAccountAdminSerializer(account_admin).data)

        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        account_admins = (
            BusinessAccountAdmin.objects.select_related("business_admin")
            .filter(business_account_id=business_account_id)
            .order_by("id")
        )
        return Response({"results": BusinessAccountAdminSerializer(account_admins, many=True).data})

    def post(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request, business_account_id)

        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            admin = BusinessAdmin.objects.create(
                name=data["full_name"],
                phone=data["mobile_no"],
                email=data["email"],
                password=make_password(data["password"]),
            )
            account_admin = BusinessAccountAdmin.objects.create(
                business_account_id=business_account_id,
                business_admin=admin,
                role="ADMIN",
                is_active=True,
            )

        return Response(BusinessAccountAdminSerializer(account_admin).data, status=status.HTTP_201_CREATED)

    def put(self, request):
        account_admin = self.get_account_admin(request)

        serializer = BusinessAdminUpdateSerializer(
            account_admin.business_admin, data=request.data, partial=True, context={"request_admin": request.user}
        )
        serializer.is_valid(raise_exception=True)
        is_active = serializer.validated_data.pop("is_active", None)
        if is_active is False and account_admin.role == OWNER:
            return Response({"detail": "The owner of the business can't be removed."},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            serializer.save()
            if is_active is not None:
                account_admin.is_active = is_active
                account_admin.save()

        return Response(BusinessAccountAdminSerializer(account_admin).data)

    def delete(self, request):
        """Removes an admin from this business. Their login stays, for any other businesses they're part of."""
        account_admin = self.get_account_admin(request)
        if account_admin.role == OWNER:
            return Response({"detail": "The owner of the business can't be removed."},
                            status=status.HTTP_400_BAD_REQUEST)
        if account_admin.business_admin_id == request.user.id:
            return Response({"detail": "You can't remove yourself. Delete your account from My Profile instead."},
                            status=status.HTTP_400_BAD_REQUEST)
        account_admin.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_account_admin(self, request):
        query = AdminDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request, params["business_account_id"])

        return get_object_or_404(
            BusinessAccountAdmin.objects.select_related("business_admin"),
            business_admin_id=params["admin_id"],
            business_account_id=params["business_account_id"],
        )


class MeView(APIView):
    """The logged-in admin's own profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(BusinessAdminSerializer(request.user).data)

    def put(self, request):
        serializer = BusinessAdminUpdateSerializer(
            request.user, data=request.data, partial=True, context={"request_admin": request.user}
        )
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("is_active", None)
        serializer.save()

        return Response(BusinessAdminSerializer(request.user).data)

    def delete(self, request):
        """Deletes the login: the admin can't sign in again and their phones stop getting notifications."""
        with transaction.atomic():
            admin = request.user
            BusinessAdminDevice.objects.filter(business_admin=admin).update(is_active=False)
            hand_over_ownership(admin)
            BusinessAccountAdmin.objects.filter(business_admin=admin).update(is_active=False)
            admin.is_active = False
            admin.save()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.JWT_COOKIE_NAME)
        return response


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request_admin": request.user})
        serializer.is_valid(raise_exception=True)

        request.user.password = make_password(serializer.validated_data["new_password"])
        request.user.save()

        return Response({"result": "Password updated."})


def subscription_response(admin):
    subscription = SubscriptionService.for_admin(admin)
    payments = subscription.payments.select_related("plan")[:24]
    return Response({
        **SubscriptionSummarySerializer(SubscriptionService.summary(admin)).data,
        "plans": SubscriptionPlanSerializer(active_plans(), many=True).data,
        "payments": SubscriptionPaymentSerializer(payments, many=True).data,
        "payment_options": {
            "razorpay": Razorpay.is_configured(),
            "google_play": GooglePlay.is_configured(),
            "google_play_product_id": settings.GOOGLE_PLAY_PRODUCT_ID,
        },
    })


class SubscriptionView(APIView):
    """The login's trial or plan, the plans on sale, and past subscription payments."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return subscription_response(request.user)


class SubscriptionCancelView(APIView):
    """Turns off auto-renew. The days already paid for stay usable."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        subscription = SubscriptionService.for_admin(request.user)
        if not subscription.auto_renew:
            return Response({"detail": "Your plan isn't set to renew."}, status=status.HTTP_400_BAD_REQUEST)
        if subscription.provider == Subscription.GOOGLE_PLAY:
            return Response(
                {"detail": "This plan was bought in Google Play. Cancel it in Play Store → Payments & "
                           "subscriptions → Subscriptions."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if subscription.provider == Subscription.RAZORPAY:
            RazorpayBilling.cancel(subscription)
        else:
            SubscriptionService.stop_renewal(subscription)
        return subscription_response(request.user)


class RazorpayCheckoutView(APIView):
    """Creates a Razorpay subscription for the chosen plan; the website then opens Razorpay Checkout."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PlanChoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        checkout = RazorpayBilling.start_checkout(request.user, serializer.validated_data["plan"])
        checkout["plan"] = SubscriptionPlanSerializer(checkout["plan"]).data
        return Response(checkout, status=status.HTTP_201_CREATED)


class RazorpayConfirmView(APIView):
    """Verifies the checkout result so the plan unlocks immediately (the webhook confirms it again)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RazorpayConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        RazorpayBilling.confirm_checkout(
            request.user, data["razorpay_payment_id"], data["razorpay_subscription_id"], data["razorpay_signature"]
        )
        return subscription_response(request.user)


class RazorpaySyncView(APIView):
    """The app calls this after Razorpay's payment page closes; it reads the subscription straight from Razorpay."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RazorpaySyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        RazorpayBilling.sync(request.user, serializer.validated_data["subscription_id"])
        return subscription_response(request.user)


class GooglePlayConfirmView(APIView):
    """The Android app sends the purchase token right after a Google Play purchase."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = GooglePlayConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        GooglePlayBilling.confirm_purchase(request.user, serializer.validated_data["purchase_token"])
        return subscription_response(request.user)


class RazorpayWebhookView(APIView):
    """Renewals, failures and cancellations from Razorpay, signed with the webhook secret."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        body = request.body
        if not Razorpay.webhook_signature_matches(body, request.headers.get("X-Razorpay-Signature")):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            RazorpayBilling.handle_webhook(json.loads(body))
        except ProviderError:
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)  # Razorpay retries later
        return Response(status=status.HTTP_200_OK)


class GooglePlayWebhookView(APIView):
    """Google Play real-time developer notifications, pushed by Pub/Sub to ?token=<GOOGLE_PLAY_RTDN_TOKEN>."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        token = settings.GOOGLE_PLAY_RTDN_TOKEN
        if not token or not hmac.compare_digest(request.query_params.get("token", ""), token):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            GooglePlayBilling.handle_notification(request.data.get("message", {}))
        except ProviderError:
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)  # Pub/Sub retries later
        return Response(status=status.HTTP_204_NO_CONTENT)
