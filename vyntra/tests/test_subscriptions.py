import base64
import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.contrib import messages
from django.contrib.admin import site as admin_site
from django.contrib.auth.hashers import check_password, make_password
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from vyntra.billing import GooglePlay, ProviderError, Razorpay
from vyntra.models import (
    BusinessAccountAdmin,
    BusinessAdmin,
    Notification,
    Subscription,
    SubscriptionPayment,
    SubscriptionPlan,
)
from vyntra.services import BusinessAdminAuthService
from vyntra.subscriptions import SubscriptionService

from .base import ApiTestCase, days

RAZORPAY = {"RAZORPAY_KEY_ID": "rzp_test_key", "RAZORPAY_KEY_SECRET": "secret", "RAZORPAY_WEBHOOK_SECRET": "hook"}


def sign(message, secret):
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def unix(moment):
    return int(moment.timestamp())


class SubscriptionTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.monthly_plan = SubscriptionPlan.objects.create(
            code="MONTHLY", name="Monthly", months=1, price=499, razorpay_plan_id="plan_m",
            google_base_plan_id="monthly", sort_order=1,
        )
        self.yearly_plan = SubscriptionPlan.objects.create(
            code="YEARLY", name="Yearly", months=12, price=4790, razorpay_plan_id="plan_y",
            google_base_plan_id="yearly", sort_order=3,
        )

    @property
    def subscription(self):
        return SubscriptionService.for_admin(self.admin)

    def end_trial(self, admin=None):
        subscription = SubscriptionService.for_admin(admin or self.admin)
        subscription.trial_ends_at = timezone.now() - timedelta(days=1)
        subscription.save()

    def login_as(self, admin):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {BusinessAdminAuthService.generate_access_token(admin)}")
        return client

    def add_admin(self):
        admin = BusinessAdmin.objects.create(
            name="Front Desk", email="desk@example.test", phone="9000000001", password=make_password("x")
        )
        BusinessAccountAdmin.objects.create(business_account=self.account, business_admin=admin, role="ADMIN")
        return admin


class TrialTests(SubscriptionTestCase):
    def test_signup_starts_a_15_day_trial(self):
        response = APIClient().post("/api/v1/auth/signup/", {
            "full_name": "New Owner", "email": "new@example.test", "mobile_no": "9876500000", "password": "Vyntra-trial-2026",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        client = self.login_as(BusinessAdmin.objects.get(email="new@example.test"))
        data = client.get("/api/v1/subscription/").data
        self.assertEqual(data["state"], "TRIAL")
        self.assertEqual(data["days_left"], 15)
        self.assertTrue(data["can_purchase"])
        self.assertEqual([p["code"] for p in data["plans"]], ["MONTHLY", "YEARLY"])

    def test_new_business_is_owned_by_its_creator(self):
        response = self.client.post("/api/v1/business-accounts/", {"business_type_id": 1, "name": "Gym 2"},
                                    format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["access"], {"is_owner": True, "owner_name": "Owner", "read_only": False})


class ReadOnlyTests(SubscriptionTestCase):
    def test_after_the_trial_the_owner_can_read_but_not_change(self):
        member = self.add_member(days(-5))
        self.end_trial()
        self.assertEqual(self.client.get(f"/api/v1/members/{self.q}").status_code, 200)
        response = self.client.put(f"/api/v1/members/{self.q}&member_id={member['id']}", {"first_name": "X"},
                                   format="json")
        self.assertEqual(response.status_code, 402)
        self.assertIn("Renew", response.data["detail"])
        self.assertEqual(self.client.post("/api/v1/business-accounts/", {"business_type_id": 1, "name": "Gym 2"},
                                          format="json").status_code, 402)
        self.assertEqual(self.client.put(f"/api/v1/business-accounts/{self.account.id}/", {"name": "New"},
                                         format="json").status_code, 402)

    def test_reading_notifications_still_works_when_read_only(self):
        self.end_trial()
        response = self.client.put(f"/api/v1/notifications/{self.q}")
        self.assertEqual(response.status_code, 204)

    def test_added_admins_follow_the_owners_subscription(self):
        desk = self.login_as(self.add_admin())
        self.assertEqual(self.client.get("/api/v1/subscription/").status_code, 200)
        self.end_trial()
        response = desk.post(f"/api/v1/members/{self.q}", {"member_code": "9", "first_name": "A",
                                                           "membership_plan_id": self.monthly.id,
                                                           "start_date": str(days(0))}, format="json")
        self.assertEqual(response.status_code, 402)
        self.assertIn("Owner's subscription has ended", response.data["detail"])
        account = desk.get(f"/api/v1/business-accounts/{self.account.id}/").data
        self.assertEqual(account["access"], {"is_owner": False, "owner_name": "Owner", "read_only": True})

    def test_a_renewal_failure_keeps_access_for_the_grace_period(self):
        self.end_trial()
        subscription = self.subscription
        subscription.current_period_end = timezone.now() - timedelta(days=1)
        subscription.auto_renew = True
        subscription.save()
        self.assertEqual(SubscriptionService.state(subscription), "GRACE")
        self.add_member(days(0))

    def test_free_days_from_django_admin_unlock_changes(self):
        self.end_trial()
        SubscriptionService.extend(self.subscription, 7)
        self.assertEqual(SubscriptionService.state(self.subscription), "CANCELLED")
        self.assertEqual(self.client.get("/api/v1/subscription/").data["days_left"], 7)
        self.add_member(days(0))


class OwnershipTests(SubscriptionTestCase):
    def test_the_owner_cant_be_removed(self):
        desk = self.login_as(self.add_admin())
        response = desk.put(f"/api/v1/admins/{self.q}&admin_id={self.admin.id}", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_an_admin_can_be_removed_from_the_business(self):
        desk = self.add_admin()
        response = self.client.delete(f"/api/v1/admins/{self.q}&admin_id={desk.id}")
        self.assertEqual(response.status_code, 204)
        admins = self.client.get(f"/api/v1/admins/{self.q}").data["results"]
        self.assertNotIn(desk.id, [a["admin"]["id"] for a in admins])
        removed = self.login_as(desk)
        self.assertEqual(removed.get(f"/api/v1/members/{self.q}").status_code, 403)

    def test_the_owner_and_yourself_cant_be_removed(self):
        desk = self.login_as(self.add_admin())
        self.assertEqual(desk.delete(f"/api/v1/admins/{self.q}&admin_id={self.admin.id}").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/v1/admins/{self.q}&admin_id={self.admin.id}").status_code, 400)

    def test_changing_your_password_needs_no_current_password_and_signs_out_other_devices(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {BusinessAdminAuthService.generate_access_token(self.admin)}")
        other_phone = self.login_as(self.admin)
        response = self.client.put("/api/v1/me/password/", {"new_password": "brand-new-pass-9"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(other_phone.get("/api/v1/me/").status_code, 401)
        this_phone = APIClient()
        this_phone.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}")
        self.assertEqual(this_phone.get("/api/v1/me/").status_code, 200)

    def test_setting_another_admins_password(self):
        desk = self.add_admin()
        desk_phone = self.login_as(desk)
        response = self.client.put(f"/api/v1/admins/password/{self.q}&admin_id={desk.id}",
                                   {"new_password": "front-desk-pass-9"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        desk.refresh_from_db()
        self.assertTrue(check_password("front-desk-pass-9", desk.password))
        self.assertEqual(desk_phone.get("/api/v1/me/").status_code, 401)

        # Nobody can set the owner's password, and your own goes through My Profile.
        self.assertEqual(desk_phone.put(f"/api/v1/admins/password/{self.q}&admin_id={self.admin.id}",
                                        {"new_password": "x-owner-pass-9"}, format="json").status_code, 401)
        desk_again = self.login_as(desk)
        self.assertEqual(desk_again.put(f"/api/v1/admins/password/{self.q}&admin_id={self.admin.id}",
                                        {"new_password": "x-owner-pass-9"}, format="json").status_code, 400)
        self.assertEqual(self.client.put(f"/api/v1/admins/password/{self.q}&admin_id={self.admin.id}",
                                         {"new_password": "x-owner-pass-9"}, format="json").status_code, 400)

    def test_deleting_the_owners_login_hands_the_business_to_the_next_admin(self):
        desk = self.add_admin()
        self.assertEqual(self.client.delete("/api/v1/me/").status_code, 204)
        self.assertEqual(SubscriptionService.owner_of(self.account.id), desk)


class RemindersTests(SubscriptionTestCase):
    def test_owner_is_reminded_3_days_before_the_trial_ends_once_a_day(self):
        subscription = self.subscription
        subscription.trial_ends_at = timezone.now() + timedelta(days=3)
        subscription.save()
        for _ in range(2):
            self.client.post("/api/v1/cron/daily/?run=morning")
        reminders = Notification.objects.filter(business_admin=self.admin, notification_type="SUBSCRIPTION")
        self.assertEqual([n.title for n in reminders], ["Your free trial ends in 3 days"])


@override_settings(**RAZORPAY)
class RazorpayTests(SubscriptionTestCase):
    def razorpay_subscription(self, status="active", start=None, months=1):
        start = start or timezone.now()
        return {
            "id": "sub_1", "plan_id": "plan_m", "status": status, "notes": {"business_admin_id": str(self.admin.id)},
            "current_start": unix(start), "current_end": unix(start + timedelta(days=30 * months)),
        }

    def payment(self, payment_id="pay_1"):
        return {"id": payment_id, "amount": 49900, "currency": "INR", "status": "captured",
                "created_at": unix(timezone.now())}

    def webhook(self, event, entity, payment=None, secret="hook"):
        payload = {"subscription": {"entity": entity}}
        if payment:
            payload["payment"] = {"entity": payment}
        body = json.dumps({"event": event, "payload": payload}).encode()
        return APIClient().post("/api/v1/webhooks/razorpay/", body, content_type="application/json",
                                HTTP_X_RAZORPAY_SIGNATURE=sign(body, secret))

    def test_checkout_then_confirm_unlocks_the_plan(self):
        with mock.patch.object(Razorpay, "_request", return_value={"id": "sub_1"}) as request:
            response = self.client.post("/api/v1/subscription/razorpay/", {"plan_code": "MONTHLY"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["subscription_id"], "sub_1")
        self.assertEqual(request.call_args.args[2]["notes"]["business_admin_id"], str(self.admin.id))

        self.end_trial()
        with mock.patch.object(Razorpay, "fetch_subscription", return_value=self.razorpay_subscription()), \
                mock.patch.object(Razorpay, "fetch_payment", return_value=self.payment()):
            response = self.client.post("/api/v1/subscription/razorpay/confirm/", {
                "razorpay_payment_id": "pay_1", "razorpay_subscription_id": "sub_1",
                "razorpay_signature": sign(b"pay_1|sub_1", "secret"),
            }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["state"], "ACTIVE")
        self.assertEqual(response.data["plan"]["code"], "MONTHLY")
        self.assertFalse(response.data["can_purchase"])
        self.assertEqual(response.data["payments"][0]["amount"], "499.00")
        self.add_member(days(0))

    def test_confirm_with_a_wrong_signature_is_refused(self):
        response = self.client.post("/api/v1/subscription/razorpay/confirm/", {
            "razorpay_payment_id": "pay_1", "razorpay_subscription_id": "sub_1", "razorpay_signature": "forged",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SubscriptionService.state(self.subscription), "TRIAL")

    def test_renewal_webhook_extends_and_is_counted_once(self):
        self.assertEqual(self.webhook("subscription.charged", self.razorpay_subscription(), self.payment())
                         .status_code, 200)
        later = timezone.now() + timedelta(days=30)
        renewal = self.razorpay_subscription(start=later)
        for _ in range(2):
            self.webhook("subscription.charged", renewal, self.payment("pay_2"))
        self.assertEqual(SubscriptionPayment.objects.count(), 2)
        self.assertEqual(unix(self.subscription.current_period_end), renewal["current_end"])

    def test_webhook_with_a_bad_signature_is_ignored(self):
        response = self.webhook("subscription.charged", self.razorpay_subscription(), self.payment(), secret="x")
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.subscription.provider)

    def test_halted_subscription_stops_renewing(self):
        self.webhook("subscription.charged", self.razorpay_subscription(), self.payment())
        self.webhook("subscription.halted", self.razorpay_subscription(status="halted"))
        self.assertEqual(self.subscription.status, Subscription.EXPIRED)
        self.assertFalse(self.subscription.auto_renew)

    def save_in_django_admin(self, plan, **changes):
        for field, value in changes.items():
            setattr(plan, field, value)
        model_admin = admin_site._registry[SubscriptionPlan]
        with mock.patch.object(model_admin, "message_user") as message:
            model_admin.save_model(RequestFactory().post("/"), plan, form=None, change=True)
        plan.refresh_from_db()
        return message

    def test_changing_the_price_in_django_admin_creates_a_new_razorpay_plan(self):
        with mock.patch.object(Razorpay, "_request", return_value={"id": "plan_m2"}) as request:
            self.save_in_django_admin(self.monthly_plan, price=599)
        self.assertEqual(self.monthly_plan.razorpay_plan_id, "plan_m2")
        self.assertEqual(request.call_args.args[2]["item"]["amount"], 59900)

        with mock.patch.object(Razorpay, "_request") as request:
            self.save_in_django_admin(self.monthly_plan, name="Monthly plan")
        request.assert_not_called()
        self.assertEqual(self.monthly_plan.razorpay_plan_id, "plan_m2")

    def test_a_refused_razorpay_plan_turns_off_payment_instead_of_charging_the_old_price(self):
        with mock.patch.object(Razorpay, "_request", side_effect=ProviderError("bad")):
            message = self.save_in_django_admin(self.monthly_plan, price=599)
        self.assertIsNone(self.monthly_plan.razorpay_plan_id)
        self.assertEqual(self.monthly_plan.price, 599)
        self.assertEqual(message.call_args.args[2], messages.ERROR)

    def test_renewals_on_the_old_razorpay_plan_still_count_after_a_price_change(self):
        self.monthly_plan.razorpay_plan_id = "plan_m2"
        self.monthly_plan.save()
        old_plan_renewal = {**self.razorpay_subscription(), "notes": {
            "business_admin_id": str(self.admin.id), "plan_code": "MONTHLY"}}
        self.webhook("subscription.charged", old_plan_renewal, self.payment())
        self.assertEqual(self.subscription.provider, Subscription.RAZORPAY)
        self.assertEqual(self.subscription.plan, self.monthly_plan)

    def cancel_paid_plan(self):
        self.webhook("subscription.charged", self.razorpay_subscription(), self.payment())
        with mock.patch.object(Razorpay, "cancel_subscription"):
            self.client.post("/api/v1/subscription/cancel/")
        return self.subscription.current_period_end

    def test_buying_after_cancelling_starts_when_the_paid_days_run_out(self):
        paid_until = self.cancel_paid_plan()
        with mock.patch.object(Razorpay, "_request", return_value={"id": "sub_2"}) as request:
            response = self.client.post("/api/v1/subscription/razorpay/", {"plan_code": "YEARLY"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(request.call_args.args[2]["start_at"], unix(paid_until))

        scheduled = {
            "id": "sub_2", "plan_id": "plan_y", "status": "authenticated", "start_at": unix(paid_until),
            "current_start": None, "current_end": None,
            "notes": {"business_admin_id": str(self.admin.id), "plan_code": "YEARLY"},
        }
        with mock.patch.object(Razorpay, "fetch_subscription", return_value=scheduled):
            response = self.client.post("/api/v1/subscription/razorpay/sync/", {"subscription_id": "sub_2"},
                                        format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["state"], "ACTIVE")
        self.assertEqual(response.data["plan"]["code"], "YEARLY")
        self.assertEqual(self.subscription.current_period_end, paid_until)
        self.assertEqual(SubscriptionPayment.objects.count(), 1)

        # The first charge on the new plan arrives when the old period ends.
        first_charge = {**scheduled, "status": "active", "current_start": unix(paid_until),
                        "current_end": unix(paid_until + timedelta(days=365))}
        self.webhook("subscription.charged", first_charge, self.payment("pay_2"))
        self.assertEqual(unix(self.subscription.current_period_end), first_charge["current_end"])
        self.assertEqual(SubscriptionPayment.objects.count(), 2)

    def test_the_old_cancelled_subscription_cant_undo_the_scheduled_one(self):
        self.cancel_paid_plan()
        scheduled = {"id": "sub_2", "plan_id": "plan_m", "status": "authenticated",
                     "start_at": unix(timezone.now() + timedelta(days=30)),
                     "notes": {"business_admin_id": str(self.admin.id), "plan_code": "MONTHLY"}}
        self.webhook("subscription.authenticated", scheduled)
        self.webhook("subscription.cancelled", self.razorpay_subscription(status="cancelled"))
        self.assertTrue(self.subscription.auto_renew)

    def test_syncing_someone_elses_subscription_is_refused(self):
        other = {"id": "sub_x", "status": "active", "notes": {"business_admin_id": "999"}}
        with mock.patch.object(Razorpay, "fetch_subscription", return_value=other):
            response = self.client.post("/api/v1/subscription/razorpay/sync/", {"subscription_id": "sub_x"},
                                        format="json")
        self.assertEqual(response.status_code, 400)

    def test_each_payment_has_a_receipt(self):
        self.webhook("subscription.charged", self.razorpay_subscription(), {**self.payment(), "method": "upi"})
        payment = self.client.get("/api/v1/subscription/").data["payments"][0]
        self.assertEqual(payment["method"], "UPI")
        self.assertTrue(payment["receipt_number"].startswith("VYN-"))

        page = APIClient().get(f"/receipts/{payment['receipt_token']}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, payment["receipt_number"])
        self.assertContains(page, "₹499.00")
        self.assertContains(page, "UPI")
        self.assertContains(page, self.admin.name)
        self.assertEqual(APIClient().get("/receipts/forged/").status_code, 404)

    def test_cancel_keeps_the_paid_days(self):
        self.webhook("subscription.charged", self.razorpay_subscription(), self.payment())
        with mock.patch.object(Razorpay, "cancel_subscription") as cancel:
            response = self.client.post("/api/v1/subscription/cancel/")
        cancel.assert_called_once_with("sub_1")
        self.assertEqual(response.data["state"], "CANCELLED")
        self.assertTrue(response.data["has_access"])
        self.assertTrue(response.data["can_purchase"])


@override_settings(GOOGLE_PLAY_SERVICE_ACCOUNT_JSON="{}", GOOGLE_PLAY_RTDN_TOKEN="rtdn")
class GooglePlayTests(SubscriptionTestCase):
    def purchase(self, state="SUBSCRIPTION_STATE_ACTIVE", renewing=True, order="GPA.1"):
        expiry = (timezone.now() + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return {
            "subscriptionState": state, "latestOrderId": order,
            "acknowledgementState": "ACKNOWLEDGEMENT_STATE_PENDING",
            "externalAccountIdentifiers": {"obfuscatedExternalAccountId": str(self.admin.id)},
            "lineItems": [{
                "productId": "vyntra_pro", "expiryTime": expiry, "offerDetails": {"basePlanId": "yearly"},
                "autoRenewingPlan": {"autoRenewEnabled": renewing,
                                     "recurringPrice": {"currencyCode": "INR", "units": "4790"}},
            }],
        }

    def test_purchase_in_the_app_unlocks_the_plan_and_is_acknowledged(self):
        with mock.patch.object(GooglePlay, "fetch_subscription", return_value=self.purchase()), \
                mock.patch.object(GooglePlay, "acknowledge") as acknowledge:
            response = self.client.post("/api/v1/subscription/google-play/confirm/", {"purchase_token": "tok"},
                                        format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["state"], "ACTIVE")
        self.assertEqual(response.data["provider"], "GOOGLE_PLAY")
        self.assertEqual(response.data["plan"]["code"], "YEARLY")
        acknowledge.assert_called_once_with("vyntra_pro", "tok")

    def test_someone_elses_purchase_is_refused(self):
        purchase = self.purchase()
        purchase["externalAccountIdentifiers"]["obfuscatedExternalAccountId"] = "999"
        with mock.patch.object(GooglePlay, "fetch_subscription", return_value=purchase):
            response = self.client.post("/api/v1/subscription/google-play/confirm/", {"purchase_token": "tok"},
                                        format="json")
        self.assertEqual(response.status_code, 400)

    def test_cancelled_in_play_store_then_expired(self):
        def notify(purchase):
            data = base64.b64encode(json.dumps({"subscriptionNotification": {"purchaseToken": "tok"}}).encode())
            with mock.patch.object(GooglePlay, "fetch_subscription", return_value=purchase), \
                    mock.patch.object(GooglePlay, "acknowledge"):
                return APIClient().post("/api/v1/webhooks/google-play/?token=rtdn",
                                        {"message": {"data": data.decode()}}, format="json")

        self.assertEqual(notify(self.purchase()).status_code, 204)
        notify(self.purchase(state="SUBSCRIPTION_STATE_CANCELED", renewing=False))
        self.assertEqual(SubscriptionService.state(self.subscription), "CANCELLED")
        notify(self.purchase(state="SUBSCRIPTION_STATE_EXPIRED", renewing=False))
        self.assertEqual(self.subscription.status, Subscription.EXPIRED)
        self.assertEqual(SubscriptionPayment.objects.count(), 1)

    def test_notifications_without_the_secret_are_refused(self):
        response = APIClient().post("/api/v1/webhooks/google-play/?token=wrong", {"message": {}}, format="json")
        self.assertEqual(response.status_code, 403)
