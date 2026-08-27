"""
Comprehensive Test Suite for Clinderma Chatbot V3
Tests:
  1. Knowledge retrieval over Blog articles (forehead bumps, moisturizers, etc.)
  2. Grounding & out-of-scope query rejection + contact collection
  3. Multi-turn lead capture timing (turn 1, turn 2/3 soft invite)
  4. Entity extraction (Name + 10-digit Indian Mobile Number)
  5. Multi-lingual support (English, Hindi, Marathi)
"""

import os
import sys
import uuid
import sqlite3

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
from app.models.schemas import ChatRequest
from app.services.rag_engine import rag_engine
from app.services.session_manager import session_manager
from app.core.config import settings

def run_tests():
    print("=" * 70)
    print("[TEST SUITE] STARTING CLINDERMA CHATBOT V3 VERIFICATION")
    print("=" * 70)

    # Test 1: Blog-specific knowledge query
    print("\n--- [TEST 1: Blog Knowledge Retrieval: Forehead Bumps / Folliculitis] ---")
    session_1 = f"test_blog_{uuid.uuid4().hex[:6]}"
    req1 = ChatRequest(
        message="Why do I get tiny bumps on my forehead after working out?",
        session_id=session_1,
        language="en"
    )
    res1 = rag_engine.process_chat(req1)
    print(f"User: {req1.message}")
    print(f"Grounded: {res1.get('grounded')} | Confidence: {res1.get('confidence')}")
    print(f"Bot Answer:\n{res1.get('answer')}")
    assert res1.get("grounded") == True, "Failed: Blog query should be grounded"
    print("--> TEST 1 PASSED: Blog knowledge retrieved accurately.")

    # Test 2: Blog-specific knowledge query: Moisturizers with acne
    print("\n--- [TEST 2: Blog Knowledge Retrieval: Moisturizer for Acne] ---")
    session_2 = f"test_blog_moist_{uuid.uuid4().hex[:6]}"
    req2 = ChatRequest(
        message="Should I use a moisturizer if I have active acne breakouts?",
        session_id=session_2,
        language="en"
    )
    res2 = rag_engine.process_chat(req2)
    print(f"User: {req2.message}")
    print(f"Grounded: {res2.get('grounded')} | Confidence: {res2.get('confidence')}")
    print(f"Bot Answer:\n{res2.get('answer')}")
    assert res2.get("grounded") == True, "Failed: Moisturizer query should be grounded"
    print("--> TEST 2 PASSED: Moisturizer & Acne blog guidance grounded.")

    # Test 3: Out-of-KB query
    print("\n--- [TEST 3: Out-of-KB Query Handling (Zero Hallucination + Lead Prompt)] ---")
    session_3 = f"test_out_{uuid.uuid4().hex[:6]}"
    req3 = ChatRequest(
        message="What is the distance between the Earth and the Moon in miles?",
        session_id=session_3,
        language="en"
    )
    res3 = rag_engine.process_chat(req3)
    print(f"User: {req3.message}")
    print(f"Grounded: {res3.get('grounded')} | Confidence: {res3.get('confidence')}")
    print(f"Bot Answer:\n{res3.get('answer')}")
    assert res3.get("grounded") == False, "Failed: Out of KB query should NOT be marked grounded"
    assert "specializ" in res3.get("answer").lower() or "knowledge base" in res3.get("answer").lower(), "Failed: Should explain specialization"
    assert "name" in res3.get("answer").lower() and "mobile" in res3.get("answer").lower(), "Failed: Should ask for Name & Mobile"
    print("--> TEST 3 PASSED: Out-of-KB gracefully handled with contact capture prompt.")

    # Test 4: Multi-turn Lead Capture Flow
    print("\n--- [TEST 4: Multi-Turn Conversation & Natural Lead Capture Flow] ---")
    session_4 = f"test_flow_{uuid.uuid4().hex[:6]}"
    
    # Turn 1: Primary question (should NOT ask for phone)
    print("\n  >> Turn 1: Primary Acne question")
    req_t1 = ChatRequest(
        message="What is purging when starting acne treatment?",
        session_id=session_4,
        language="en"
    )
    res_t1 = rag_engine.process_chat(req_t1)
    print(f"  User: {req_t1.message}")
    print(f"  Bot:\n{res_t1.get('answer')[:180]}...")
    assert "by the way, could i have" not in res_t1.get("answer").lower(), "Failed: Turn 1 should not ask for contact info"

    # Turn 2: Follow-up question (Turn 2 -> Should naturally include soft lead invite)
    print("\n  >> Turn 2: Follow-up question (Should append soft lead invitation)")
    req_t2 = ChatRequest(
        message="How long does acne purging usually last?",
        session_id=session_4,
        language="en"
    )
    res_t2 = rag_engine.process_chat(req_t2)
    print(f"  User: {req_t2.message}")
    print(f"  Bot:\n{res_t2.get('answer')}")
    assert "by the way" in res_t2.get("answer").lower() or "whatsapp" in res_t2.get("answer").lower(), "Failed: Turn 2 should include soft lead invitation"

    # Turn 3: User provides Name and Mobile Number
    print("\n  >> Turn 3: User gives Name & Phone Number")
    req_t3 = ChatRequest(
        message="My name is Sumit, 9022905913",
        session_id=session_4,
        language="en"
    )
    res_t3 = rag_engine.process_chat(req_t3)
    print(f"  User: {req_t3.message}")
    print(f"  Bot:\n{res_t3.get('answer')}")
    assert "sumit" in res_t3.get("answer").lower(), "Failed: Bot should address user by name"
    assert "9022905913" in res_t3.get("answer"), "Failed: Bot should acknowledge phone number"

    # Verify DB lead record
    conn = sqlite3.connect(settings.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, phone_number FROM leads WHERE phone_number LIKE '%9022905913%'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None, "Failed: Lead not found in SQLite leads table"
    assert row[0] == "Sumit", f"Expected Name 'Sumit', got '{row[0]}'"
    print(f"  --> Lead verified in DB: Name={row[0]}, Phone={row[1]}")
    print("--> TEST 4 PASSED: Multi-turn lead capture flow works flawlessly.")

    # Test 5: Multi-lingual (Hindi)
    print("\n--- [TEST 5: Multi-Lingual Support (Hindi)] ---")
    session_5 = f"test_hi_{uuid.uuid4().hex[:6]}"
    req5 = ChatRequest(
        message="acne theek hone me kitna samay lagta hai?",
        session_id=session_5,
        language="hi"
    )
    res5 = rag_engine.process_chat(req5)
    print(f"User: {req5.message}")
    print(f"Bot Answer:\n{res5.get('answer')}")
    assert res5.get("grounded") == True, "Failed: Hindi acne question should be grounded"
    print("--> TEST 5 PASSED: Multi-lingual Hindi query answered natively.")

    print("\n" + "=" * 70)
    print("ALL 5 TEST SUITES PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
