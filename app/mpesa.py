"""
M-Pesa Daraja API Integration
Handles STK Push (Lipa Na M-Pesa Online) and callback processing.

Environment variables required:
  MPESA_CONSUMER_KEY       – from Safaricom Developer Portal
  MPESA_CONSUMER_SECRET    – from Safaricom Developer Portal
  MPESA_SHORTCODE          – Business/Paybill shortcode
  MPESA_PASSKEY            – Lipa Na M-Pesa Online passkey
  MPESA_CALLBACK_URL       – Publicly accessible URL for Safaricom to POST results to
  MPESA_ENV                – "sandbox" or "production" (default: sandbox)
"""

import base64
import logging
import os
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
MPESA_ENV             = os.getenv("MPESA_ENV")
MPESA_CONSUMER_KEY    = os.getenv("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE       = os.getenv("MPESA_SHORTCODE")
MPESA_PASSKEY         = os.getenv("MPESA_PASSKEY")
MPESA_CALLBACK_URL    = os.getenv("MPESA_CALLBACK_URL")

BASE_URL = (
    "https://api.safaricom.co.ke"
    if MPESA_ENV == "production"
    else "https://sandbox.safaricom.co.ke"
)

# Sandbox passkey (Safaricom official test passkey — only valid in sandbox)
SANDBOX_PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"


def _passkey() -> str:
    return MPESA_PASSKEY if MPESA_ENV == "production" else SANDBOX_PASSKEY


def _shortcode() -> str:
    return MPESA_SHORTCODE if MPESA_ENV == "production" else "174379"


# ── Auth ──────────────────────────────────────────────────────────────────────
def get_access_token() -> str | None:
    """Fetch an OAuth access token from Safaricom."""
    if not MPESA_CONSUMER_KEY or not MPESA_CONSUMER_SECRET:
        logger.warning("M-Pesa credentials not configured — skipping token fetch")
        return None

    credentials = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()

    try:
        resp = requests.get(
            f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {credentials}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as exc:
        logger.error("M-Pesa token fetch failed: %s", exc)
        return None


# ── STK Push ──────────────────────────────────────────────────────────────────
def stk_push(phone: str, amount: float, order_uuid: str, description: str = "TicketInit Tickets") -> dict:
    """
    Initiate an M-Pesa STK push (Lipa Na M-Pesa Online).

    :param phone:       Kenyan phone number (any format — normalised internally)
    :param amount:      Amount in KES (rounded to nearest integer)
    :param order_uuid:  UUID of the Order — used as AccountReference & external ID
    :param description: Short description shown in M-Pesa prompt
    :return:            dict with keys: success (bool), checkout_request_id (str|None),
                        merchant_request_id (str|None), error (str|None)
    """
    phone = _normalise_phone(phone)
    if not phone:
        return {"success": False, "error": "Invalid phone number"}

    token = get_access_token()
    if not token:
        return {"success": False, "error": "Could not obtain M-Pesa access token. Check credentials."}

    timestamp  = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    shortcode  = _shortcode()
    passkey    = _passkey()
    password   = base64.b64encode(
        f"{shortcode}{passkey}{timestamp}".encode()
    ).decode()

    payload = {
        "BusinessShortCode": shortcode,
        "Password":          password,
        "Timestamp":         timestamp,
        "TransactionType":   "CustomerPayBillOnline",
        "Amount":            int(round(amount)),
        "PartyA":            phone,
        "PartyB":            shortcode,
        "PhoneNumber":       phone,
        "CallBackURL":       MPESA_CALLBACK_URL,
        "AccountReference":  order_uuid[:12],   # max 12 chars
        "TransactionDesc":   description[:13],  # max 13 chars
    }

    try:
        resp = requests.post(
            f"{BASE_URL}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            timeout=15,
        )
        data = resp.json()
        logger.info("STK push response: %s", data)

        if data.get("ResponseCode") == "0":
            return {
                "success":             True,
                "checkout_request_id": data.get("CheckoutRequestID"),
                "merchant_request_id": data.get("MerchantRequestID"),
                "error":               None,
            }
        else:
            return {
                "success": False,
                "error":   data.get("errorMessage") or data.get("ResponseDescription", "STK push failed"),
            }
    except Exception as exc:
        logger.error("STK push exception: %s", exc)
        return {"success": False, "error": str(exc)}


# ── Query STK status ──────────────────────────────────────────────────────────
def query_stk_status(checkout_request_id: str) -> dict:
    """
    Query the status of an STK push transaction.
    Returns dict with: result_code (str), result_desc (str), success (bool)
    """
    token = get_access_token()
    if not token:
        return {"success": False, "result_code": "error", "result_desc": "Auth failed"}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    shortcode = _shortcode()
    passkey   = _passkey()
    password  = base64.b64encode(
        f"{shortcode}{passkey}{timestamp}".encode()
    ).decode()

    payload = {
        "BusinessShortCode":  shortcode,
        "Password":           password,
        "Timestamp":          timestamp,
        "CheckoutRequestID":  checkout_request_id,
    }

    try:
        resp = requests.post(
            f"{BASE_URL}/mpesa/stkpushquery/v1/query",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            timeout=10,
        )
        data = resp.json()
        result_code = str(data.get("ResultCode", "-1"))
        result_desc = data.get("ResultDesc", "Unknown")

        return {
            "success":     result_code == "0",
            "result_code": result_code,
            "result_desc": result_desc,
        }
    except Exception as exc:
        logger.error("STK query exception: %s", exc)
        return {"success": False, "result_code": "error", "result_desc": str(exc)}


# ── Callback parser ───────────────────────────────────────────────────────────
def parse_callback(body: dict) -> dict:
    """
    Parse a Safaricom STK-push callback payload.
    Returns a normalised dict:
      {
        checkout_request_id: str,
        result_code:         int,
        result_desc:         str,
        mpesa_receipt:       str | None,
        phone:               str | None,
        amount:              float | None,
        transaction_date:    str | None,
      }
    """
    try:
        stk_callback = body["Body"]["stkCallback"]
        checkout_id  = stk_callback.get("CheckoutRequestID", "")
        result_code  = int(stk_callback.get("ResultCode", -1))
        result_desc  = stk_callback.get("ResultDesc", "")

        # Metadata is only present when ResultCode == 0
        metadata_items = (
            stk_callback.get("CallbackMetadata", {}).get("Item", [])
        )
        meta = {item["Name"]: item.get("Value") for item in metadata_items}

        return {
            "checkout_request_id": checkout_id,
            "result_code":         result_code,
            "result_desc":         result_desc,
            "mpesa_receipt":       meta.get("MpesaReceiptNumber"),
            "phone":               str(meta.get("PhoneNumber", "")),
            "amount":              float(meta.get("Amount", 0)),
            "transaction_date":    str(meta.get("TransactionDate", "")),
        }
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Callback parse error: %s — body: %s", exc, body)
        return {
            "checkout_request_id": "",
            "result_code":         -1,
            "result_desc":         f"Parse error: {exc}",
            "mpesa_receipt":       None,
            "phone":               None,
            "amount":              None,
            "transaction_date":    None,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _normalise_phone(phone: str) -> str | None:
    """
    Normalise a Kenyan phone number to the 2547XXXXXXXX format required by Daraja.
    Accepts: 07XX, 01XX, +2547XX, 2547XX
    """
    phone = phone.strip().replace(" ", "").replace("-", "")

    if phone.startswith("+254"):
        phone = phone[1:]   # strip leading +
    elif phone.startswith("0"):
        phone = "254" + phone[1:]

    # Must be 12 digits starting with 254
    if len(phone) == 12 and phone.startswith("254"):
        return phone

    return None