"""
WhatsApp messages to gym members, through Meta's WhatsApp Cloud API.

Business-initiated WhatsApp messages must use templates approved in Meta's WhatsApp Manager. The template names
and their {{1}}, {{2}}… body variables are listed in TEMPLATES; create them in Meta with exactly these names.
Nothing is sent until WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID are set and the business turns WhatsApp on.
"""

import json
import logging
import urllib.error
import urllib.request
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .models import BusinessAccount, WhatsAppMessage, WhatsAppSetting
from .subscriptions import SubscriptionService

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v21.0"

# message type → (template name, WhatsAppSetting switch). Body variables are in the order of the comments.
TEMPLATES = {
    # {{1}} member first name, {{2}} plan, {{3}} gym name, {{4}} end date
    "EXPIRY": ("vyntra_plan_expiring", "expiry_reminders"),
    # {{1}} member first name, {{2}} plan, {{3}} gym name, {{4}} end date
    "EXPIRED": ("vyntra_plan_expired", "expired_followups"),
    # {{1}} member first name, {{2}} amount due, {{3}} gym name
    "DUES": ("vyntra_dues_pending", "dues_reminders"),
    # {{1}} member first name, {{2}} amount, {{3}} gym name, {{4}} date, {{5}} balance left
    "PAYMENT": ("vyntra_payment_received", "payment_receipts"),
    # {{1}} member first name, {{2}} gym name
    "BIRTHDAY": ("vyntra_birthday_wish", "birthday_wishes"),
}


def is_configured():
    return bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)


def rupees(amount):
    amount = Decimal(amount)
    return f"₹{amount:,.0f}" if amount == amount.to_integral() else f"₹{amount:,.2f}"


def day(value):
    return f"{value.day} {value:%b %Y}"


def get_setting(business_account_id):
    setting, _ = WhatsAppSetting.objects.get_or_create(business_account_id=business_account_id)
    return setting


def sent_this_month(business_account_id, today=None):
    today = today or timezone.localdate()
    return WhatsAppMessage.objects.filter(
        business_account_id=business_account_id, status="SENT", sent_date__gte=today.replace(day=1)
    ).count()


def _post(phone, template, params):
    """Sends one template message; returns Meta's message id. Raises on failure."""
    body = {
        "messaging_product": "whatsapp",
        "to": f"91{phone}",
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": settings.WHATSAPP_TEMPLATE_LANGUAGE},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in params]}],
        },
    }
    request = urllib.request.Request(
        f"{GRAPH_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)["messages"][0]["id"]
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode(errors="replace")[:900]) from error


def send(member, message_type, params, setting=None, today=None):
    """
    Sends one reminder to a member if the business has it switched on, the owner's trial or plan is active, the
    member has a mobile number, it wasn't already sent today, and the monthly limit isn't reached.
    Returns the WhatsAppMessage, or None when nothing was sent.
    """
    today = today or timezone.localdate()
    business_account_id = member.business_account_id
    template, switch = TEMPLATES[message_type]
    setting = setting or get_setting(business_account_id)
    if not (is_configured() and setting.enabled and getattr(setting, switch) and member.phone):
        return None
    owner = SubscriptionService.owner_of(business_account_id)
    if owner is None or not SubscriptionService.has_access(SubscriptionService.for_admin(owner)):
        return None
    if WhatsAppMessage.objects.filter(member=member, message_type=message_type, sent_date=today).exists():
        return None
    if sent_this_month(business_account_id, today) >= settings.WHATSAPP_MONTHLY_LIMIT:
        logger.warning("WhatsApp monthly limit reached for business %s", business_account_id)
        return None

    message = WhatsAppMessage(business_account_id=business_account_id, member=member, message_type=message_type,
                              phone=member.phone, template=template, sent_date=today)
    try:
        message.provider_message_id = _post(member.phone, template, params)
        message.status = "SENT"
    except Exception as error:
        logger.warning("WhatsApp %s to member %s failed: %s", message_type, member.id, error)
        message.status, message.error = "FAILED", str(error)[:1000]
    message.save()
    return message


def run_morning(business_account_id, members, today):
    """The morning reminders for one business; `members` are its active members from MemberService.get_members."""
    setting = get_setting(business_account_id)
    if not (is_configured() and setting.enabled):
        return 0
    gym = BusinessAccount.objects.get(id=business_account_id).name
    sent = 0

    def first(member):
        return member.first_name.strip().split(" ")[0]

    for member in members:
        latest = member.active_memberships[0] if member.active_memberships else None
        try:
            if latest and not member.is_live and latest.end_date == today - timedelta(days=1):
                sent += bool(send(member, "EXPIRED", [first(member), latest.membership_plan.name, gym,
                                                      day(latest.end_date)], setting, today))
            elif latest and latest.end_date in (today, today + timedelta(days=3)):
                sent += bool(send(member, "EXPIRY", [first(member), latest.membership_plan.name, gym,
                                                     day(latest.end_date)], setting, today))
            # Dues once a week (Mondays), so members aren't chased every day.
            if today.weekday() == 0 and member.total_due > 0:
                sent += bool(send(member, "DUES", [first(member), rupees(member.total_due), gym], setting, today))
            dob = member.date_of_birth
            if dob and (dob.month, dob.day) == (today.month, today.day):
                sent += bool(send(member, "BIRTHDAY", [first(member), gym], setting, today))
        except Exception:
            logger.exception("WhatsApp reminders failed for member %s", member.id)
    return sent


def payment_received(payment):
    """A receipt on WhatsApp right after a payment is recorded."""
    from .services import PaymentService  # avoid a circular import

    member = payment.member
    balance = PaymentService.balance(payment.membership) if payment.membership_id else Decimal("0")
    try:
        send(member, "PAYMENT", [
            member.first_name.strip().split(" ")[0], rupees(payment.amount), member.business_account.name,
            day(timezone.localtime(payment.payment_date).date()), rupees(max(balance, Decimal("0"))),
        ])
    except Exception:
        logger.exception("WhatsApp receipt failed for payment %s", payment.id)
