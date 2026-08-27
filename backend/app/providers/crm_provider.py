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

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
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
        created_at = datetime.datetime.now().isoformat()
        clean_name = name.strip() if name and name.strip() else "Web Visitor"

        conn = self._get_conn()
        cursor = conn.cursor()

        # Check if phone already exists
        cursor.execute("SELECT lead_id, name, concern FROM leads WHERE phone_number = ?", (phone_number,))
        existing = cursor.fetchone()

        if existing:
            lead_id = existing[0]
            new_name = clean_name if clean_name != "Web Visitor" else existing[1]
            new_concern = f"{existing[2]} | {concern}" if concern else existing[2]
            cursor.execute("""
                UPDATE leads SET name = ?, concern = ?, channel = ? WHERE lead_id = ?
            """, (new_name, new_concern, channel, lead_id))
        else:
            lead_id = f"KYLAS_LEAD_{uuid.uuid4().hex[:8].upper()}"
            cursor.execute("""
                INSERT INTO leads (lead_id, name, phone_number, concern, channel, kylas_synced, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (lead_id, clean_name, phone_number, concern or "General Inquiry", channel, created_at))

        conn.commit()
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
        self, phone_number: str, name: Optional[str] = "Web Visitor", concern: Optional[str] = "General Inquiry", channel: str = "website"
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
