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
)
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

        admin = BusinessAdmin.objects.filter(Q(email__iexact=login) | Q(phone=login)).first()
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
        return Response({"results": BusinessAccountSerializer(accounts, many=True).data})

    def post(self, request):
        serializer = BusinessAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            account = BusinessAccount.objects.create(**serializer.validated_data)
            BusinessAccountAdmin.objects.create(
                business_account=account,
                business_admin=request.user,
                role="ADMIN",
                is_active=True,
            )

        return Response(BusinessAccountSerializer(account).data, status=status.HTTP_201_CREATED)


class BusinessAccountDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        account = get_object_or_404(BusinessAccountService.get_accounts_for_admin(request.user), id=id)
        return Response(BusinessAccountSerializer(account).data)

    def put(self, request, id):
        account = get_object_or_404(BusinessAccountService.get_accounts_for_admin(request.user), id=id)

        serializer = BusinessAccountUpdateSerializer(account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(BusinessAccountSerializer(account).data)

    def delete(self, request, id):
        account = get_object_or_404(BusinessAccountService.get_accounts_for_admin(request.user), id=id)

        account.is_active = False
        account.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

        serializer = PaymentCreateSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        member = data.pop("member_id")
        membership = data.pop("membership_id", None)
        # Default to the member's current active membership so dues stay attributable.
        if membership is None:
            membership = Membership.objects.filter(member=member, is_active=True).order_by("-id").first()
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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])
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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

        memberships = MemberService.get_memberships(params["business_account_id"], params["member_id"])
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(memberships, request, view=self)
        return paginator.get_paginated_response(MembershipSerializer(page, many=True).data)

    def post(self, request):
        query = BusinessAccountQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        business_account_id = query.validated_data["business_account_id"]
        BusinessAccountService.check_admin_access(request.user, business_account_id)

        serializer = MembershipActionSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        member, plan = data["member_id"], data["membership_plan_id"]
        discount = data.get("discount", Decimal("0"))

        with transaction.atomic():
            if not member.is_active:
                member.is_active = True
                member.save()
                ActivityService.log(member, "MEMBER_REACTIVATED", "Reactivated", request.user)
            if data["action"] == "renew":
                start_date = data.get("start_date") or MembershipService.renewal_start_date(member)
                membership = MembershipService.renew(member, plan, start_date, discount, request.user)
            else:
                membership = MembershipService.change_plan(member, plan, discount, request.user)
            if data.get("payment"):
                PaymentService.create(member, membership, data["payment"], request.user)

        member = MemberService.get_members(business_account_id).get(id=member.id)
        return Response(MemberSerializer(member).data, status=status.HTTP_201_CREATED)

    def put(self, request):
        query = MembershipDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])
        membership = get_object_or_404(
            Membership.objects.select_related("membership_plan__duration_type", "member"),
            id=params["membership_id"],
            business_account_id=params["business_account_id"],
        )

        serializer = MembershipUpdateSerializer(data=request.data, context={"membership": membership})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)
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
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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
        BusinessAccountService.check_admin_access(request.user, business_account_id)

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

        with transaction.atomic():
            serializer.save()
            if is_active is not None:
                account_admin.is_active = is_active
                account_admin.save()

        return Response(BusinessAccountAdminSerializer(account_admin).data)

    def get_account_admin(self, request):
        query = AdminDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

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
