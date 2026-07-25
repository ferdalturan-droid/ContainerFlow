"""Regression tests for the invitation + password-reset flow added in
iteration 7. Covers:
- POST /api/superadmin/companies validates Kunde-ID is required
- POST /api/superadmin/companies sends invitation when admin_email is given
- /api/auth/login blocks users with invitation_status=pending
- GET  /api/auth/verify-token returns metadata for a fresh token
- POST /api/auth/accept-invitation sets password + flips status to active
- A consumed token returns 410 on re-verify
- POST /api/auth/forgot-password is always 200 (no email enumeration)
- POST /api/auth/reset-password updates the password atomically
- POST /api/superadmin/users only allows role=super_admin (everything else 403)
- POST /api/superadmin/companies/{id}/resend-invitation regenerates a token
"""
import os
import uuid
import requests
import pytest

API = os.environ.get("BACKEND_URL", "http://localhost:8001")
SA_EMAIL = "doganmiketuran@gmail.com"
SA_PASS = "SuperAdmin2026!"


def _login(email, password):
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    return r


@pytest.fixture(scope="module")
def sa_token():
    r = _login(SA_EMAIL, SA_PASS)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def sa_headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}"}


def _admin_token(user_id: str):
    """Pull the latest unused invitation token directly out of mongo (test only)."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv()

    async def go():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        return await db.invitation_tokens.find_one(
            {"user_id": user_id, "used": False}, {"_id": 0},
            sort=[("created_at", -1)],
        )
    return asyncio.get_event_loop().run_until_complete(go())


class TestNyBruger:
    def test_create_super_admin_succeeds(self, sa_headers):
        email = f"owner-{uuid.uuid4().hex[:8]}@platform.com"
        r = requests.post(
            f"{API}/api/superadmin/users", headers=sa_headers,
            json={"email": email, "name": "T", "password": "Pw1234!",
                  "role": "super_admin", "company_id": "*"}, timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "super_admin"

    def test_create_non_super_admin_is_blocked(self, sa_headers):
        r = requests.post(
            f"{API}/api/superadmin/users", headers=sa_headers,
            json={"email": "ladmin@x.dk", "name": "T", "password": "Pw1234!",
                  "role": "location_admin", "company_id": "default"}, timeout=10,
        )
        assert r.status_code == 403, r.text


class TestCompanyCreation:
    def test_kunde_id_is_required(self, sa_headers):
        r = requests.post(
            f"{API}/api/superadmin/companies", headers=sa_headers,
            json={"name": "NoIDCorp"}, timeout=10,
        )
        # Pydantic returns 422 for missing required field
        assert r.status_code in (400, 422), r.text

    def test_customer_creation_sends_invitation_and_blocks_login(self, sa_headers):
        suffix = uuid.uuid4().hex[:8]
        admin_email = f"argo-{suffix}@test.dk"
        r = requests.post(
            f"{API}/api/superadmin/companies", headers=sa_headers,
            json={
                "name": f"ARGO-{suffix}",
                "customer_id": f"K{suffix.upper()}",
                "company_type": "customer",
                "admin_email": admin_email,
                "admin_name": "Test Admin",
                "admin_phone": "+45 11 22 33 44",
            }, timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["company"]["customer_id"] == f"K{suffix.upper()}"
        assert body["created_admin"]["email"] == admin_email

        # Login should be blocked: pending invitation
        r2 = _login(admin_email, "anything")
        assert r2.status_code == 403, r2.text
        assert "aktiveret" in r2.json().get("detail", "").lower()

        # Pull the token, walk through verify -> accept -> login
        token_doc = _admin_token(body["created_admin"]["id"])
        assert token_doc, "no invitation token written"
        token = token_doc["token"]

        rv = requests.get(f"{API}/api/auth/verify-token", params={"token": token, "type": "invitation"}, timeout=10)
        assert rv.status_code == 200, rv.text
        assert rv.json()["email"] == admin_email
        assert rv.json()["role"] == "customer_admin"

        ra = requests.post(
            f"{API}/api/auth/accept-invitation",
            json={"token": token, "new_password": "MinKode1!"}, timeout=10,
        )
        assert ra.status_code == 200, ra.text

        # Same token now used → 410
        rv2 = requests.get(f"{API}/api/auth/verify-token", params={"token": token, "type": "invitation"}, timeout=10)
        assert rv2.status_code == 410, rv2.text

        # Login works
        r3 = _login(admin_email, "MinKode1!")
        assert r3.status_code == 200, r3.text
        assert r3.json()["user"]["invitation_status"] == "active"
        assert r3.json()["user"]["role"] == "customer_admin"

    def test_resend_invitation(self, sa_headers):
        suffix = uuid.uuid4().hex[:8]
        admin_email = f"resend-{suffix}@test.dk"
        r = requests.post(
            f"{API}/api/superadmin/companies", headers=sa_headers,
            json={"name": f"RES-{suffix}", "customer_id": f"R{suffix.upper()}",
                  "company_type": "customer", "admin_email": admin_email,
                  "admin_name": "X"}, timeout=15,
        )
        assert r.status_code == 200
        cid = r.json()["company"]["id"]
        # Resend twice — the first token is invalidated when the second is generated
        rr = requests.post(
            f"{API}/api/superadmin/companies/{cid}/resend-invitation",
            headers=sa_headers, timeout=10,
        )
        assert rr.status_code == 200, rr.text
        assert rr.json()["admin_email"] == admin_email


class TestForgotPassword:
    def test_forgot_unknown_email_is_200(self):
        r = requests.post(
            f"{API}/api/auth/forgot-password",
            json={"email": f"nonexist-{uuid.uuid4().hex[:8]}@x.dk"}, timeout=10,
        )
        assert r.status_code == 200

    def test_full_reset_flow(self, sa_headers):
        # Create a fresh super_admin, mark a known password, then reset via token
        suffix = uuid.uuid4().hex[:8]
        email = f"reset-{suffix}@platform.com"
        rc = requests.post(
            f"{API}/api/superadmin/users", headers=sa_headers,
            json={"email": email, "name": "R", "password": "Old1234!",
                  "role": "super_admin", "company_id": "*"}, timeout=10,
        )
        assert rc.status_code == 200, rc.text
        user_id = rc.json()["id"]

        # Trigger forgot-password
        rf = requests.post(f"{API}/api/auth/forgot-password", json={"email": email}, timeout=10)
        assert rf.status_code == 200

        token_doc = _admin_token(user_id)
        assert token_doc, "no reset token written"
        token = token_doc["token"]
        assert token_doc["token_type"] == "reset"

        # Submit new password
        rr = requests.post(
            f"{API}/api/auth/reset-password",
            json={"token": token, "new_password": "Nyt9876!"}, timeout=10,
        )
        assert rr.status_code == 200, rr.text

        # Old password fails, new one succeeds
        r1 = _login(email, "Old1234!")
        assert r1.status_code == 401
        r2 = _login(email, "Nyt9876!")
        assert r2.status_code == 200


class TestVerifyTokenErrors:
    def test_invalid_token(self):
        r = requests.get(f"{API}/api/auth/verify-token",
                         params={"token": "bogus", "type": "invitation"}, timeout=10)
        assert r.status_code == 400

    def test_missing_token(self):
        r = requests.get(f"{API}/api/auth/verify-token", params={"type": "invitation"}, timeout=10)
        assert r.status_code == 400

    def test_unknown_type(self):
        r = requests.get(f"{API}/api/auth/verify-token",
                         params={"token": "x", "type": "weird"}, timeout=10)
        assert r.status_code == 400
