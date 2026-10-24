"""API for PG businesses (rooms, tenants, rent bills, payments, deposits). Every endpoint takes ?business_account_id=."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Expense,
    Member,
    MemberAttendance,
    Notification,
    PgBed,
    PgBill,
    PgDepositEntry,
    PgRoom,
    PgTenancy,
    PgTenant,
)
from .pg import _ZERO, PgService, bill_balance_expr, check_pg
from .pg_serializers import (
    PG_DETAIL_FIELDS,
    BillDetailQuerySerializer,
    BillDiscountSerializer,
    ChargeCreateSerializer,
    CheckoutPreviewQuerySerializer,
    DepositCreateSerializer,
    DepositEntrySerializer,
    PgBillSerializer,
    PgPropertySerializer,
    PgRoomSerializer,
    PgTenancySerializer,
    PgTenantSerializer,
    PgTenantWriteSerializer,
    RentPaymentCreateSerializer,
    RoomDetailQuerySerializer,
    TenantActionSerializer,
    TenantDetailQuerySerializer,
    TenantListQuerySerializer,
)
from .serializers import BusinessAccountQuerySerializer, _money
from .services import ActivityService, BusinessAccountService, NotificationService, PaymentService, rupees

MEMBER_FIELDS = ["member_code", "first_name", "last_name", "phone", "email", "gender", "date_of_birth"]
TENANCY_FIELDS = ["rent", "billing_cycle_months", "due_day", "deposit_amount"]


def pg_params(request, query_serializer=BusinessAccountQuerySerializer):
    """Validated query params for a PG endpoint the logged-in admin may use."""
    query = query_serializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    params = query.validated_data
    BusinessAccountService.check_admin_access(request, params["business_account_id"])
    check_pg(params["business_account_id"])
    return params


def next_member_code(business_account_id):
    codes = set(Member.objects.filter(business_account_id=business_account_id).values_list("member_code", flat=True))
    number = len(codes) + 1
    while f"T{number}" in codes:
        number += 1
    return f"T{number}"


def occupants(business_account_id):
    return {
        t.bed_id: t
        for t in PgTenancy.objects.filter(business_account_id=business_account_id, status__in=PgTenancy.LIVING)
        .select_related("member")
    }


def tenant_detail(business_account_id, member_id):
    """A tenant with their bills, deposit and earlier stays: everything the profile screen shows."""
    member = get_object_or_404(PgService.tenants(business_account_id), id=member_id)
    PgService.attach_tenancies([member])
    tenancy = member.tenancy
    data = PgTenantSerializer(member).data
    if tenancy is None:
        return {**data, "bills": [], "deposit": None, "deposit_entries": [], "past_stays": []}
    bills = (
        PgBill.objects.filter(member_id=member.id)
        .exclude(status=PgBill.VOID)
        .prefetch_related("items", "payments")
        .order_by("-period_start", "-id")
    )
    deposit = {key: _money(value) for key, value in PgService.deposit_summary(tenancy).items()}
    past = PgTenancy.objects.filter(member_id=member.id).exclude(id=tenancy.id).select_related("bed__room")
    return {
        **data,
        "bills": PgBillSerializer(bills, many=True).data,
        "deposit": deposit,
        "deposit_entries": DepositEntrySerializer(tenancy.deposit_entries.order_by("-entry_date", "-id"), many=True).data,
        "past_stays": PgTenancySerializer(past.order_by("-start_date"), many=True).data,
    }


class PgPropertyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = pg_params(request)
        return Response(PgPropertySerializer(PgService.get_property(params["business_account_id"])).data)

    def put(self, request):
        params = pg_params(request)
        serializer = PgPropertySerializer(PgService.get_property(params["business_account_id"]), data=request.data,
                                          partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PgRoomView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = pg_params(request)
        business_account_id = params["business_account_id"]
        rooms = sorted(
            PgRoom.objects.filter(business_account_id=business_account_id, is_active=True).prefetch_related("beds"),
            key=lambda r: (r.floor or "", len(r.room_number), r.room_number),
        )
        context = {"occupants": occupants(business_account_id)}
        return Response({"results": PgRoomSerializer(rooms, many=True, context=context).data})

    def post(self, request):
        params = pg_params(request)
        business_account_id = params["business_account_id"]
        serializer = PgRoomSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        bed_count = data.pop("bed_count")
        with transaction.atomic():
            # A removed room with the same number comes back instead (room numbers are unique per PG).
            room = PgRoom.objects.filter(business_account_id=business_account_id,
                                         room_number__iexact=data["room_number"]).first()
            if room:
                for field, value in data.items():
                    setattr(room, field, value)
                room.is_active = True
                room.save()
            else:
                room = PgRoom.objects.create(business_account_id=business_account_id, **data)
            PgService.set_bed_count(room, bed_count)
        return Response(self.room_data(room), status=status.HTTP_201_CREATED)

    def put(self, request):
        room = self.get_room(request)
        serializer = PgRoomSerializer(room, data=request.data, partial=True,
                                      context={"business_account_id": room.business_account_id})
        serializer.is_valid(raise_exception=True)
        bed_count = serializer.validated_data.pop("bed_count", None)
        with transaction.atomic():
            serializer.save()
            if bed_count is not None:
                PgService.set_bed_count(room, bed_count)
        return Response(self.room_data(room))

    def delete(self, request):
        room = self.get_room(request)
        if PgTenancy.objects.filter(bed__room=room, status__in=PgTenancy.LIVING).exists():
            return Response({"detail": "Move the tenants out of this room before removing it."},
                            status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            room.is_active = False
            room.save()
            room.beds.update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_room(self, request):
        params = pg_params(request, RoomDetailQuerySerializer)
        return get_object_or_404(PgRoom, id=params["room_id"], business_account_id=params["business_account_id"],
                                 is_active=True)

    def room_data(self, room):
        room = PgRoom.objects.prefetch_related("beds").get(id=room.id)
        return PgRoomSerializer(room, context={"occupants": occupants(room.business_account_id)}).data


class PgTenantView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if "member_id" in request.query_params:
            params = pg_params(request, TenantDetailQuerySerializer)
            return Response(tenant_detail(params["business_account_id"], params["member_id"]))

        params = pg_params(request, TenantListQuerySerializer)
        business_account_id = params["business_account_id"]
        PgService.ensure_account_bills(business_account_id)
        members = PgService.filter_tenants(
            PgService.tenants(business_account_id), params.get("status"), params.get("has_dues"), params.get("search")
        )
        order = ["oldest_due_date", "first_name"] if params.get("has_dues") else ["first_name", "id"]
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(members.order_by(*order), request, view=self)
        PgService.attach_tenancies(page)
        return paginator.get_paginated_response(PgTenantSerializer(page, many=True).data)

    def post(self, request):
        params = pg_params(request)
        business_account_id = params["business_account_id"]
        serializer = PgTenantWriteSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        member_data = {k: data.pop(k) for k in MEMBER_FIELDS if k in data}
        details = {k: data.pop(k) for k in PG_DETAIL_FIELDS if k in data}
        bed = data.pop("bed_id")

        with transaction.atomic():
            member = Member.objects.create(
                **member_data,
                member_code=member_data.get("member_code") or next_member_code(business_account_id),
                business_account_id=business_account_id,
                created_by_business_admin=request.user,
                is_active=True,
            )
            PgTenant.objects.create(member=member, **details)
            PgService.move_in(member, bed, data, request.user)

        NotificationService.notify_activity(
            business_account_id, request.user, "New tenant added", f"{request.user.name} added {member} to {bed}", member,
        )
        return Response(tenant_detail(business_account_id, member.id), status=status.HTTP_201_CREATED)

    def put(self, request):
        params = pg_params(request, TenantDetailQuerySerializer)
        business_account_id = params["business_account_id"]
        member = get_object_or_404(Member, id=params["member_id"], business_account_id=business_account_id)
        serializer = PgTenantWriteSerializer(
            data=request.data, partial=True, context={"business_account_id": business_account_id, "member": member}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenancy = PgTenancy.objects.filter(member=member).order_by("-start_date", "-id").first()
        terms = {k: data[k] for k in TENANCY_FIELDS if k in data}
        if tenancy and terms.get("deposit_amount") is not None:
            collected = PgService.deposit_summary(tenancy)["collected"]
            if terms["deposit_amount"] < collected:
                return Response({"deposit_amount": [f"{rupees(collected)} is already collected."]},
                                status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for field in MEMBER_FIELDS:
                if field in data:
                    setattr(member, field, data[field])
            member.save()
            details = {k: data[k] for k in PG_DETAIL_FIELDS if k in data}
            if details:
                PgTenant.objects.update_or_create(member=member, defaults=details)
            if tenancy and terms:
                changes = [
                    f"{field.replace('_', ' ')} {getattr(tenancy, field)} → {value}"
                    for field, value in terms.items() if getattr(tenancy, field) != value
                ]
                for field, value in terms.items():
                    setattr(tenancy, field, value)
                tenancy.save()
                if changes:
                    ActivityService.log(member, "TENANCY_UPDATED",
                                        "Stay updated (from the next bill): " + "; ".join(changes), request.user)
        return Response(tenant_detail(business_account_id, member.id))


class PgTenantActionView(APIView):
    """Shift bed, give / withdraw notice, check out, or move a past tenant back in."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        params = pg_params(request)
        business_account_id = params["business_account_id"]
        serializer = TenantActionSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        member = data["member_id"]
        tenancy = PgTenancy.objects.filter(member=member).select_related("bed__room").order_by("-start_date", "-id").first()
        action = data["action"]
        living = tenancy is not None and tenancy.status in PgTenancy.LIVING
        if action == "move_in" and living:
            return Response({"detail": "This tenant already lives here."}, status=status.HTTP_400_BAD_REQUEST)
        if action != "move_in" and not living:
            return Response({"detail": "This tenant has moved out."}, status=status.HTTP_400_BAD_REQUEST)

        result = {}
        with transaction.atomic():
            if action == "shift":
                PgService.shift(tenancy, data["bed"], request.user, data.get("rent"))
            elif action == "notice":
                PgService.give_notice(tenancy, data["leave_date"], request.user, data.get("notice_date"),
                                      data.get("reason"))
            elif action == "cancel_notice":
                PgService.cancel_notice(tenancy, request.user)
            elif action == "checkout":
                result = PgService.checkout(tenancy, data, request.user)
            else:
                terms = data["terms"]
                member.is_active = True
                member.save()
                PgService.move_in(member, terms.pop("bed_id"), terms, request.user)

        response = tenant_detail(business_account_id, member.id)
        if result:
            response["checkout"] = {key: _money(value) for key, value in result.items()}
        return Response(response)


class PgCheckoutPreviewView(APIView):
    """What a checkout on a date would leave owing / to refund, without changing anything."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = pg_params(request, CheckoutPreviewQuerySerializer)
        tenancy = (
            PgTenancy.objects.filter(member_id=params["member_id"], business_account_id=params["business_account_id"],
                                     status__in=PgTenancy.LIVING)
            .first()
        )
        if tenancy is None:
            return Response({"detail": "This tenant has moved out."}, status=status.HTTP_400_BAD_REQUEST)
        leave_date = params.get("leave_date") or timezone.localdate()
        preview = PgService.checkout_preview(tenancy, leave_date, params["prorate_last_bill"])
        return Response({"leave_date": leave_date, **{key: _money(value) for key, value in preview.items()}})


class PgBillView(APIView):
    """A tenant's bills (GET ?member_id=), or a discount on one bill (PUT ?bill_id=)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = pg_params(request, TenantDetailQuerySerializer)
        bills = (
            PgBill.objects.filter(business_account_id=params["business_account_id"], member_id=params["member_id"])
            .exclude(status=PgBill.VOID)
            .prefetch_related("items", "payments")
            .order_by("-period_start", "-id")
        )
        return Response({"results": PgBillSerializer(bills, many=True).data})

    def put(self, request):
        params = pg_params(request, BillDetailQuerySerializer)
        bill = get_object_or_404(PgBill.objects.select_related("tenancy", "member"), id=params["bill_id"],
                                 business_account_id=params["business_account_id"])
        serializer = BillDiscountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            PgService.set_discount(bill, serializer.validated_data["discount"], request.user)
        return Response(tenant_detail(params["business_account_id"], bill.member_id))


class PgChargeView(APIView):
    """Adds a one-off charge (e.g. a key deposit or damage) to a tenant's current bill."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        params = pg_params(request)
        serializer = ChargeCreateSerializer(data=request.data, context={"business_account_id": params["business_account_id"]})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenancy = data["member_id"]
        with transaction.atomic():
            PgService.add_charge(tenancy, data["description"], data["amount"], request.user)
        return Response(tenant_detail(params["business_account_id"], tenancy.member_id), status=status.HTTP_201_CREATED)


class PgPaymentView(APIView):
    """Records rent received from a tenant (oldest bills first; any extra is kept as advance)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        params = pg_params(request)
        business_account_id = params["business_account_id"]
        serializer = RentPaymentCreateSerializer(data=request.data, context={"business_account_id": business_account_id})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenancy = data.pop("member_id")
        bill = data.pop("bill", None)
        with transaction.atomic():
            PgService.ensure_bills(tenancy)
            PgService.record_payment(tenancy, data, request.user, bill=bill)
        NotificationService.notify_activity(
            business_account_id, request.user, "Rent received",
            f"{request.user.name} recorded {rupees(data['amount'])} from {tenancy.member}", tenancy.member,
        )
        return Response(tenant_detail(business_account_id, tenancy.member_id), status=status.HTTP_201_CREATED)


class PgDepositView(APIView):
    """Deposit collected, refunded or kept (deducted) for a tenant."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        params = pg_params(request)
        serializer = DepositCreateSerializer(data=request.data, context={"business_account_id": params["business_account_id"]})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenancy = data["member_id"]
        with transaction.atomic():
            PgService.deposit_entry(
                tenancy, data["entry_type"], data["amount"], request.user, payment_method=data.get("payment_method"),
                reason=data.get("reason") or None, entry_date=data.get("entry_date"),
            )
        return Response(tenant_detail(params["business_account_id"], tenancy.member_id), status=status.HTTP_201_CREATED)


class PgDashboardView(APIView):
    """Everything the PG home screen needs in one request."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = pg_params(request)
        business_account_id = params["business_account_id"]
        today = timezone.localdate()
        PgService.ensure_account_bills(business_account_id, today)

        beds = PgBed.objects.filter(business_account_id=business_account_id, is_active=True, room__is_active=True).count()
        living = PgTenancy.objects.filter(business_account_id=business_account_id, status__in=PgTenancy.LIVING)
        occupied = living.values("bed_id").distinct().count()
        open_bills = PgBill.objects.filter(business_account_id=business_account_id,
                                           status__in=[PgBill.UNPAID, PgBill.PARTIAL])

        def total(qs):
            return qs.aggregate(total=Coalesce(Sum(bill_balance_expr()), _ZERO))["total"]

        deposits = {
            row["entry_type"]: row["total"]
            for row in PgDepositEntry.objects.filter(business_account_id=business_account_id)
            .values("entry_type").annotate(total=Sum("amount"))
        }
        held = deposits.get("COLLECT", Decimal("0")) - deposits.get("REFUND", Decimal("0")) - deposits.get(
            "DEDUCT", Decimal("0"))
        month_start = today.replace(day=1)
        expenses = Expense.objects.filter(business_account_id=business_account_id, is_active=True,
                                          expense_date__gte=month_start, expense_date__lte=today)
        month_expenses = expenses.aggregate(total=Coalesce(Sum("amount"), _ZERO))["total"]
        collections = PaymentService.get_collections_summary(business_account_id)
        collections["outstanding_dues"] = _money(total(open_bills))

        return Response({
            "beds": {"total": beds, "occupied": occupied, "vacant": max(beds - occupied, 0)},
            "rooms": PgRoom.objects.filter(business_account_id=business_account_id, is_active=True).count(),
            "tenants": {
                "living": living.count(),
                "notice": living.filter(status=PgTenancy.NOTICE).count(),
                "leaving_this_week": living.filter(status=PgTenancy.NOTICE,
                                                   expected_end_date__lte=today + timedelta(days=7)).count(),
                "joined_this_month": living.filter(start_date__gte=month_start).count(),
            },
            "collections": collections,
            "dues": {
                "total": _money(total(open_bills)),
                "overdue": _money(total(open_bills.filter(due_date__lt=today))),
                "due_today": _money(total(open_bills.filter(due_date=today))),
                "tenants": open_bills.values("member_id").distinct().count(),
            },
            "deposits_held": _money(held),
            "month_expenses": _money(month_expenses),
            "month_profit": _money(Decimal(collections["month_collection"]) - month_expenses),
            "checked_in_today": MemberAttendance.objects.filter(
                business_account_id=business_account_id, attendance_date=today
            ).count(),
            "unread_notifications": Notification.objects.filter(
                business_account_id=business_account_id, business_admin=request.user, is_read=False
            ).count(),
        })
