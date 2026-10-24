from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from vyntra import whatsapp
from vyntra.models import Membership, WhatsAppMessage
from vyntra.services import MemberService, NotificationService

from .base import ApiTestCase, days

WHATSAPP = {"WHATSAPP_TOKEN": "token", "WHATSAPP_PHONE_NUMBER_ID": "12345", "WHATSAPP_MONTHLY_LIMIT": 500}


@override_settings(**WHATSAPP)
class WhatsAppTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.post = mock.patch.object(whatsapp, "_post", return_value="wamid.1").start()
        self.addCleanup(mock.patch.stopall)

    def ending_in(self, n, **fields):
        """A member whose plan ends n days from today."""
        member = self.add_member(days(-5), paid=1000, **fields)
        Membership.objects.filter(member_id=member["id"]).update(end_date=days(n))
        return member

    def turn_on(self, **switches):
        response = self.client.put(f"/api/v1/whatsapp-settings/{self.q}", {"enabled": True, **switches},
                                   format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def test_nothing_is_sent_until_the_owner_turns_it_on(self):
        self.ending_in(3, phone="9876543210")
        NotificationService.run_daily("morning")
        self.post.assert_not_called()
        self.assertFalse(self.client.get(f"/api/v1/whatsapp-settings/{self.q}").data["enabled"])

    def test_morning_expiry_reminder_once_a_day(self):
        self.turn_on()
        member = self.ending_in(3, phone="9876543210", first_name="Rahul Kumar")
        NotificationService.run_daily("morning")
        self.post.assert_called_once()
        phone, template, params = self.post.call_args.args
        self.assertEqual((phone, template), ("9876543210", "vyntra_plan_expiring"))
        self.assertEqual(params[0], "Rahul")
        self.assertEqual(WhatsAppMessage.objects.get().member_id, member["id"])

        WhatsAppMessage.objects.update(sent_date=timezone.localdate())
        NotificationService._morning(self.account.id, timezone.localdate())  # same day again
        self.assertEqual(self.post.call_count, 1)

    def test_payment_receipt_and_switches(self):
        self.turn_on()
        with self.captureOnCommitCallbacks(execute=True):
            self.add_member(days(0), phone="9876543210", paid=400)
        template, params = self.post.call_args.args[1:]
        self.assertEqual(template, "vyntra_payment_received")
        self.assertEqual((params[1], params[4]), ("₹400", "₹600"))

        self.turn_on(payment_receipts=False)
        with self.captureOnCommitCallbacks(execute=True):
            self.add_member(days(0), phone="9876543211", paid=400, member_code="M2")
        self.assertEqual(self.post.call_count, 1)

    def test_no_phone_no_subscription_or_over_the_limit_sends_nothing(self):
        self.turn_on()
        with self.captureOnCommitCallbacks(execute=True):
            self.add_member(days(0), paid=100)  # no phone
        self.post.assert_not_called()

        with override_settings(WHATSAPP_MONTHLY_LIMIT=0), self.captureOnCommitCallbacks(execute=True):
            self.add_member(days(0), phone="9876543210", paid=100, member_code="M3")
        self.post.assert_not_called()

    def test_failures_are_logged_and_only_the_owner_changes_settings(self):
        self.turn_on()
        self.post.side_effect = RuntimeError("template not approved")
        with self.captureOnCommitCallbacks(execute=True):
            self.add_member(days(0), phone="9876543210", paid=100)
        message = WhatsAppMessage.objects.get()
        self.assertEqual((message.status, message.error), ("FAILED", "template not approved"))
        settings = self.client.get(f"/api/v1/whatsapp-settings/{self.q}").data
        self.assertEqual((settings["available"], settings["sent_this_month"]), (True, 0))

    def test_dues_on_mondays_and_birthdays(self):
        self.turn_on()
        today = timezone.localdate()
        monday = today - timedelta(days=today.weekday())
        self.add_member(monday.isoformat(), phone="9876543210", paid=100,
                        date_of_birth=monday.replace(year=1995).isoformat())
        whatsapp.run_morning(self.account.id, list(MemberService.get_members(self.account.id)), monday)
        templates = sorted(call.args[1] for call in self.post.call_args_list)
        self.assertEqual(templates, ["vyntra_birthday_wish", "vyntra_dues_pending"])
