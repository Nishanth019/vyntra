from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from vyntra.models import (
    BusinessAccount,
    BusinessAccountAdmin,
    BusinessAdmin,
    BusinessType,
    DurationType,
    MembershipPlan,
)
from vyntra.services import BusinessAdminAuthService


def days(n):
    """Today + n days (negative for the past)."""
    return timezone.localdate() + timedelta(days=n)


class ApiTestCase(TestCase):
    """A gym with an admin logged in, a Monthly (₹1,000) and a Quarterly (₹2,700) plan."""

    def setUp(self):
        self.admin = BusinessAdmin.objects.create(
            name="Owner", email="owner@example.test", phone="9000000000", password=make_password("x"), is_active=True
        )
        self.account = BusinessAccount.objects.create(business_type=BusinessType.objects.get(code="GYM"), name="Gym")
        BusinessAccountAdmin.objects.create(
            business_account=self.account, business_admin=self.admin, role="ADMIN", is_active=True
        )
        month = DurationType.objects.get(code="MONTH")
        self.monthly = MembershipPlan.objects.create(
            business_account=self.account, name="Monthly", duration_type=month, duration_value=1, amount=1000
        )
        self.quarterly = MembershipPlan.objects.create(
            business_account=self.account, name="Quarterly", duration_type=month, duration_value=3, amount=2700
        )
        self.client = APIClient()
        token = BusinessAdminAuthService.generate_access_token(self.admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.q = f"?business_account_id={self.account.id}"
        self.codes = 0

    def add_member(self, start, plan=None, paid=None, **fields):
        """Adds a member through the API, optionally with a first payment."""
        self.codes += 1
        body = {
            "member_code": str(self.codes),
            "first_name": f"Member{self.codes}",
            "membership_plan_id": (plan or self.monthly).id,
            "start_date": str(start),
            **fields,
        }
        if paid:
            body["payment"] = {"amount": str(paid), "payment_method": "CASH"}
        response = self.client.post(f"/api/v1/members/{self.q}", body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def member(self, member_id):
        return self.client.get(f"/api/v1/members/{self.q}&member_id={member_id}").data

    def action(self, member, action, plan=None, **fields):
        body = {"action": action, "member_id": member["id"], "membership_plan_id": (plan or self.monthly).id}
        body.update({k: str(v) if hasattr(v, "isoformat") else v for k, v in fields.items()})
        return self.client.post(f"/api/v1/memberships/{self.q}", body, format="json")

    def update_membership(self, membership_id, **fields):
        body = {k: str(v) if hasattr(v, "isoformat") else v for k, v in fields.items()}
        return self.client.put(f"/api/v1/memberships/{self.q}&membership_id={membership_id}", body, format="json")

    def members(self, **params):
        query = "".join(f"&{k}={v}" for k, v in params.items())
        return [m["id"] for m in self.client.get(f"/api/v1/members/{self.q}{query}").data["results"]]
