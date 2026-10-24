"""
PG / hostel businesses: rooms and beds, tenants' stays (tenancies), rent bills, rent payments, security deposits
and checkout.

A tenant is a `member` of a PG business; their stay on a bed is a `PgTenancy`. Rent is billed in advance: each
bill covers one billing cycle starting on the tenancy's due day. The first bill runs from the joining date to the
day before the next due day, at a prorated or the full rent. Payments are recorded against bills, oldest first;
anything over what's due is kept as the tenancy's advance and used up by the next bills.
"""

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .models import (
    BusinessAccount,
    BusinessAdminDevice,
    Member,
    Notification,
    Payment,
    PgBed,
    PgBill,
    PgBillItem,
    PgDepositEntry,
    PgProperty,
    PgTenancy,
)
from .services import ActivityService, BusinessAccountService, NotificationService, PaymentService, rupees

PG = "PG"

# Older app builds only know gyms. Builds that can run a PG send this header, and only they see PG
# businesses and the PG business type.
FEATURES_HEADER = "X-Vyntra-Features"

_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Value(Decimal("0"), output_field=_MONEY)


def client_supports_pg(request):
    features = request.headers.get(FEATURES_HEADER, "")
    return PG.lower() in [f.strip().lower() for f in features.split(",")]


def is_pg(business_account_id):
    return BusinessAccount.objects.filter(id=business_account_id, business_type__code=PG).exists()


def check_pg(business_account_id):
    if not is_pg(business_account_id):
        raise NotFound("This business isn't a PG.")


def whole_rupees(amount):
    return Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def add_months(day, months, on_day=None):
    """`day` moved by `months` months, on `on_day` (default the same day), clipped to the month's last day."""
    year, month = divmod(day.month - 1 + months, 12)
    year, month = day.year + year, month + 1
    return date(year, month, min(on_day or day.day, calendar.monthrange(year, month)[1]))


def default_due_day(start_date):
    """Rent falls due on the joining day each month; days after the 28th don't exist in every month."""
    return min(start_date.day, 28)


def bill_status(bill):
    if bill.total - bill.discount - bill.paid <= 0:
        return PgBill.PAID
    return PgBill.PARTIAL if bill.paid > 0 else PgBill.UNPAID


def bill_balance_expr():
    return F("total") - F("discount") - F("paid")


def member_due_expr():
    """What a tenant still owes across their bills."""
    owed = Subquery(
        PgBill.objects.filter(member_id=OuterRef("pk"))
        .exclude(status=PgBill.VOID)
        .values("member_id")
        .annotate(s=Sum(bill_balance_expr()))
        .values("s")[:1],
        output_field=_MONEY,
    )
    return Coalesce(owed, _ZERO)


def oldest_due_expr():
    """Due date of a tenant's oldest unpaid bill."""
    return Subquery(
        PgBill.objects.filter(member_id=OuterRef("pk"), status__in=[PgBill.UNPAID, PgBill.PARTIAL])
        .order_by("due_date")
        .values("due_date")[:1]
    )


def latest_tenancy_expr():
    return Subquery(
        PgTenancy.objects.filter(member_id=OuterRef("pk")).order_by("-start_date", "-id").values("id")[:1]
    )


class PgService:
    # ---------------------------------------------------------------------------------------------------------
    # Property and beds

    @classmethod
    def get_property(cls, business_account_id):
        prop, _ = PgProperty.objects.get_or_create(business_account_id=business_account_id)
        return prop

    @classmethod
    def occupant(cls, bed):
        return PgTenancy.objects.filter(bed=bed, status__in=PgTenancy.LIVING).select_related("member").first()

    @classmethod
    def check_bed_free(cls, bed, tenancy=None):
        others = PgTenancy.objects.filter(bed=bed, status__in=PgTenancy.LIVING)
        if tenancy is not None:
            others = others.exclude(id=tenancy.id)
        living = others.select_related("member").first()
        if living:
            raise ValidationError({"bed_id": f"This bed is taken by {living.member}."})

    @classmethod
    def set_bed_count(cls, room, count):
        """Adds beds (reusing removed ones first) or removes free beds, highest numbers first."""
        beds = list(PgBed.objects.filter(room=room).order_by("id"))
        active = [b for b in beds if b.is_active]
        if count > len(active):
            needed = count - len(active)
            for bed in [b for b in beds if not b.is_active][:needed]:
                bed.is_active = True
                bed.save()
                needed -= 1
            labels = {b.label for b in beds}
            number = 1
            while needed:
                if str(number) not in labels:
                    PgBed.objects.create(business_account_id=room.business_account_id, room=room, label=str(number))
                    needed -= 1
                number += 1
        elif count < len(active):
            taken = set(
                PgTenancy.objects.filter(bed__room=room, status__in=PgTenancy.LIVING).values_list("bed_id", flat=True)
            )
            free = sorted((b for b in active if b.id not in taken), key=lambda b: (len(b.label), b.label), reverse=True)
            remove = len(active) - count
            if remove > len(free):
                raise ValidationError({"bed_count": f"{len(taken)} bed(s) in this room are taken."})
            for bed in free[:remove]:
                bed.is_active = False
                bed.save()

    # ---------------------------------------------------------------------------------------------------------
    # Bills

    @classmethod
    def first_period(cls, start_date, due_day, cycle_months):
        """(period end, length in days of a full cycle ending then) of the first bill."""
        if start_date.day == due_day:
            end = add_months(start_date, cycle_months) - timedelta(days=1)
            return end, (end - start_date).days + 1
        if due_day > start_date.day:
            next_due = start_date.replace(day=due_day)
        else:
            next_due = add_months(start_date, 1, due_day)
        full_start = add_months(next_due, -cycle_months, due_day)
        return next_due - timedelta(days=1), (next_due - full_start).days

    @classmethod
    def cycle_rent(cls, tenancy):
        return tenancy.rent * tenancy.billing_cycle_months

    @classmethod
    def create_bill(cls, tenancy, period_start, period_end, items):
        """A bill made of (item_type, description, amount) lines; the tenancy's advance pays what it can."""
        total = sum((amount for _, _, amount in items), Decimal("0"))
        bill = PgBill.objects.create(
            business_account_id=tenancy.business_account_id,
            tenancy=tenancy,
            member_id=tenancy.member_id,
            period_start=period_start,
            period_end=period_end,
            due_date=period_start,
            total=total,
        )
        PgBillItem.objects.bulk_create(
            PgBillItem(bill=bill, item_type=kind, description=text, amount=amount) for kind, text, amount in items
        )
        cls.apply_advance(tenancy, bill)
        return bill

    @classmethod
    def apply_advance(cls, tenancy, bill):
        use = min(tenancy.advance_balance, max(bill.balance, Decimal("0")))
        if use > 0:
            bill.paid += use
            tenancy.advance_balance -= use
            tenancy.save(update_fields=["advance_balance", "updated_at"])
        bill.status = bill_status(bill)
        bill.save()

    @classmethod
    def save_bill(cls, bill):
        """After a bill's total or discount changes: anything paid beyond it moves to the advance."""
        excess = bill.paid - (bill.total - bill.discount)
        if excess > 0:
            bill.paid -= excess
            tenancy = bill.tenancy
            tenancy.advance_balance += excess
            tenancy.save(update_fields=["advance_balance", "updated_at"])
        bill.status = bill_status(bill)
        bill.save()

    @classmethod
    def first_bill(cls, tenancy, prorate):
        start = tenancy.start_date
        end, full_days = cls.first_period(start, tenancy.due_day, tenancy.billing_cycle_months)
        days = (end - start).days + 1
        rent = cls.cycle_rent(tenancy)
        if days < full_days and prorate:
            rent = whole_rupees(rent * days / full_days)
            text = f"Rent {start:%d %b} – {end:%d %b %Y} ({days} days)"
        else:
            text = f"Rent {start:%d %b} – {end:%d %b %Y}"
        return cls.create_bill(tenancy, start, end, [(PgBillItem.RENT, text, rent)])

    @classmethod
    def ensure_bills(cls, tenancy, today=None):
        """Creates every bill that has fallen due for a tenant who still lives here (catches up missed days)."""
        if tenancy.status not in PgTenancy.LIVING:
            return
        today = today or timezone.localdate()
        last = tenancy.bills.exclude(status=PgBill.VOID).order_by("-period_start").first()
        while last is not None and last.period_end < today:
            start = last.period_end + timedelta(days=1)
            if tenancy.expected_end_date and start > tenancy.expected_end_date:
                return
            end = add_months(start, tenancy.billing_cycle_months, tenancy.due_day) - timedelta(days=1)
            text = f"Rent {start:%d %b} – {end:%d %b %Y}"
            try:
                with transaction.atomic():
                    last = cls.create_bill(tenancy, start, end, [(PgBillItem.RENT, text, cls.cycle_rent(tenancy))])
            except IntegrityError:  # made by a request running at the same time
                last = tenancy.bills.get(period_start=start)

    @classmethod
    def ensure_account_bills(cls, business_account_id, today=None):
        for tenancy in PgTenancy.objects.filter(business_account_id=business_account_id, status__in=PgTenancy.LIVING):
            cls.ensure_bills(tenancy, today)

    @classmethod
    def open_bills(cls, tenancy):
        return tenancy.bills.filter(status__in=[PgBill.UNPAID, PgBill.PARTIAL]).order_by("period_start", "id")

    @classmethod
    def due(cls, tenancy):
        return tenancy.bills.exclude(status=PgBill.VOID).aggregate(
            total=Coalesce(Sum(bill_balance_expr()), _ZERO)
        )["total"]

    @classmethod
    def current_bill(cls, tenancy, today=None):
        """The bill covering today, else the latest one."""
        today = today or timezone.localdate()
        bills = tenancy.bills.exclude(status=PgBill.VOID)
        return (
            bills.filter(period_start__lte=today, period_end__gte=today).first()
            or bills.order_by("-period_start").first()
        )

    @classmethod
    def add_charge(cls, tenancy, description, amount, admin):
        bill = cls.current_bill(tenancy)
        if bill is None:
            raise ValidationError({"detail": "This tenant has no bill to add the charge to."})
        PgBillItem.objects.create(bill=bill, item_type=PgBillItem.CHARGE, description=description, amount=amount)
        bill.total += amount
        cls.apply_advance(tenancy, bill)
        ActivityService.log(tenancy.member, "CHARGE_ADDED", f"Charge added: {description}, {rupees(amount)}", admin)
        return bill

    @classmethod
    def set_discount(cls, bill, discount, admin):
        if discount > bill.total:
            raise ValidationError({"discount": "Discount can't be more than the bill."})
        old = bill.discount
        bill.discount = discount
        cls.save_bill(bill)
        ActivityService.log(
            bill.member,
            "DISCOUNT_GIVEN",
            f"Discount on the bill for {bill.period_start:%d %b %Y}: {rupees(old)} → {rupees(discount)}",
            admin,
        )
        return bill

    # ---------------------------------------------------------------------------------------------------------
    # Payments

    @classmethod
    def record_payment(cls, tenancy, data, admin, bill=None):
        """
        Pays the chosen bill first, then the oldest open bills; anything left over is kept as advance.
        One `payment` row per bill paid (and one for the advance), so each bill knows what paid it.
        """
        remaining = data["amount"]
        common = {
            "business_account_id": tenancy.business_account_id,
            "member_id": tenancy.member_id,
            "payment_date": data.get("payment_date") or timezone.now(),
            "payment_method": data["payment_method"],
            "transaction_reference": data.get("transaction_reference"),
            "notes": data.get("notes"),
            "created_by_business_admin": admin,
            "is_active": True,
        }
        bills = list(cls.open_bills(tenancy))
        if bill is not None and bill in bills:
            bills.remove(bill)
            bills.insert(0, bill)
        payments = []
        for open_bill in bills:
            if remaining <= 0:
                break
            portion = min(remaining, open_bill.balance)
            payments.append(Payment.objects.create(**common, pg_bill=open_bill, amount=portion))
            open_bill.paid += portion
            open_bill.status = bill_status(open_bill)
            open_bill.save()
            remaining -= portion
        if remaining > 0:
            payments.append(Payment.objects.create(**common, amount=remaining))
            tenancy.advance_balance += remaining
            tenancy.save(update_fields=["advance_balance", "updated_at"])

        method = PaymentService.METHOD_LABELS.get(data["payment_method"], data["payment_method"])
        text = f"Paid {rupees(data['amount'])} by {method}"
        if data.get("transaction_reference"):
            text += f" (ref {data['transaction_reference']})"
        if remaining > 0:
            text += f", {rupees(remaining)} kept as advance"
        ActivityService.log(tenancy.member, "PAYMENT_ADDED", text, admin, payment=payments[0])
        return payments

    @classmethod
    def undo_payment(cls, payment):
        """Takes a deleted payment back off its bill, or off the advance (and the bills the advance paid)."""
        if payment.pg_bill_id:
            bill = payment.pg_bill
            bill.paid = max(bill.paid - payment.amount, Decimal("0"))
            bill.status = bill_status(bill) if bill.status != PgBill.VOID else PgBill.VOID
            bill.save()
            return
        tenancy = PgTenancy.objects.filter(member_id=payment.member_id).order_by("-start_date", "-id").first()
        if tenancy is None:
            return
        take = payment.amount
        from_advance = min(take, tenancy.advance_balance)
        tenancy.advance_balance -= from_advance
        tenancy.save(update_fields=["advance_balance", "updated_at"])
        take -= from_advance
        for bill in tenancy.bills.exclude(status=PgBill.VOID).filter(paid__gt=0).order_by("-period_start"):
            if take <= 0:
                break
            back = min(take, bill.paid)
            bill.paid -= back
            bill.status = bill_status(bill)
            bill.save()
            take -= back

    # ---------------------------------------------------------------------------------------------------------
    # Deposits

    @classmethod
    def deposit_summary(cls, tenancy):
        totals = {
            row["entry_type"]: row["total"]
            for row in tenancy.deposit_entries.values("entry_type").annotate(total=Sum("amount"))
        }
        collected = totals.get(PgDepositEntry.COLLECT, Decimal("0"))
        refunded = totals.get(PgDepositEntry.REFUND, Decimal("0"))
        deducted = totals.get(PgDepositEntry.DEDUCT, Decimal("0"))
        return {
            "agreed": tenancy.deposit_amount,
            "collected": collected,
            "refunded": refunded,
            "deducted": deducted,
            "held": collected - refunded - deducted,
            "pending": max(tenancy.deposit_amount - collected, Decimal("0")),
        }

    @classmethod
    def deposit_entry(cls, tenancy, entry_type, amount, admin, payment_method=None, reason=None, entry_date=None):
        summary = cls.deposit_summary(tenancy)
        if entry_type == PgDepositEntry.COLLECT and amount > summary["pending"]:
            raise ValidationError(
                {"amount": f"Only {rupees(summary['pending'])} of the deposit is still to collect."}
                if summary["pending"] > 0
                else {"amount": "The deposit is already collected in full."}
            )
        if entry_type != PgDepositEntry.COLLECT and amount > summary["held"]:
            raise ValidationError({"amount": f"Only {rupees(summary['held'])} of the deposit is held."})
        entry = PgDepositEntry.objects.create(
            business_account_id=tenancy.business_account_id,
            tenancy=tenancy,
            entry_type=entry_type,
            amount=amount,
            entry_date=entry_date or timezone.localdate(),
            payment_method=payment_method,
            reason=reason,
            created_by_business_admin=admin,
        )
        verb = {PgDepositEntry.COLLECT: "collected", PgDepositEntry.REFUND: "refunded",
                PgDepositEntry.DEDUCT: "kept"}[entry_type]
        ActivityService.log(
            tenancy.member, f"DEPOSIT_{entry_type}", f"Deposit {verb}: {rupees(amount)}" + (f" ({reason})" if reason else ""),
            admin,
        )
        return entry

    # ---------------------------------------------------------------------------------------------------------
    # Tenant lifecycle

    @classmethod
    def move_in(cls, member, bed, data, admin):
        """Starts a stay: the tenancy, its first bill, one-off charges, the deposit paid and rent received now."""
        cls.check_bed_free(bed)
        start_date = data.get("start_date") or timezone.localdate()
        prop = cls.get_property(member.business_account_id)
        tenancy = PgTenancy.objects.create(
            business_account_id=member.business_account_id,
            member=member,
            bed=bed,
            rent=data.get("rent", bed.room.rent_per_bed),
            billing_cycle_months=data.get("billing_cycle_months", 1),
            due_day=data.get("due_day") or default_due_day(start_date),
            start_date=start_date,
            deposit_amount=data.get("deposit_amount") or Decimal("0"),
            created_by_business_admin=admin,
        )
        prorate = data.get("prorate_first_bill", prop.prorate_first_bill)
        bill = cls.first_bill(tenancy, prorate)
        for charge in data.get("charges") or []:
            PgBillItem.objects.create(
                bill=bill, item_type=PgBillItem.CHARGE, description=charge["description"], amount=charge["amount"]
            )
            bill.total += charge["amount"]
        bill.status = bill_status(bill)
        bill.save()
        cls.ensure_bills(tenancy)

        ActivityService.log(
            member, "TENANT_MOVED_IN",
            f"Moved in to {bed} on {start_date:%d %b %Y}, rent {rupees(tenancy.rent)}/month, due on day {tenancy.due_day}",
            admin,
        )
        if data.get("deposit_paid"):
            cls.deposit_entry(
                tenancy, PgDepositEntry.COLLECT, data["deposit_paid"], admin,
                payment_method=(data.get("payment") or {}).get("payment_method", "CASH"),
            )
        if data.get("payment"):
            cls.record_payment(tenancy, data["payment"], admin, bill=bill)
        return tenancy

    @classmethod
    def shift(cls, tenancy, bed, admin, rent=None):
        if bed.id == tenancy.bed_id:
            raise ValidationError({"bed_id": "The tenant is already on this bed."})
        cls.check_bed_free(bed, tenancy)
        old = tenancy.bed
        tenancy.bed = bed
        text = f"Moved from {old} to {bed}"
        if rent is not None and rent != tenancy.rent:
            text += f", rent {rupees(tenancy.rent)} → {rupees(rent)} from the next bill"
            tenancy.rent = rent
        tenancy.save()
        ActivityService.log(tenancy.member, "BED_CHANGED", text, admin)
        return tenancy

    @classmethod
    def give_notice(cls, tenancy, leave_date, admin, notice_date=None, reason=None):
        if tenancy.status != PgTenancy.ACTIVE:
            raise ValidationError({"detail": "This tenant has already given notice."})
        if leave_date < tenancy.start_date:
            raise ValidationError({"leave_date": "The leaving date can't be before they moved in."})
        tenancy.status = PgTenancy.NOTICE
        tenancy.notice_date = notice_date or timezone.localdate()
        tenancy.expected_end_date = leave_date
        tenancy.leave_reason = reason or None
        tenancy.save()
        ActivityService.log(
            tenancy.member, "NOTICE_GIVEN",
            f"Gave notice, leaving on {leave_date:%d %b %Y}" + (f" ({reason})" if reason else ""), admin,
        )
        return tenancy

    @classmethod
    def cancel_notice(cls, tenancy, admin):
        if tenancy.status != PgTenancy.NOTICE:
            raise ValidationError({"detail": "This tenant hasn't given notice."})
        tenancy.status = PgTenancy.ACTIVE
        tenancy.notice_date = tenancy.expected_end_date = tenancy.leave_reason = None
        tenancy.save()
        cls.ensure_bills(tenancy)
        ActivityService.log(tenancy.member, "NOTICE_CANCELLED", "Notice withdrawn, staying on", admin)
        return tenancy

    @classmethod
    def checkout_preview(cls, tenancy, leave_date, prorate_last=False):
        """What checking out on `leave_date` would leave: dues, deposit held and advance to give back."""
        with transaction.atomic():
            sid = transaction.savepoint()
            result = cls._settle_bills(tenancy, leave_date, prorate_last)
            result["deposit_held"] = cls.deposit_summary(tenancy)["held"]
            transaction.savepoint_rollback(sid)
        return result

    @classmethod
    def _settle_bills(cls, tenancy, leave_date, prorate_last):
        """Voids bills after the leaving date (their payments become advance), optionally prorates the last one
        and uses the advance on what's still owed."""
        for bill in tenancy.bills.exclude(status=PgBill.VOID).filter(period_start__gt=leave_date):
            tenancy.advance_balance += bill.paid
            bill.paid = Decimal("0")
            bill.status = PgBill.VOID
            bill.save()
        tenancy.save(update_fields=["advance_balance", "updated_at"])

        last = tenancy.bills.exclude(status=PgBill.VOID).filter(period_start__lte=leave_date, period_end__gt=leave_date).first()
        if last is not None and prorate_last:
            days = (leave_date - last.period_start).days + 1
            full = (last.period_end - last.period_start).days + 1
            for item in last.items.filter(item_type=PgBillItem.RENT):
                new = whole_rupees(item.amount * days / full)
                last.total -= item.amount - new
                item.amount = new
                item.description += f", charged to {leave_date:%d %b} ({days} days)"
                item.save()
            cls.save_bill(last)

        tenancy.refresh_from_db(fields=["advance_balance"])
        for bill in cls.open_bills(tenancy):
            cls.apply_advance(tenancy, bill)
        return {"dues": cls.due(tenancy), "advance": tenancy.advance_balance}

    @classmethod
    def checkout(cls, tenancy, data, admin):
        """
        Ends the stay on `leave_date`: settles the bills, optionally pays dues from the deposit, keeps a deduction,
        refunds the rest of the deposit and any advance, frees the bed and moves the tenant to past tenants.
        """
        if tenancy.status not in PgTenancy.LIVING:
            raise ValidationError({"detail": "This tenant has already left."})
        leave_date = data.get("leave_date") or timezone.localdate()
        if leave_date < tenancy.start_date:
            raise ValidationError({"leave_date": "The leaving date can't be before they moved in."})
        method = data.get("refund_method") or "CASH"

        settled = cls._settle_bills(tenancy, leave_date, data.get("prorate_last_bill", False))
        held = cls.deposit_summary(tenancy)["held"]
        deduction = data.get("deduction") or Decimal("0")
        if deduction > held:
            raise ValidationError({"deduction": f"Only {rupees(held)} of the deposit is held."})

        if data.get("dues_from_deposit") and settled["dues"] > 0 and held - deduction > 0:
            use = min(settled["dues"], held - deduction)
            cls.deposit_entry(tenancy, PgDepositEntry.DEDUCT, use, admin, reason="Used for rent dues",
                              entry_date=leave_date)
            cls.record_payment(tenancy, {"amount": use, "payment_method": "DEPOSIT",
                                         "notes": "Paid from the security deposit at checkout"}, admin)
        if deduction > 0:
            cls.deposit_entry(tenancy, PgDepositEntry.DEDUCT, deduction, admin,
                              reason=data.get("deduction_reason") or "Kept at checkout", entry_date=leave_date)
        refund = cls.deposit_summary(tenancy)["held"]
        if refund > 0:
            cls.deposit_entry(tenancy, PgDepositEntry.REFUND, refund, admin, payment_method=method,
                              entry_date=leave_date)

        tenancy.refresh_from_db()
        advance = tenancy.advance_balance
        if advance > 0:
            # Rent paid ahead goes back to the tenant, so it no longer counts as collected.
            Payment.objects.create(
                business_account_id=tenancy.business_account_id, member_id=tenancy.member_id, amount=-advance,
                payment_date=timezone.now(), payment_method=method, notes="Advance refunded at checkout",
                created_by_business_admin=admin, is_active=True,
            )
            tenancy.advance_balance = Decimal("0")

        tenancy.status = PgTenancy.ENDED
        tenancy.end_date = leave_date
        if data.get("reason"):
            tenancy.leave_reason = data["reason"]
        tenancy.save()
        member = tenancy.member
        member.is_active = False
        member.save()

        dues = cls.due(tenancy)
        text = f"Moved out of {tenancy.bed} on {leave_date:%d %b %Y}"
        if refund > 0:
            text += f", deposit refunded {rupees(refund)}"
        if advance > 0:
            text += f", advance refunded {rupees(advance)}"
        if dues > 0:
            text += f", {rupees(dues)} still due"
        ActivityService.log(member, "TENANT_MOVED_OUT", text, admin)
        return {"deposit_refunded": refund, "advance_refunded": advance, "dues": dues}

    # ---------------------------------------------------------------------------------------------------------
    # Lists

    @classmethod
    def tenants(cls, business_account_id):
        """Tenants (members) of a PG, annotated with their latest tenancy and what they owe."""
        return (
            Member.objects.filter(business_account_id=business_account_id)
            .select_related("pg_details")
            .annotate(latest_tenancy_id=latest_tenancy_expr(), total_due=member_due_expr(), oldest_due_date=oldest_due_expr())
        )

    @classmethod
    def attach_tenancies(cls, members):
        """Loads each member's latest tenancy (with bed and room) as `tenancy`."""
        ids = [m.latest_tenancy_id for m in members if m.latest_tenancy_id]
        tenancies = PgTenancy.objects.select_related("bed__room").in_bulk(ids)
        for member in members:
            member.tenancy = tenancies.get(member.latest_tenancy_id)
        return members

    @classmethod
    def filter_tenants(cls, members, status=None, has_dues=None, search=None):
        if search:
            members = members.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(phone__icontains=search)
                | Q(member_code__icontains=search)
                | Q(pg_tenancies__bed__room__room_number__iexact=search)
            ).distinct()
        living = PgTenancy.objects.filter(member_id=OuterRef("pk"), status__in=PgTenancy.LIVING)
        if status == "living":
            members = members.filter(id__in=living.values("member_id"))
        elif status in ("active", "notice"):
            members = members.filter(
                id__in=PgTenancy.objects.filter(status=status.upper()).values("member_id")
            )
        elif status == "past":
            members = members.exclude(
                id__in=PgTenancy.objects.filter(status__in=PgTenancy.LIVING).values("member_id")
            ).filter(id__in=PgTenancy.objects.values("member_id"))
        if has_dues is not None:
            members = members.filter(total_due__gt=0) if has_dues else members.filter(total_due__lte=0)
        return members


def pg_morning(business_account_id, today):
    """The PG version of the morning job: makes the day's rent bills, then rent due / overdue / leaving alerts."""
    PgService.ensure_account_bills(business_account_id, today)
    setting = NotificationService.get_setting(business_account_id)
    push_details = not setting.morning_summary
    names = NotificationService._names

    open_bills = (
        PgBill.objects.filter(business_account_id=business_account_id, status__in=[PgBill.UNPAID, PgBill.PARTIAL],
                              tenancy__status__in=PgTenancy.LIVING)
        .select_related("member")
        .order_by("due_date")
    )
    due_today = [b for b in open_bills if b.due_date == today]
    overdue = [b for b in open_bills if b.due_date < today]
    overdue_total = sum((b.balance for b in overdue), Decimal("0"))
    leaving = list(
        PgTenancy.objects.filter(
            business_account_id=business_account_id, status=PgTenancy.NOTICE,
            expected_end_date__gte=today, expected_end_date__lte=today + timedelta(days=3),
        ).select_related("member")
    )
    birthdays = [
        m for m in Member.objects.filter(business_account_id=business_account_id, is_active=True,
                                         date_of_birth__isnull=False)
        if (m.date_of_birth.month, m.date_of_birth.day) == (today.month, today.day)
    ]

    if setting.dues_reminders and due_today:
        NotificationService.notify(
            business_account_id, "RENT_DUE", f"Rent due today from {len(due_today)} tenant(s)",
            names([b.member for b in due_today]), push=push_details, member_filter="dues",
        )
    if setting.dues_reminders and today.weekday() == 0 and overdue:
        tenants = list({b.member_id: b.member for b in overdue}.values())
        NotificationService.notify(
            business_account_id, "DUES", f"{rupees(overdue_total)} rent overdue",
            f"{len(tenants)} tenant(s): {names(tenants)}", push=push_details, member_filter="dues",
        )
    if setting.expiry_reminders and leaving:
        NotificationService.notify(
            business_account_id, "LEAVING", f"{len(leaving)} tenant(s) leaving in the next 3 days",
            ", ".join(f"{t.member} ({t.expected_end_date:%d %b})" for t in leaving),
            push=push_details, member_filter="notice",
        )
    if setting.birthday_alerts and birthdays:
        NotificationService.notify(business_account_id, "BIRTHDAY", "🎂 Birthdays today", names(birthdays),
                                   push=push_details, member=birthdays[0] if len(birthdays) == 1 else None)

    parts = []
    if due_today:
        parts.append(f"{len(due_today)} rent(s) due today")
    if overdue:
        parts.append(f"{rupees(overdue_total)} overdue")
    if leaving:
        parts.append(f"{len(leaving)} leaving soon")
    if birthdays:
        parts.append(f"{len(birthdays)} birthday(s)")
    title = "Good morning! Today at your PG"
    admins = BusinessAccountService.get_admins(business_account_id)
    # Recorded even when switched off, so the job doesn't run twice in a day.
    Notification.objects.bulk_create(
        Notification(
            business_account_id=business_account_id, business_admin=admin, notification_type="MORNING_SUMMARY",
            title=title, message=" · ".join(parts) if parts else "All clear: nothing needs your attention today.",
            notification_date=today, is_read=not setting.morning_summary,
        )
        for admin in admins
    )
    if setting.morning_summary and parts:
        tokens = BusinessAdminDevice.objects.filter(business_admin__in=admins, is_active=True).values_list(
            "push_token", flat=True
        )
        NotificationService.send_push(list(tokens), title, " · ".join(parts),
                                      {"business_account_id": business_account_id, "member_filter": None,
                                       "member_id": None})
