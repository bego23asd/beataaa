"""Vercel serverless function: Netflix Trial Sender API.

Deployed as /api/... on the same Vercel domain as the frontend.
No framework needed - pure Python http.server handler (Vercel Python runtime).
"""

import asyncio
import json
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

import httpx

URL = "https://web.prod.cloud.netflix.com/graphql"
TIMEOUT = 120  # generous; Vercel Pro allows up to 300s maxDuration

NFVDID_VALUE = "BQFmAAEBEDfQY0dAGiJZuocAfFU2CQpAYdUwSM-D1OYmnErF2ElCBLm3CS95c_ywNg2ALWYqpR11S7Q7F8GGn_WlsEleYshSjx9uKQE-KVY35tPLE1ZtgQ%3D%3D"


def collect_screen_updates(node, out=None):
    """Grab every serverScreenUpdate string from the component tree."""
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "serverScreenUpdate" and isinstance(v, str):
                out.append(v)
            collect_screen_updates(v, out)
    elif isinstance(node, list):
        for item in node:
            collect_screen_updates(item, out)
    return out


def build_payload1(user_email: str, flwssn: str) -> dict:
    """CLCSWebInitSignup - the opening call."""
    return {
        "operationName": "CLCSWebInitSignup",
        "variables": {
            "inputNode": "WELCOME",
            "locale": "en-IN",
            "inputFields": [
                {"name": "flwssn", "value": {"stringValue": flwssn}},
                {"name": "email", "value": {"stringValue": user_email}},
                {"name": "recaptchaError", "value": {"stringValue": "LOAD_TIMED_OUT"}},
                {"name": "recaptchaResponseTime", "value": {}},
                {"name": "recaptchaSiteKey", "value": {"stringValue": "6LdqW_EqAAAAAO87Fb_kcZfNzsI0qJRcKiJDYpUv"}},
                {"name": "recaptchaToken", "value": {}},
            ],
        },
        "extensions": {
            "persistedQuery": {
                "id": "5d76d6a0-ccfe-4c31-b587-b4e1954732ca",
                "version": 102,
            }
        },
    }
def build_payload2(resp1_text, user_email):
    """CLCSScreenUpdate built from the FRESH state Netflix returned in call #1."""
    obj = json.loads(resp1_text)
    screen = obj["data"]["clcsWebInitSignup"]["screen"]
    server_state = screen["serverState"]
    updates = collect_screen_updates(screen.get("componentTree", {}))
    if not updates:
        raise RuntimeError("fresh serverScreenUpdate not found")
    screen_update = max(updates, key=len)
    return {
        "operationName": "CLCSScreenUpdate",
        "variables": {
            "format": "HTML",
            "imageFormat": "PNG",
            "locale": "en-IN",
            "serverState": server_state,
            "serverScreenUpdate": screen_update,
            "inputFields": [
                {"name": "email", "value": {"stringValue": user_email}},
                {"name": "pipcConsent", "value": {"booleanValue": False}},
            ],
        },
        "extensions": {
            "persistedQuery": {
                "id": "0fd81de7-07af-4c7d-802f-0f4ea4181aa3",
                "version": 102,
            }
        },
    }


def build_headers(req_id, top_uuid, flwssn):
    return {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        'Content-Type': 'application/json',
        'Origin': 'https://www.netflix.com',
        'Referer': 'https://www.netflix.com/',
        'Accept-Language': 'en-US,en;q=0.9',
        'x-netflix.request.id': req_id,
        'x-netflix.request.toplevel.uuid': top_uuid,
        'x-netflix.request.clcs.bucket': 'high',
        'x-netflix.context.form-factor': 'phone',
        'x-netflix.context.app-version': 'v38c5b0da',
        'x-netflix.context.locales': 'en-in',
        'Cookie': f"nfvdid={NFVDID_VALUE}; flwssn={flwssn}",
    }


async def send_trial(user_email, debug=False):
    flwssn = str(uuid.uuid4())
    req_id = str(uuid.uuid4())
    top_uuid = str(uuid.uuid4())

    payload1 = build_payload1(user_email, flwssn)
    headers = build_headers(req_id, top_uuid, flwssn)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp1 = await client.post(URL, json=payload1, headers=headers)
            if '"errors"' in resp1.text.lower():
                return {
                    "success": False,
                    "message": "Signup init was rejected by Netflix.",
                    "debug": resp1.text[:400] if debug else "",
                }

            payload2 = build_payload2(resp1.text, user_email)
            resp2 = await client.post(URL, json=payload2, headers=headers)
            text2 = resp2.text.lower()

            if '"errors"' in text2:
                return {
                    "success": False,
                    "message": "Screen update was rejected by Netflix.",
                    "debug": resp2.text[:400] if debug else "",
                }

            if "email-register-link-sent" in text2 or "sign-up link" in text2:
                return {
                    "success": True,
                    "message": "A sign-up link email was sent. The user must TAP/click the link in the email to finish signing up (30-day trial follows after).",
                    "debug": "Netflix returned the 'email-register-link-sent' screen.",
                }

            if resp2.status_code == 200:
                return {"success": True, "message": "Successfully sent 30 days trial for your email"}
            return {
                "success": False,
                "message": f"Screen update was rejected by Netflix (status {resp2.status_code}).",
                "debug": resp2.text[:400] if debug else "",
            }
    except Exception as e:
        return {"success": False, "message": f"Something broke: {e}."}
class handler(BaseHTTPRequestHandler):
    """Vercel Python runtime entry point."""

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def log_message(self, format, *args):
        return  # Vercel captures logs itself

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/api", "/api/", "/api/index", "/api/index.py"):
            self._send_json(200, {
                "service": "Netflix Trial Sender API",
                "status": "ok",
                "docs": "POST /api/send-trial with JSON {\"email\": \"...\"}",
            })
            return
        self._send_json(404, {"success": False, "message": "Not found."})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/send-trial", "/send-trial"):
            self._send_json(404, {"success": False, "message": "Not found."})
            return

        data = self._read_body()
        email = (data.get("email") or "").strip()
        debug = bool(data.get("debug"))

        if not email or "@" not in email:
            self._send_json(400, {"success": False, "message": "Please enter a valid email address."})
            return

        result = asyncio.run(send_trial(email, debug=debug))
        self._send_json(200, result)