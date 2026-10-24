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
