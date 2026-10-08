import os
import sys
import unittest
import io
import json

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
from app.core.db import run_migrations
from app.core.auth import ensure_default_admin


class TestAdminPRDFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_migrations()
        ensure_default_admin()
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

        # Login as Admin
        r = cls.client.post("/api/auth/login", json={"username": "admin", "password": "clinderma@admin2026"})
        assert r.status_code == 200, f"Admin login failed: {r.text}"
        cls.admin_token = r.json()["access_token"]
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

        # Login as Doctor
        r = cls.client.post("/api/auth/login", json={"username": "doctor", "password": "doctor@clinderma2026"})
        assert r.status_code == 200, f"Doctor login failed: {r.text}"
        cls.doc_token = r.json()["access_token"]
        cls.doc_headers = {"Authorization": f"Bearer {cls.doc_token}"}

        # Login as Viewer
        r = cls.client.post("/api/auth/login", json={"username": "viewer", "password": "viewer@clinderma2026"})
        assert r.status_code == 200, f"Viewer login failed: {r.text}"
        cls.viewer_token = r.json()["access_token"]
        cls.viewer_headers = {"Authorization": f"Bearer {cls.viewer_token}"}

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    # ── 1. Auth & RBAC ──────────────────────────────────────────────────────────
    def test_01_auth_me(self):
        r = self.client.get("/api/auth/me", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "admin")

        r = self.client.get("/api/auth/me", headers=self.doc_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "doctor")

        r = self.client.get("/api/auth/me", headers=self.viewer_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "viewer")

    # ── 2. Knowledge Base & FAQs CRUD ───────────────────────────────────────────
    def test_02_kb_crud_and_draft_workflow(self):
        # Create draft entry
        payload = {
            "category": "Treatment",
            "question": "What is the Acne Clear 60-day protocol?",
            "answer": "A medical protocol combining Salicylic acid and Ayurvedic botanicals."
        }
        r = self.client.post("/api/admin/kb", headers=self.admin_headers, json=payload)
        self.assertEqual(r.status_code, 200)
        kb_id = r.json()["id"]
        self.assertEqual(r.json()["kb_status"], "draft")

        # Verify in draft list
        r = self.client.get("/api/admin/kb/drafts", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        draft_ids = [d["id"] for d in r.json()["drafts"]]
        self.assertIn(kb_id, draft_ids)

        # Update entry
        r = self.client.put(f"/api/admin/kb/{kb_id}", headers=self.admin_headers, json={
            "answer": "Updated medical protocol with dermatologist guidance."
        })
        self.assertEqual(r.status_code, 200)

        # Test chat retrieves draft content
        r = self.client.post("/api/admin/test-chat", headers=self.admin_headers, json={
            "message": "tell me about the Acne Clear 60-day protocol",
            "session_id": "test_sandbox_1"
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["mode"], "draft")

        # Push to live
        r = self.client.post("/api/admin/push-to-live", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["entries_pushed"], 1)

        # Restore
        r = self.client.post("/api/admin/restore", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "restored")

    # ── 3. Document Upload ──────────────────────────────────────────────────────
    def test_03_kb_document_upload(self):
        file_content = b"Clinderma usage guidelines: apply sunscreen 15 minutes before stepping out."
        r = self.client.post(
            "/api/admin/kb/documents",
            headers=self.admin_headers,
            files={"file": ("sunscreen_guide.txt", io.BytesIO(file_content), "text/plain")},
            data={"category": "Products"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "uploaded")

        # List documents
        r = self.client.get("/api/admin/kb/documents", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)

    # ── 4. Offers Management ────────────────────────────────────────────────────
    def test_04_offers_management(self):
        payload = {
            "name": "End-of-Month Clearance",
            "discount_code": "CLIN30",
            "discount_type": "percentage",
            "discount_value": 30.0,
            "applicable_products": ["Clarifying Serum"],
            "conditions": {"min_order": 999},
            "start_date": "2026-10-01",
            "end_date": "2026-10-31"
        }
        r = self.client.post("/api/admin/offers", headers=self.admin_headers, json=payload)
        self.assertEqual(r.status_code, 200)
        offer_id = r.json()["id"]

        # Pause and resume offer
        r = self.client.patch(f"/api/admin/offers/{offer_id}/pause", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "paused")

        r = self.client.patch(f"/api/admin/offers/{offer_id}/pause", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "active")

        # Public active offers
        r = self.client.get("/api/offers/active")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()["offers"]), 1)

    # ── 5. Customer Chats & Takeover / Handback ─────────────────────────────────
    def test_05_customer_chats_takeover_handback(self):
        import uuid
        test_session = f"sess_customer_flow_{uuid.uuid4().hex[:8]}"

        # Customer sends message
        r = self.client.post("/api/chat", json={
            "message": "Hello, I want advice for hormonal acne.",
            "session_id": test_session
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(len(r.json()["answer"]) > 0)

        # Admin views chats
        r = self.client.get("/api/admin/chats", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)

        # Admin takes over
        r = self.client.post("/api/admin/chats/takeover", headers=self.admin_headers, json={"session_id": test_session})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "taken_over")

        # Chatbot is silenced while under takeover
        r = self.client.post("/api/chat", json={
            "message": "Are you still there?",
            "session_id": test_session
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["answer"], "")

        # Admin types directly to customer
        r = self.client.post("/api/admin/chats/message", headers=self.admin_headers, json={
            "session_id": test_session,
            "message": "Hi, I am taking over this conversation to assist you personally."
        })
        self.assertEqual(r.status_code, 200)

        # Hand back to bot
        r = self.client.post("/api/admin/chats/handback", headers=self.admin_headers, json={"session_id": test_session})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "handed_back")

    # ── 6. Doctor Review Workflow ───────────────────────────────────────────────
    def test_06_doctor_review_workflow(self):
        # Tag an answer
        r = self.client.post("/api/admin/reviews/tag", headers=self.admin_headers, json={
            "session_id": "sess_doc_rev_1",
            "customer_question": "Can I use hydroquinone without doctor supervision?",
            "chatbot_answer": "Yes, hydroquinone can be purchased and used freely.",
            "tag_note": "Hydroquinone requires medical prescription and skin monitoring."
        })
        self.assertEqual(r.status_code, 200)
        rev_id = r.json()["id"]

        # Doctor reviews and edits
        r = self.client.post(f"/api/admin/reviews/{rev_id}/edit", headers=self.doc_headers, json={
            "corrected_answer": "Hydroquinone is a prescription depigmenting agent that requires dermatologist guidance and a restricted usage period."
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "edited")
        self.assertTrue(r.json()["kb_updated"])

    # ── 7. Audit Log ────────────────────────────────────────────────────────────
    def test_07_audit_log(self):
        r = self.client.get("/api/admin/audit-log", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertIn("logs", r.json())
        self.assertGreater(len(r.json()["logs"]), 0)

    # ── 8. Analytics & CSV Export ───────────────────────────────────────────────
    def test_08_analytics_and_export(self):
        # Funnel
        r = self.client.get("/api/admin/analytics/funnel", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["funnel"]), 6)
        self.assertIn("non_openers", r.json())

        # Orders
        r = self.client.get("/api/admin/analytics/orders?view=daily", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertIn("total_revenue", r.json())

        # CSV Export
        r_funnel = self.client.get("/api/admin/analytics/export?type=funnel", headers=self.admin_headers)
        self.assertEqual(r_funnel.status_code, 200)
        self.assertIn("Stage", r_funnel.text)

        r_orders = self.client.get("/api/admin/analytics/export?type=orders", headers=self.admin_headers)
        self.assertEqual(r_orders.status_code, 200)
        self.assertIn("Order Value", r_orders.text)

    # ── 9. RBAC Restrictions Matrix ─────────────────────────────────────────────
    def test_09_rbac_matrix(self):
        # Viewer cannot create KB
        r = self.client.post("/api/admin/kb", headers=self.viewer_headers, json={"question": "q", "answer": "a"})
        self.assertEqual(r.status_code, 403)

        # Doctor cannot create offers
        r = self.client.post("/api/admin/offers", headers=self.doc_headers, json={"name": "test"})
        self.assertEqual(r.status_code, 403)

        # Viewer cannot takeover chat
        r = self.client.post("/api/admin/chats/takeover", headers=self.viewer_headers, json={"session_id": "s"})
        self.assertEqual(r.status_code, 403)

        # Doctor cannot takeover chat (admin only)
        r = self.client.post("/api/admin/chats/takeover", headers=self.doc_headers, json={"session_id": "s"})
        self.assertEqual(r.status_code, 403)

        # Doctor cannot view audit log (admin only)
        r = self.client.get("/api/admin/audit-log", headers=self.doc_headers)
        self.assertEqual(r.status_code, 403)

        # Viewer can view analytics
        r = self.client.get("/api/admin/analytics/funnel", headers=self.viewer_headers)
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
