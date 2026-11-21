from vyntra.models import SubscriptionPlan

from .base import ApiTestCase


class LandingPageTests(ApiTestCase):
    def test_landing_page_shows_live_prices(self):
        SubscriptionPlan.objects.create(code="MONTHLY", name="Monthly", months=1, price=999, sort_order=1)
        SubscriptionPlan.objects.create(code="YEARLY", name="Yearly", months=12, price=9590, sort_order=4)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₹9,590")
        self.assertContains(response, "Save 20%")
        self.assertContains(response, "/signup")


class GetAppLinkTests(ApiTestCase):
    ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Instagram 300.0"
    IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Instagram 300.0"

    def test_android_goes_to_play_store_with_referrer(self):
        response = self.client.get("/get/?utm_source=instagram&utm_campaign=launch", HTTP_USER_AGENT=self.ANDROID)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://play.google.com/store/apps/details?id=com.manaze.app"))
        self.assertIn("referrer=utm_source%3Dinstagram%26utm_campaign%3Dlaunch", response["Location"])

    def test_iphone_and_desktop_go_to_landing_page(self):
        response = self.client.get("/get/?utm_source=instagram", HTTP_USER_AGENT=self.IPHONE)
        self.assertEqual(response["Location"], "/?utm_source=instagram")
        self.assertEqual(self.client.get("/get/")["Location"], "/")
