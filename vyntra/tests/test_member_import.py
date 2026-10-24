import io
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from vyntra.models import Member, Payment

from .base import ApiTestCase

HEADINGS = "Member ID,First Name*,Last Name,Mobile,Plan*,Start Date*,End Date,Amount Paid,Payment Method\n"


def csv_file(body, name="members.csv"):
    return SimpleUploadedFile(name, (HEADINGS + body).encode(), content_type="text/csv")


class MemberImportTests(ApiTestCase):
    def upload(self, file, dry_run=False):
        query = f"{self.q}&dry_run=true" if dry_run else self.q
        return self.client.post(f"/api/v1/members/import/{query}", {"file": file}, format="multipart")

    def test_dry_run_reports_problems_without_saving(self):
        response = self.upload(csv_file(
            "201,Rahul,Sharma,98765 43210,Monthly,01-10-2026,,500,upi\n"
            "202,Priya,,12345,Yearly,01-10-2026,,,\n"
            ",Arjun,,,quarterly,2026-09-15,,,\n"
        ), dry_run=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["total"], response.data["ok"], response.data["created"]), (3, 2, 0))
        bad = response.data["rows"][1]
        self.assertFalse(bad["ok"])
        self.assertTrue(any(e.startswith("Plan:") for e in bad["errors"]))
        self.assertEqual(response.data["rows"][2]["member_code"], "101")  # no ID → next free number
        self.assertEqual(Member.objects.count(), 0)

    def test_import_creates_members_plans_and_payments_from_the_good_rows(self):
        response = self.upload(csv_file(
            "201,Rahul,Sharma,+91 98765 43210,monthly,01-10-2026,15-11-2026,500,UPI\n"
            "202,Priya,,12345,Monthly,01-10-2026,,,\n"
        ))
        self.assertEqual(response.data["created"], 1)
        member = Member.objects.get(member_code="201")
        self.assertEqual(member.phone, "9876543210")
        membership = member.memberships.get(is_active=True)
        self.assertEqual((membership.start_date, membership.end_date), (date(2026, 10, 1), date(2026, 11, 15)))
        payment = Payment.objects.get(member=member)
        self.assertEqual((payment.amount, payment.payment_method), (500, "UPI"))
        self.assertEqual(payment.payment_date.date(), date(2026, 10, 1))

    def test_excel_files_and_problem_rows(self):
        book = Workbook()
        sheet = book.active
        sheet.append(["Name", "Mobile", "Plan", "Start Date", "Amount Paid"])
        sheet.append(["Kiran Rao", 9876543211, "Monthly", date(2026, 10, 5), 1500])  # paid more than the plan
        sheet.append(["Meena", 9876543212, "Monthly", date(2026, 10, 5), 1000])
        buffer = io.BytesIO()
        book.save(buffer)
        upload = SimpleUploadedFile("members.xlsx", buffer.getvalue())
        response = self.upload(upload)
        self.assertEqual(response.data["created"], 1, response.data)
        self.assertTrue(response.data["rows"][0]["errors"][0].startswith("Amount Paid"))
        self.assertEqual(Member.objects.get().first_name, "Meena")

    def test_duplicate_ids_and_unreadable_files(self):
        response = self.upload(csv_file("301,A,,,Monthly,01-10-2026,,,\n301,B,,,Monthly,01-10-2026,,,\n"),
                               dry_run=True)
        self.assertEqual(response.data["ok"], 1)
        self.assertEqual(self.upload(SimpleUploadedFile("x.pdf", b"%PDF")).status_code, 400)
        no_headings = SimpleUploadedFile("x.csv", b"Rahul,Monthly\n")
        self.assertEqual(self.upload(no_headings).status_code, 400)

    def test_template_download(self):
        response = self.client.get("/api/v1/members/import/template/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"First Name*", response.content)
