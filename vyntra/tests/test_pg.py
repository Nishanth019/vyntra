from datetime import date
from decimal import Decimal

from vyntra.models import (
    BusinessAccount,
    BusinessAccountAdmin,
    BusinessType,
    Expense,
    Notification,
    Payment,
    PgBill,
    PgTenancy,
    Staff,
)
from vyntra.pg import PgService, add_months

from .base import ApiTestCase, days


class PgTestCase(ApiTestCase):
    """The gym from ApiTestCase plus a PG with room 101 (2 beds, ₹5,000), owned by the same admin."""

    def setUp(self):
        super().setUp()
        self.pg = BusinessAccount.objects.create(business_type=BusinessType.objects.get(code="PG"), name="PG")
        BusinessAccountAdmin.objects.create(business_account=self.pg, business_admin=self.admin, role="OWNER",
                                            is_active=True)
        self.client.credentials(HTTP_AUTHORIZATION=self.client._credentials["HTTP_AUTHORIZATION"],
                                HTTP_X_VYNTRA_FEATURES="pg")
        self.p = f"?business_account_id={self.pg.id}"
        self.room = self.post("rooms", {"room_number": "101", "rent_per_bed": "5000", "bed_count": 2})
        self.bed1, self.bed2 = (b["id"] for b in self.room["beds"])
        self.phones = 0

    def post(self, path, body, expect=201):
        response = self.client.post(f"/api/v1/pg/{path}/{self.p}", body, format="json")
        self.assertEqual(response.status_code, expect, response.data)
        return response.data

    def add_tenant(self, start, bed=None, **fields):
        self.phones += 1
        return self.post("tenants", {"first_name": f"Tenant{self.phones}", "phone": f"98765{self.phones:05d}",
                                     "bed_id": bed or self.bed1, "start_date": str(start), **fields})

    def tenant(self, member_id):
        return self.client.get(f"/api/v1/pg/tenants/{self.p}&member_id={member_id}").data

    def action(self, member_id, action, expect=200, **fields):
        body = {"action": action, "member_id": member_id}
        body.update({k: str(v) if hasattr(v, "isoformat") else v for k, v in fields.items()})
        response = self.client.post(f"/api/v1/pg/tenants/action/{self.p}", body, format="json")
        self.assertEqual(response.status_code, expect, response.data)
        return response.data


class OlderAppTests(PgTestCase):
    def test_older_builds_never_see_pg(self):
        self.client.credentials(HTTP_AUTHORIZATION=self.client._credentials["HTTP_AUTHORIZATION"])
        types = [t["code"] for t in self.client.get("/api/v1/business-types/").data["results"]]
        accounts = [a["id"] for a in self.client.get("/api/v1/business-accounts/").data["results"]]
        self.assertEqual(types, ["GYM"])
        self.assertEqual(accounts, [self.account.id])

    def test_new_builds_see_both(self):
        types = {t["code"] for t in self.client.get("/api/v1/business-types/").data["results"]}
        self.assertEqual(types, {"GYM", "PG"})

    def test_pg_endpoints_refuse_a_gym(self):
        response = self.client.get(f"/api/v1/pg/rooms/{self.q}")
        self.assertEqual(response.status_code, 404)

    def test_creating_a_pg_sets_it_up(self):
        pg_type = BusinessType.objects.get(code="PG")
        response = self.client.post("/api/v1/business-accounts/", {"name": "New PG", "business_type_id": pg_type.id},
                                    format="json")
        self.assertEqual(response.status_code, 201, response.data)
        settings = self.client.get(f"/api/v1/pg/property/?business_account_id={response.data['id']}").data
        self.assertEqual(settings["default_due_day"], 1)


class RoomTests(PgTestCase):
    def test_beds_follow_the_count_but_taken_beds_stay(self):
        self.add_tenant(days(0), bed=self.bed2)
        response = self.client.put(f"/api/v1/pg/rooms/{self.p}&room_id={self.room['id']}", {"bed_count": 1},
                                   format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([b["id"] for b in response.data["beds"]], [self.bed2])
        response = self.client.put(f"/api/v1/pg/rooms/{self.p}&room_id={self.room['id']}", {"bed_count": 3},
                                   format="json")
        self.assertEqual(len(response.data["beds"]), 3)
        self.assertEqual(response.data["beds"][1]["occupant"]["name"], "Tenant1")

    def test_a_room_with_tenants_cant_be_removed(self):
        self.add_tenant(days(0))
        response = self.client.delete(f"/api/v1/pg/rooms/{self.p}&room_id={self.room['id']}")
        self.assertEqual(response.status_code, 400)

    def test_one_tenant_per_bed(self):
        self.add_tenant(days(0))
        response = self.client.post(f"/api/v1/pg/tenants/{self.p}",
                                    {"first_name": "B", "phone": "9123456789", "bed_id": self.bed1}, format="json")
        self.assertEqual(response.status_code, 400)


class BillTests(PgTestCase):
    def test_first_bill_is_prorated_to_the_next_due_day(self):
        tenant = self.add_tenant(date(2026, 10, 10), due_day=1)
        first = tenant["bills"][-1]
        self.assertEqual((first["period_start"], first["period_end"]), ("2026-10-10", "2026-10-31"))
        self.assertEqual(first["total"], "3548.00")  # 5,000 × 22 / 31

    def test_full_first_month_when_asked(self):
        tenant = self.add_tenant(date(2026, 10, 10), due_day=1, prorate_first_bill=False)
        self.assertEqual(tenant["bills"][-1]["total"], "5000.00")

    def test_bills_catch_up_to_today(self):
        start = add_months(days(0), -2)
        tenant = self.add_tenant(start)
        self.assertEqual(len(tenant["bills"]), 3)
        self.assertEqual(tenant["total_due"], "15000.00")
        self.assertEqual(tenant["tenancy"]["due_day"], min(start.day, 28))

    def test_payments_pay_the_oldest_bill_first_and_keep_the_rest_as_advance(self):
        tenant = self.add_tenant(add_months(days(0), -1))
        tenant = self.post("payments", {"member_id": tenant["id"], "amount": "12000", "payment_method": "UPI"})
        self.assertEqual([b["status"] for b in tenant["bills"]], ["PAID", "PAID"])
        self.assertEqual(tenant["tenancy"]["advance_balance"], "2000.00")
        self.assertEqual(Payment.objects.filter(member_id=tenant["id"]).count(), 3)  # 2 bills + advance

        # The advance pays toward the next bill.
        PgService.ensure_bills(PgTenancy.objects.get(member_id=tenant["id"]), add_months(days(0), 1))
        tenant = self.tenant(tenant["id"])
        self.assertEqual(tenant["bills"][0]["paid"], "2000.00")
        self.assertEqual(tenant["total_due"], "3000.00")

    def test_deleting_a_payment_puts_the_due_back(self):
        tenant = self.add_tenant(days(0), payment={"amount": "5000", "payment_method": "CASH"})
        self.assertEqual(tenant["total_due"], "0.00")
        payment_id = tenant["bills"][0]["payments"][0]["id"]
        self.client.delete(f"/api/v1/payments/{self.p}&payment_id={payment_id}")
        self.assertEqual(self.tenant(tenant["id"])["total_due"], "5000.00")

    def test_charges_and_discounts(self):
        tenant = self.add_tenant(days(0), charges=[{"description": "Key deposit", "amount": "300"}])
        self.assertEqual(tenant["total_due"], "5300.00")
        tenant = self.post("charges", {"member_id": tenant["id"], "description": "Laundry", "amount": "200"})
        bill_id = tenant["bills"][0]["id"]
        response = self.client.put(f"/api/v1/pg/bills/{self.p}&bill_id={bill_id}", {"discount": "500"}, format="json")
        self.assertEqual(response.data["total_due"], "5000.00")

    def test_gym_payment_endpoint_points_pg_to_rent(self):
        tenant = self.add_tenant(days(0))
        response = self.client.post(f"/api/v1/payments/{self.p}",
                                    {"member_id": tenant["id"], "amount": "100", "payment_method": "CASH"},
                                    format="json")
        self.assertEqual(response.status_code, 400)


class StayTests(PgTestCase):
    def test_shift_bed(self):
        tenant = self.add_tenant(days(0))
        tenant = self.action(tenant["id"], "shift", bed_id=self.bed2, rent="5500")
        self.assertEqual(tenant["tenancy"]["bed"]["id"], self.bed2)
        self.assertEqual(tenant["tenancy"]["rent"], "5500.00")

    def test_notice_stops_billing_after_the_leaving_date(self):
        tenant = self.add_tenant(add_months(days(0), -1))
        self.action(tenant["id"], "notice", leave_date=days(-1))
        tenancy = PgTenancy.objects.get(member_id=tenant["id"])
        PgService.ensure_bills(tenancy, add_months(days(0), 2))
        self.assertEqual(tenancy.bills.count(), 2)
        self.action(tenant["id"], "cancel_notice")
        self.assertEqual(PgTenancy.objects.get(member_id=tenant["id"]).status, "ACTIVE")

    def test_checkout_settles_the_deposit(self):
        tenant = self.add_tenant(days(0), deposit_amount="10000", deposit_paid="10000")
        tenant = self.action(tenant["id"], "checkout", leave_date=days(0), dues_from_deposit=True,
                             deduction="1000", deduction_reason="Broken chair")
        # ₹5,000 rent came out of the deposit, ₹1,000 kept, ₹4,000 back.
        self.assertEqual(tenant["checkout"]["deposit_refunded"], "4000.00")
        self.assertEqual(tenant["total_due"], "0.00")
        self.assertEqual(tenant["tenancy"]["status"], "ENDED")
        self.assertFalse(tenant["is_active"])
        self.assertIsNone(self.client.get(f"/api/v1/pg/rooms/{self.p}").data["results"][0]["beds"][0]["occupant"])

    def test_checkout_refunds_rent_paid_ahead(self):
        tenant = self.add_tenant(days(0), payment={"amount": "8000", "payment_method": "CASH"})
        tenant = self.action(tenant["id"], "checkout", leave_date=days(0))
        self.assertEqual(tenant["checkout"]["advance_refunded"], "3000.00")
        collected = sum(Payment.objects.filter(member_id=tenant["id"], is_active=True).values_list("amount", flat=True))
        self.assertEqual(collected, Decimal("5000"))

    def test_checkout_preview_changes_nothing(self):
        tenant = self.add_tenant(days(0), deposit_amount="3000", deposit_paid="3000")
        preview = self.client.get(f"/api/v1/pg/checkout-preview/{self.p}&member_id={tenant['id']}").data
        self.assertEqual((preview["dues"], preview["deposit_held"]), ("5000.00", "3000.00"))
        self.assertEqual(PgTenancy.objects.get(member_id=tenant["id"]).status, "ACTIVE")

    def test_moving_back_in(self):
        tenant = self.add_tenant(days(-40))
        self.action(tenant["id"], "checkout", leave_date=days(-10))
        tenant = self.action(tenant["id"], "move_in", bed_id=self.bed2, start_date=days(0))
        self.assertEqual(tenant["tenancy"]["status"], "ACTIVE")
        self.assertEqual(len(tenant["past_stays"]), 1)

    def test_lists_and_dashboard(self):
        self.add_tenant(days(0), payment={"amount": "5000", "payment_method": "CASH"})
        late = self.add_tenant(days(0), bed=self.bed2)
        self.action(late["id"], "notice", leave_date=days(3))
        dues = self.client.get(f"/api/v1/pg/tenants/{self.p}&has_dues=true").data["results"]
        notice = self.client.get(f"/api/v1/pg/tenants/{self.p}&status=notice").data["results"]
        self.assertEqual([t["id"] for t in dues], [late["id"]])
        self.assertEqual([t["id"] for t in notice], [late["id"]])
        dashboard = self.client.get(f"/api/v1/pg/dashboard/{self.p}").data
        self.assertEqual(dashboard["beds"], {"total": 2, "occupied": 2, "vacant": 0})
        self.assertEqual(dashboard["dues"]["total"], "5000.00")
        self.assertEqual(dashboard["tenants"]["leaving_this_week"], 1)

    def test_morning_job_makes_bills_and_reminds(self):
        tenant = self.add_tenant(add_months(days(0), -1))
        PgBill.objects.filter(member_id=tenant["id"], period_start=days(0)).delete()
        self.client.post("/api/v1/cron/daily/?run=morning")
        self.assertTrue(PgBill.objects.filter(member_id=tenant["id"], period_start=days(0)).exists())
        types = set(Notification.objects.filter(business_account=self.pg).values_list("notification_type", flat=True))
        self.assertIn("RENT_DUE", types)
        self.assertIn("MORNING_SUMMARY", types)


class ExpenseAndSalaryTests(ApiTestCase):
    def test_expenses_with_totals(self):
        for category, amount in [("RENT", "20000"), ("ELECTRICITY", "3000")]:
            response = self.client.post(f"/api/v1/expenses/{self.q}",
                                        {"category": category, "amount": amount, "description": category}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
        data = self.client.get(f"/api/v1/expenses/{self.q}&date_from={days(-1)}").data
        self.assertEqual(data["total"], "23000.00")
        self.assertEqual(data["by_category"][0]["category"], "RENT")

    def test_salary_is_one_expense_and_can_be_undone(self):
        staff = Staff.objects.create(business_account=self.account, employee_code="S1", first_name="Ravi",
                                     created_by_business_admin=self.admin, salary=12000)
        month = days(0).strftime("%Y-%m")
        response = self.client.post(f"/api/v1/staff-salaries/{self.q}",
                                    {"staff_id": staff.id, "salary_month": month, "amount": "12000"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Expense.objects.filter(is_active=True, category="SALARY").count(), 1)
        again = self.client.post(f"/api/v1/staff-salaries/{self.q}",
                                 {"staff_id": staff.id, "salary_month": month, "amount": "12000"}, format="json")
        self.assertEqual(again.status_code, 400)
        expense = Expense.objects.get()
        edit = self.client.put(f"/api/v1/expenses/{self.q}&expense_id={expense.id}", {"amount": "1"}, format="json")
        self.assertEqual(edit.status_code, 400)

        listing = self.client.get(f"/api/v1/staff-salaries/{self.q}&month={month}").data
        self.assertEqual(listing["paid"], "12000.00")
        self.client.delete(f"/api/v1/staff-salaries/{self.q}&salary_id={response.data['id']}")
        self.assertFalse(Expense.objects.filter(is_active=True).exists())
