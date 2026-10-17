from .base import ApiTestCase, days


class PhoneNumberTests(ApiTestCase):
    def create(self, **fields):
        body = {"member_code": "P1", "first_name": "Phone", "membership_plan_id": self.monthly.id, **fields}
        return self.client.post(f"/api/v1/members/{self.q}", body, format="json")

    def test_invalid_mobile_numbers_are_refused(self):
        for phone in ["12345", "98765432", "5876543210", "98765432101", "98765abcde", "+1 202 555 0143"]:
            response = self.create(phone=phone)
            self.assertEqual(response.status_code, 400, phone)
            self.assertIn("10-digit mobile", str(response.data["phone"]))
        response = self.create(phone="9876543210", emergency_contact_phone="12345")
        self.assertEqual(response.status_code, 400)
        self.assertIn("emergency_contact_phone", response.data)

    def test_valid_numbers_are_stored_as_10_digits(self):
        response = self.create(phone="+91 98765-43210", emergency_contact_phone="09123456789")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["phone"], "9876543210")
        self.assertEqual(response.data["gym_details"]["emergency_contact_phone"], "9123456789")

    def test_phone_is_optional(self):
        self.assertEqual(self.create(phone="").status_code, 201)

    def test_organisation_and_staff_numbers(self):
        account = self.client.put(
            f"/api/v1/business-accounts/{self.account.id}/", {"contact_no": "1800 123"}, format="json"
        )
        self.assertEqual(account.status_code, 400)
        staff = self.client.post(
            f"/api/v1/staff/{self.q}",
            {"employee_code": "S1", "first_name": "Coach", "phone": "4444444444"},
            format="json",
        )
        self.assertEqual(staff.status_code, 400)

    def test_signup_mobile(self):
        body = {"full_name": "New", "email": "new@example.test", "password": "a-Strong-pass-123"}
        bad = self.client.post("/api/v1/auth/signup/", {**body, "mobile_no": "0000000000"}, format="json")
        self.assertEqual(bad.status_code, 400)
        good = self.client.post("/api/v1/auth/signup/", {**body, "mobile_no": "+919000000001"}, format="json")
        self.assertEqual(good.status_code, 201, good.data)
        self.assertEqual(good.data["admin"]["mobile_no"], "9000000001")

    def test_login_with_a_formatted_mobile(self):
        response = self.client.post("/api/v1/auth/login/", {"login": "+91 90000 00000", "password": "x"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
