from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    LoginSerializer,
    MemberAttendanceDetailQuerySerializer,
    MemberAttendanceListQuerySerializer,
    MemberAttendanceSerializer,
    MemberAttendanceUpdateSerializer,
    MemberDetailQuerySerializer,
    MemberListQuerySerializer,
    MemberSerializer,
    MembershipPlanDetailQuerySerializer,
    MembershipPlanSerializer,
    SignupSerializer,
    StaffDetailQuerySerializer,
    StaffListQuerySerializer,
    StaffSerializer,
)
from .services import BusinessAccountService, BusinessAdminAuthService, MemberService


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
        if params["is_active"] is not None:
            members = members.filter(is_active=params["is_active"])

        # One filter() call so both dates apply to the same (active) membership.
        end_date_filters = {}
        if params.get("end_date_from"):
            end_date_filters["memberships__end_date__gte"] = params["end_date_from"]
        if params.get("end_date_to"):
            end_date_filters["memberships__end_date__lte"] = params["end_date_to"]
        if end_date_filters:
            members = members.filter(memberships__is_active=True, **end_date_filters)

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
        payment = data.pop("payment", None)

        with transaction.atomic():
            member = Member.objects.create(
                **data,
                business_account_id=business_account_id,
                created_by_business_admin=request.user,
                is_active=True,
            )
            membership = self.create_membership(member, plan, start_date)
            if payment:
                self.create_payment(request, member, membership, payment)

        member = MemberService.get_members(business_account_id).get(id=member.id)
        return Response(MemberSerializer(member).data, status=status.HTTP_201_CREATED)

    def put(self, request):
        member = self.get_member(request)

        serializer = MemberSerializer(
            member, data=request.data, partial=True, context={"business_account_id": member.business_account_id}
        )
        serializer.is_valid(raise_exception=True)
        plan = serializer.validated_data.pop("membership_plan_id", None)
        start_date = serializer.validated_data.pop("start_date", timezone.localdate())
        payment = serializer.validated_data.pop("payment", None)

        with transaction.atomic():
            serializer.save()
            # A different plan replaces the current active membership.
            membership = member.active_memberships[0] if member.active_memberships else None
            if plan and (membership is None or membership.membership_plan_id != plan.id):
                Membership.objects.filter(member=member, is_active=True).update(is_active=False)
                membership = self.create_membership(member, plan, start_date)
            if payment:
                self.create_payment(request, member, membership, payment)

        member = MemberService.get_members(member.business_account_id).get(id=member.id)
        return Response(MemberSerializer(member).data)

    def delete(self, request):
        member = self.get_member(request)

        with transaction.atomic():
            member.is_active = False
            member.save()
            Membership.objects.filter(member=member, is_active=True).update(is_active=False)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_member(self, request):
        query = MemberDetailQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        BusinessAccountService.check_admin_access(request.user, params["business_account_id"])

        return get_object_or_404(MemberService.get_members(params["business_account_id"]), id=params["member_id"])

    def create_membership(self, member, plan, start_date):
        return Membership.objects.create(
            business_account_id=member.business_account_id,
            member=member,
            membership_plan=plan,
            start_date=start_date,
            end_date=MemberService.calculate_end_date(start_date, plan),
            amount=plan.amount,
            is_active=True,
        )

    def create_payment(self, request, member, membership, payment):
        payment.setdefault("payment_date", timezone.now())
        Payment.objects.create(
            **payment,
            business_account_id=member.business_account_id,
            member=member,
            membership=membership,
            created_by_business_admin=request.user,
            is_active=True,
        )


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


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request_admin": request.user})
        serializer.is_valid(raise_exception=True)

        request.user.password = make_password(serializer.validated_data["new_password"])
        request.user.save()

        return Response({"result": "Password updated."})
