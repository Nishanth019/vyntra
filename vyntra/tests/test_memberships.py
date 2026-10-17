from datetime import date, timedelta

from vyntra.models import Membership, Payment

from .base import ApiTestCase, days


def after(iso_date, n=1):
    """The date n days after a YYYY-MM-DD string, as a string."""
    return str(date.fromisoformat(iso_date) + timedelta(days=n))


class JoiningTests(ApiTestCase):
    def test_new_member_is_active_with_dues_on_their_plan(self):
        m = self.add_member(days(-5), paid=400)
        self.assertEqual(m["status"], "live")
        self.assertEqual(m["total_due"], "600.00")

    def test_member_starting_later_is_upcoming(self):
        m = self.add_member(days(3))
        self.assertEqual(m["status"], "upcoming")

    def test_lookup_by_phone_and_email(self):
        m = self.add_member(days(0), phone="9876543210", email="Ravi@Example.test")
        self.assertEqual(self.members(phone="9876543210"), [m["id"]])
        self.assertEqual(self.members(email="ravi@example.test"), [m["id"]])


class RenewTests(ApiTestCase):
    def test_renew_is_refused_for_an_active_member(self):
        m = self.add_member(days(-5))
        response = self.action(m, "renew")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Change Plan", response.data["detail"])

    def test_renew_an_expired_member_counts_only_the_new_plan(self):
        m = self.add_member(days(-40), paid=200)  # ₹800 left unpaid on the old plan
        self.assertEqual(self.member(m["id"])["status"], "expired")
        response = self.action(m, "renew", plan=self.quarterly, payment={"amount": "700", "payment_method": "UPI"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "live")
        self.assertEqual(response.data["membership"]["start_date"], str(days(0)))
        self.assertEqual(response.data["total_due"], "2000.00")

    def test_inactive_member_with_running_plan_is_reactivated_not_renewed(self):
        m = self.add_member(days(-5))
        self.client.delete(f"/api/v1/members/{self.q}&member_id={m['id']}")
        response = self.action(m, "renew")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Reactivate", response.data["detail"])
        reactivated = self.client.put(f"/api/v1/members/{self.q}&member_id={m['id']}", {"is_active": True}, format="json")
        self.assertEqual(reactivated.data["status"], "live")


class ChangePlanTests(ApiTestCase):
    def test_change_plan_replaces_the_current_plan_and_ignores_old_payments(self):
        m = self.add_member(days(-10), paid=1000)
        old_id = m["membership"]["id"]
        response = self.action(m, "change_plan", plan=self.quarterly, start_date=days(0))
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual(data["membership"]["membership_plan"]["name"], "Quarterly")
        self.assertEqual(data["membership"]["start_date"], str(days(0)))
        self.assertEqual(data["total_due"], "2700.00")  # the ₹1,000 paid on the old plan doesn't count
        self.assertIsNone(data["next_membership"])
        self.assertEqual(Membership.objects.get(id=old_id).end_date, days(-1))

    def test_change_plan_can_start_on_the_old_plans_start_date(self):
        m = self.add_member(days(-10))
        response = self.action(m, "change_plan", plan=self.quarterly, start_date=days(-10))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["membership"]["membership_plan"]["name"], "Quarterly")
        self.assertEqual(response.data["total_due"], "2700.00")

    def test_change_plan_cannot_start_in_the_future_or_before_the_current_plan(self):
        m = self.add_member(days(-10))
        for start in (days(1), days(-11)):
            response = self.action(m, "change_plan", start_date=start)
            self.assertEqual(response.status_code, 400, start)

    def test_change_plan_is_refused_for_expired_members(self):
        m = self.add_member(days(-40))
        self.assertEqual(self.action(m, "change_plan").status_code, 400)

    def test_change_plan_of_a_plan_that_has_not_started(self):
        m = self.add_member(days(5))
        response = self.action(m, "change_plan", plan=self.quarterly, start_date=days(5))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["membership"]["membership_plan"]["name"], "Quarterly")


class FuturePlanTests(ApiTestCase):
    def ending_soon(self, paid=None):
        """A member whose Monthly plan ends in 3–5 days (depending on the month's length)."""
        return self.add_member(days(-26), paid=paid)

    def test_future_plan_only_in_the_last_7_days(self):
        m = self.add_member(days(-10))
        response = self.action(m, "renew_early")
        self.assertEqual(response.status_code, 400)
        self.assertIn("last 7 days", response.data["detail"])

    def test_future_plan_starts_after_the_current_one(self):
        m = self.ending_soon(paid=600)
        end = m["membership"]["end_date"]
        response = self.action(m, "renew_early", plan=self.quarterly, payment={"amount": "500", "payment_method": "UPI"})
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual(data["membership"]["end_date"], end)  # current plan unchanged
        self.assertEqual(data["next_membership"]["start_date"], after(end))
        self.assertEqual(data["status"], "live")
        self.assertEqual(data["total_due"], "400.00")  # current plan only

    def test_future_plan_must_not_overlap_and_may_leave_a_gap(self):
        m = self.ending_soon()
        end = m["membership"]["end_date"]
        self.assertEqual(self.action(m, "renew_early", start_date=end).status_code, 400)
        response = self.action(m, "renew_early", start_date=days(12))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["next_membership"]["start_date"], str(days(12)))

    def test_only_one_future_plan(self):
        m = self.ending_soon()
        self.assertEqual(self.action(m, "renew_early").status_code, 201)
        self.assertEqual(self.action(m, "renew_early", start_date=days(40)).status_code, 400)

    def test_renewed_member_leaves_the_expiring_list(self):
        renewed, waiting = self.ending_soon(), self.ending_soon()
        self.action(renewed, "renew_early")
        expiring = self.members(is_active="true", end_date_from=days(0), end_date_to=days(7))
        self.assertNotIn(renewed["id"], expiring)
        self.assertIn(waiting["id"], expiring)

    def test_extending_the_current_plan_moves_the_future_plan(self):
        m = self.ending_soon()
        data = self.action(m, "renew_early").data
        end = data["membership"]["end_date"]
        response = self.update_membership(data["membership"]["id"], extend_days=3)
        self.assertEqual(response.data["membership"]["end_date"], after(end, 3))
        self.assertEqual(response.data["next_membership"]["start_date"], after(end, 4))

    def test_editing_the_current_start_date_moves_the_future_plan(self):
        m = self.ending_soon()
        data = self.action(m, "renew_early").data
        response = self.update_membership(data["membership"]["id"], start_date=days(-20))
        current, future = response.data["membership"], response.data["next_membership"]
        self.assertGreater(future["start_date"], current["end_date"])

    def test_future_plan_start_cannot_be_edited_into_the_current_plan(self):
        m = self.ending_soon()
        data = self.action(m, "renew_early").data
        response = self.update_membership(data["next_membership"]["id"], start_date=days(2))
        self.assertEqual(response.status_code, 400)

    def test_changing_the_current_plan_keeps_the_future_plan(self):
        m = self.ending_soon()
        future = self.action(m, "renew_early").data["next_membership"]
        response = self.action(m, "change_plan", plan=self.quarterly, start_date=days(0))
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual(data["membership"]["membership_plan"]["name"], "Quarterly")
        self.assertEqual(data["next_membership"]["id"], future["id"])
        self.assertGreater(data["next_membership"]["start_date"], data["membership"]["end_date"])

    def test_cancel_a_future_plan_with_payments(self):
        m = self.ending_soon()
        future = self.action(
            m, "renew_early", payment={"amount": "1000", "payment_method": "CASH"}
        ).data["next_membership"]
        response = self.client.delete(f"/api/v1/memberships/{self.q}&membership_id={future['id']}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["next_membership"])
        self.assertEqual(response.data["status"], "live")
        self.assertFalse(Payment.objects.filter(member_id=m["id"], amount=1000, is_active=True).exists())

    def test_renew_is_refused_while_a_future_plan_waits(self):
        m = self.ending_soon()
        self.action(m, "renew_early")
        self.assertEqual(self.action(m, "renew").status_code, 400)

    def test_gap_before_the_future_plan(self):
        """After the current plan ends the member waits for the future plan; they're not expired."""
        m = self.add_member(days(-35))  # ended 6 days ago
        current = Membership.objects.get(id=m["membership"]["id"])
        Membership.objects.create(
            business_account=self.account, member_id=m["id"], membership_plan=self.monthly,
            start_date=days(3), end_date=days(32), amount=1000, discount=0, is_active=True,
        )
        current.is_active = False
        current.save()
        data = self.member(m["id"])
        self.assertEqual(data["status"], "upcoming")
        self.assertEqual(data["membership"]["start_date"], str(days(3)))
