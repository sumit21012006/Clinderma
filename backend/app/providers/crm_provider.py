import uuid
import datetime
from typing import Optional, Dict, Any
from app.providers.base import AbstractCRMProvider
from app.core.db import get_conn
from app.core.config import settings


def _mask_phone(phone: str) -> str:
    """Return a masked version of a phone number for safe logging."""
    if not phone or len(phone) < 4:
        return "****"
    return phone[:3] + "****" + phone[-2:]


class MockKylasCRMProvider(AbstractCRMProvider):
    """
    Development/testing CRM provider.
    Saves leads to local SQLite / PostgreSQL only.
    No real Kylas API call is made.
    kylas_synced = 0 to indicate leads are NOT in real Kylas.
    """

    def __init__(self):
        self._init_db()

    def _init_db(self):
        conn = get_conn()
        cursor = conn.cursor()
        # Use ON CONFLICT upsert-safe DDL — phone_number is the business key.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                lead_id     TEXT PRIMARY KEY,
                name        TEXT,
                phone_number TEXT NOT NULL,
                concern     TEXT,
                channel     TEXT,
                kylas_synced INTEGER DEFAULT 0,
                created_at  TEXT
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()

    def create_lead(
        self, phone_number: str, name: Optional[str] = "Web Visitor",
        concern: Optional[str] = "General Inquiry", channel: str = "website"
    ) -> Dict[str, Any]:
        created_at = datetime.datetime.now().isoformat()
        clean_name = name.strip() if name and name.strip() else "Web Visitor"
        new_lead_id = f"KYLAS_LEAD_{uuid.uuid4().hex[:8].upper()}"

        conn = get_conn()
        cursor = conn.cursor()

        # Upsert: if phone already exists, update name/concern; otherwise insert.
        cursor.execute(
            "SELECT lead_id, name, concern FROM leads WHERE phone_number = %s",
            (phone_number,)
        )
        existing = cursor.fetchone()

        if existing:
            lead_id = existing["lead_id"] if isinstance(existing, dict) else existing[0]
            prev_name = existing["name"] if isinstance(existing, dict) else existing[1]
            prev_concern = existing["concern"] if isinstance(existing, dict) else existing[2]
            # Prefer a real name over the placeholder
            final_name = clean_name if clean_name not in ("Web Visitor", "Website Visitor") else (prev_name or clean_name)
            # Keep concern concise — just update with latest concern, not append session IDs
            final_concern = concern or prev_concern
            cursor.execute(
                "UPDATE leads SET name = %s, concern = %s, channel = %s WHERE phone_number = %s",
                (final_name, final_concern, channel, phone_number)
            )
            clean_name = final_name
        else:
            lead_id = new_lead_id
            cursor.execute(
                "INSERT INTO leads (lead_id, name, phone_number, concern, channel, kylas_synced, created_at) "
                "VALUES (%s, %s, %s, %s, %s, 0, %s)",
                (lead_id, clean_name, phone_number, concern or "General Inquiry", channel, created_at)
            )

        conn.commit()
        cursor.close()
        conn.close()

        # Safe log — phone masked
        print(f"[CRM MOCK] Lead {lead_id} saved locally: {clean_name} ({_mask_phone(phone_number)})")

        return {
            "lead_id": lead_id,
            "name": clean_name,
            "phone_number": phone_number,
            "status": "SAVED_LOCALLY_NOT_SYNCED_TO_KYLAS",
            "kylas_synced": False,
            "created_at": created_at,
        }


class LiveKylasCRMProvider(AbstractCRMProvider):
    """
    Production CRM provider.
    DUAL-WRITE: always saves to local DB first, then calls Kylas API.
    If Kylas API fails the lead is still safe locally (kylas_synced = 0).
    Set CRM_PROVIDER=kylas_api in .env to activate.
    Requires: KYLAS_API_KEY and KYLAS_API_URL in environment.
    """

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """Ensure leads table exists (same DDL as mock provider)."""
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                lead_id     TEXT PRIMARY KEY,
                name        TEXT,
                phone_number TEXT NOT NULL,
                concern     TEXT,
                channel     TEXT,
                kylas_synced INTEGER DEFAULT 0,
                created_at  TEXT
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()

    def _save_locally(
        self, phone_number: str, name: str, concern: str, channel: str, created_at: str
    ) -> str:
        """Save or update lead in local DB. Returns the lead_id."""
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT lead_id, name, concern FROM leads WHERE phone_number = %s",
            (phone_number,)
        )
        existing = cursor.fetchone()
        if existing:
            lead_id = existing["lead_id"] if isinstance(existing, dict) else existing[0]
            prev_name = existing["name"] if isinstance(existing, dict) else existing[1]
            final_name = name if name not in ("Web Visitor", "Website Visitor") else (prev_name or name)
            cursor.execute(
                "UPDATE leads SET name = %s, concern = %s, channel = %s WHERE phone_number = %s",
                (final_name, concern, channel, phone_number)
            )
        else:
            lead_id = f"KYLAS_LEAD_{uuid.uuid4().hex[:8].upper()}"
            cursor.execute(
                "INSERT INTO leads (lead_id, name, phone_number, concern, channel, kylas_synced, created_at) "
                "VALUES (%s, %s, %s, %s, %s, 0, %s)",
                (lead_id, name, phone_number, concern, channel, created_at)
            )
        conn.commit()
        cursor.close()
        conn.close()
        return lead_id if not existing else (existing["lead_id"] if isinstance(existing, dict) else existing[0])

    def _mark_synced(self, lead_id: str, kylas_id: str) -> None:
        """Mark a lead as successfully synced to Kylas."""
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE leads SET kylas_synced = 1, lead_id = %s WHERE lead_id = %s",
            (kylas_id, lead_id)
        )
        conn.commit()
        cursor.close()
        conn.close()

    def create_lead(
        self, phone_number: str, name: Optional[str] = "Web Visitor",
        concern: Optional[str] = "General Inquiry", channel: str = "website"
    ) -> Dict[str, Any]:
        import requests

        created_at = datetime.datetime.now().isoformat()
        clean_name = name.strip() if name and name.strip() else "Web Visitor"
        clean_concern = concern or "General Inquiry"

        # Step 1: Always save locally first (lead is safe even if Kylas is down)
        lead_id = self._save_locally(phone_number, clean_name, clean_concern, channel, created_at)

        # Step 2: Call real Kylas API
        headers = {
            "api-key": settings.KYLAS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "firstName": clean_name,
            "phoneNumbers": [{"type": "MOBILE", "value": phone_number}],
            "source": channel,
            "requirement": clean_concern,
        }

        kylas_synced = False
        try:
            response = requests.post(
                settings.KYLAS_API_URL, json=payload, headers=headers, timeout=5
            )
            response.raise_for_status()
            data = response.json()
            kylas_id = str(data.get("id", lead_id))
            self._mark_synced(lead_id, kylas_id)
            lead_id = kylas_id
            kylas_synced = True
            print(f"[CRM LIVE] Lead synced to Kylas: {kylas_id} ({_mask_phone(phone_number)})")
        except Exception as e:
            # Lead already saved locally — not lost
            print(f"[CRM LIVE] Kylas API failed ({type(e).__name__}): lead saved locally only ({_mask_phone(phone_number)})")

        return {
            "lead_id": lead_id,
            "name": clean_name,
            "phone_number": phone_number,
            "status": "SYNCED_LIVE_KYLAS" if kylas_synced else "SAVED_LOCALLY_KYLAS_PENDING",
            "kylas_synced": kylas_synced,
            "created_at": created_at,
        }


def get_crm_provider() -> AbstractCRMProvider:
    if settings.CRM_PROVIDER == "kylas_api":
        return LiveKylasCRMProvider()
    return MockKylasCRMProvider()
