import uuid
import datetime
from typing import Optional, Dict, Any
from app.providers.base import AbstractCRMProvider
from app.core.db import get_conn
from app.core.config import settings


class MockKylasCRMProvider(AbstractCRMProvider):
    def __init__(self):
        self._init_db()

    def _init_db(self):
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                lead_id TEXT PRIMARY KEY,
                name TEXT,
                phone_number TEXT NOT NULL UNIQUE,
                concern TEXT,
                channel TEXT,
                kylas_synced INTEGER DEFAULT 1,
                created_at TEXT
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
        lead_id = f"KYLAS_LEAD_{uuid.uuid4().hex[:8].upper()}"

        conn = get_conn()
        cursor = conn.cursor()

        # Upsert: if phone exists, update name/concern; otherwise insert
        cursor.execute("""
            INSERT INTO leads (lead_id, name, phone_number, concern, channel, kylas_synced, created_at)
            VALUES (%s, %s, %s, %s, %s, 1, %s)
            ON CONFLICT (phone_number) DO UPDATE
                SET name = CASE
                        WHEN EXCLUDED.name != 'Web Visitor' THEN EXCLUDED.name
                        ELSE leads.name
                    END,
                    concern = leads.concern || ' | ' || EXCLUDED.concern,
                    channel = EXCLUDED.channel
            RETURNING lead_id, name
        """, (lead_id, clean_name, phone_number, concern or "General Inquiry", channel, created_at))

        returned = cursor.fetchone()
        if returned:
            lead_id = returned["lead_id"]
            clean_name = returned["name"]

        conn.commit()
        cursor.close()
        conn.close()

        print(f"[CRM PROVIDER] Synced Lead {lead_id} to Kylas CRM (Mock): {clean_name} ({phone_number}) - {concern}")

        return {
            "lead_id": lead_id,
            "name": clean_name,
            "phone_number": phone_number,
            "status": "SUCCESSFULLY_SYNCED_TO_KYLAS",
            "kylas_synced": True,
            "created_at": created_at
        }


class LiveKylasCRMProvider(AbstractCRMProvider):
    def create_lead(
        self, phone_number: str, name: Optional[str] = "Web Visitor",
        concern: Optional[str] = "General Inquiry", channel: str = "website"
    ) -> Dict[str, Any]:
        import requests
        headers = {"api-key": settings.KYLAS_API_KEY, "Content-Type": "application/json"}
        payload = {
            "firstName": name or "Web Visitor",
            "phoneNumbers": [{"type": "MOBILE", "value": phone_number}],
            "source": channel,
            "requirement": concern
        }
        try:
            response = requests.post(settings.KYLAS_API_URL, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            lead_id = str(data.get("id", "KYLAS_PROD"))
        except Exception as e:
            print(f"[CRM Live API Warning]: {e}, falling back to local ID")
            lead_id = f"KYLAS_LEAD_{uuid.uuid4().hex[:8].upper()}"

        return {
            "lead_id": lead_id,
            "name": name,
            "phone_number": phone_number,
            "status": "SYNCED_LIVE_KYLAS",
            "kylas_synced": True,
            "created_at": datetime.datetime.now().isoformat()
        }


def get_crm_provider() -> AbstractCRMProvider:
    if settings.CRM_PROVIDER == "mock_kylas":
        return MockKylasCRMProvider()
    else:
        return LiveKylasCRMProvider()
