import sqlite3
import os
import uuid
import datetime
from typing import Optional, Dict, Any
from app.providers.base import AbstractCRMProvider
from app.core.config import settings

class MockKylasCRMProvider(AbstractCRMProvider):
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DB_PATH
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                lead_id TEXT PRIMARY KEY,
                name TEXT,
                phone_number TEXT NOT NULL,
                concern TEXT,
                channel TEXT,
                kylas_synced INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def create_lead(
        self, phone_number: str, name: Optional[str] = "Web Visitor", concern: Optional[str] = "General Inquiry", channel: str = "website"
    ) -> Dict[str, Any]:
        lead_id = f"KYLAS_LEAD_{uuid.uuid4().hex[:8].upper()}"
        created_at = datetime.datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads (lead_id, name, phone_number, concern, channel, kylas_synced, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (lead_id, name or "Web Visitor", phone_number, concern or "General Inquiry", channel, created_at))
        conn.commit()
        conn.close()

        print(f"[CRM PROVIDER] Synced Lead {lead_id} to Kylas CRM (Mock): {phone_number} - {concern}")

        return {
            "lead_id": lead_id,
            "phone_number": phone_number,
            "status": "SUCCESSFULLY_SYNCED_TO_KYLAS",
            "kylas_synced": True,
            "created_at": created_at
        }

class LiveKylasCRMProvider(AbstractCRMProvider):
    def create_lead(
        self, phone_number: str, name: Optional[str] = "Web Visitor", concern: Optional[str] = "General Inquiry", channel: str = "website"
    ) -> Dict[str, Any]:
        # Production REST call to Kylas CRM
        import requests
        headers = {"api-key": settings.KYLAS_API_KEY, "Content-Type": "application/json"}
        payload = {
            "firstName": name,
            "phoneNumbers": [{"type": "MOBILE", "value": phone_number}],
            "source": channel,
            "requirement": concern
        }
        response = requests.post(settings.KYLAS_API_URL, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {
            "lead_id": data.get("id", "KYLAS_PROD"),
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
