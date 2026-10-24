from vyntra.models import Member, Notification

from .base import ApiTestCase, days


class DailyJobTests(ApiTestCase):
    def run_job(self, run):
        response = self.client.post(f"/api/v1/cron/daily/?run={run}")
        self.assertEqual(response.status_code, 200, response.data)

    def test_expired_a_week_ago_moves_to_inactive_and_runs_once_a_day(self):
        stale = self.add_member(days(-40))  # ended 11 days ago
        recent = self.add_member(days(-33))  # ended 4 days ago
        self.run_job("morning")
        self.run_job("morning")
        self.assertFalse(Member.objects.get(id=stale["id"]).is_active)
        self.assertTrue(Member.objects.get(id=recent["id"]).is_active)
        self.assertEqual(
            Notification.objects.filter(business_account=self.account, notification_type="MORNING_SUMMARY").count(), 1
        )

    def test_member_waiting_for_a_future_plan_is_not_moved_to_inactive(self):
        m = self.add_member(days(-26))
        self.action(m, "renew_early", start_date=days(30))
        self.run_job("morning")
        self.assertTrue(Member.objects.get(id=m["id"]).is_active)

    def test_evening_summary(self):
        self.add_member(days(0), paid=500)
        self.run_job("evening")
        summary = Notification.objects.get(business_account=self.account, notification_type="EVENING_SUMMARY")
        self.assertIn("₹500", summary.message)

    def test_no_evening_summary_on_a_quiet_day(self):
        self.run_job("evening")
        self.assertFalse(Notification.objects.filter(notification_type="EVENING_SUMMARY").exists())


class DashboardTests(ApiTestCase):
    def test_counts_and_dues(self):
        self.add_member(days(-5), paid=1000)  # active, paid
        self.add_member(days(-5), paid=300)  # active, ₹700 due
        self.add_member(days(-40))  # expired
        data = self.client.get(f"/api/v1/dashboard/{self.q}").data
        self.assertEqual(data["members"]["all"], 3)
        self.assertEqual(data["members"]["live"], 2)
        self.assertEqual(data["members"]["expired"], 1)
        self.assertEqual(data["members"]["dues"], 2)
        self.assertEqual(data["collections"]["outstanding_dues"], "1700.00")

    def test_insights_period(self):
        self.add_member(days(-2), paid=1000)
        data = self.client.get(f"/api/v1/insights/{self.q}&date_from={days(-6)}&date_to={days(0)}").data
        self.assertEqual(data["summary"]["new_members"]["value"], 1)
        self.assertEqual(len(data["series"]), 7)
