"""
Seed realistic tele-dermatology clinical data for Clinderma Mid-Semester Project Review.
Generates:
- 16 diverse patient leads across Indian metros with clinical concerns and Kylas sync status.
- 6 rich clinical handoff tickets with transcripts, severity flags, doctor notes, and AI summaries.
"""

import sys
import os
import datetime

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.db import get_conn
from app.services.handoff_manager import handoff_manager

def seed_database():
    conn = get_conn()
    cursor = conn.cursor()

    print("[SEED] Resetting demo leads and handoffs for clean review state...")
    cursor.execute("DELETE FROM leads")
    cursor.execute("DELETE FROM handoffs")
    cursor.execute("DELETE FROM transcripts")
    conn.commit()

    now = datetime.datetime.now()

    # 1. Seed Realistic Patient Leads
    leads_data = [
        ("KYLAS_LEAD_SUMIT01", "Sumit Mane", "9022905913", "Acne Vulgaris: Comedones & active breakouts on cheeks | Skin Type: Oily", "website", 1, (now - datetime.timedelta(hours=2)).isoformat()),
        ("KYLAS_LEAD_POOJA02", "Pooja Sharma", "9820144521", "Suspected Chemical Burn / Erythema from AHA 30% + Tretinoin | Skin Type: Sensitive", "website", 1, (now - datetime.timedelta(hours=5)).isoformat()),
        ("KYLAS_LEAD_RAHUL03", "Rahul Verma", "9819234812", "Inquiring about Salicylic Acid 2% while on oral Isotretinoin 20mg | Skin Type: Extremely Dry", "website", 1, (now - datetime.timedelta(hours=14)).isoformat()),
        ("KYLAS_LEAD_ANANY04", "Ananya Iyer", "9930812944", "Skin Assessment: Melasma & Post-Inflammatory Hyperpigmentation | Duration: 6+ months | Skin Type: Combination", "assessment_form", 1, (now - datetime.timedelta(days=1, hours=2)).isoformat()),
        ("KYLAS_LEAD_SNEHA05", "Sneha Patel", "9876543210", "Skin Assessment: Epidermal Melasma on Malar Prominence | Duration: 1 year | Skin Type: Normal to Dry", "assessment_form", 1, (now - datetime.timedelta(days=1, hours=8)).isoformat()),
        ("KYLAS_LEAD_VIKRA06", "Vikramaditya Rao", "9740112833", "Hormonal Jawline Acne & Texture | Skin Type: Oily T-zone", "website", 1, (now - datetime.timedelta(days=2)).isoformat()),
        ("KYLAS_LEAD_TANYA07", "Tanya Kapoor", "9811223344", "Skin Assessment: Damaged Moisture Barrier from Over-exfoliation | Duration: 2 weeks | Skin Type: Reactive Sensitive", "assessment_form", 1, (now - datetime.timedelta(days=2, hours=6)).isoformat()),
        ("KYLAS_LEAD_ARJUN08", "Arjun Mehta", "9822334455", "Persistent Blackheads & Enlarged Pores | Skin Type: Very Oily", "website", 1, (now - datetime.timedelta(days=3)).isoformat()),
        ("KYLAS_LEAD_PRIYA09", "Priya Nambiar", "9845112233", "Skin Assessment: Post-Acne Erythema (PIE) & Red Marks | Duration: 3 months | Skin Type: Dry Sensitive", "assessment_form", 1, (now - datetime.timedelta(days=3, hours=10)).isoformat()),
        ("KYLAS_LEAD_KAVIT10", "Kavita Joshi", "9890123456", "Forehead Fungal Acne (Malassezia Folliculitis) vs Comedonal Acne | Skin Type: Combination", "website", 0, (now - datetime.timedelta(days=4)).isoformat()),
        ("KYLAS_LEAD_ROHIT11", "Rohit Deshmukh", "9823456789", "Sun Spots & Uneven Pigmentation on Forehead | Skin Type: Normal", "website", 1, (now - datetime.timedelta(days=4, hours=14)).isoformat()),
        ("KYLAS_LEAD_MEERA12", "Meera Nair", "9847123456", "Skin Assessment: Early Fine Lines & Loss of Elasticity | Duration: 1 year | Skin Type: Dry", "assessment_form", 1, (now - datetime.timedelta(days=5)).isoformat()),
        ("KYLAS_LEAD_ADITI13", "Aditi Sen", "9830123456", "Rosacea Flushes & Sensitive Cheeks | Skin Type: Extremely Sensitive", "website", 0, (now - datetime.timedelta(days=5, hours=8)).isoformat()),
        ("KYLAS_LEAD_ROHAN14", "Rohan Kulkarni", "9822998877", "Body Acne (Bacne) & Folliculitis Treatment Protocol | Skin Type: Oily", "website", 1, (now - datetime.timedelta(days=6)).isoformat()),
        ("KYLAS_LEAD_DEVAN15", "Devansh Singhania", "9810998877", "Skin Assessment: Cystic Nodular Acne on Cheeks | Duration: 8 months | Skin Type: Oily Sensitive", "assessment_form", 1, (now - datetime.timedelta(days=6, hours=12)).isoformat()),
        ("KYLAS_LEAD_RITU16", "Ritu Choudhary", "9829887766", "Perioral Dermatitis Flare-up around mouth | Skin Type: Combination", "website", 1, (now - datetime.timedelta(days=7)).isoformat()),
    ]

    for lead in leads_data:
        cursor.execute("""
            INSERT INTO leads (lead_id, name, phone_number, concern, channel, kylas_synced, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, lead)

    print(f"[SEED] Inserted {len(leads_data)} realistic patient leads.")

    # 2. Seed Realistic Clinical Escalation Tickets
    handoffs_data = [
        {
            "session_id": "CLINICAL_ESC_URGENT_POOJA",
            "user_name": "Pooja Sharma",
            "user_phone": "9820144521",
            "reason": "Adverse Reaction / Severe Stinging & Erythema",
            "channel": "website",
            "status": "pending",
            "severity": "critical",
            "doctor_notes": "Urgent triage needed: Patient advised immediate cool compresses and petroleum jelly barrier occlusion. Call scheduled via WhatsApp.",
            "ai_summary": "Patient combined 30% AHA peel with 0.1% Tretinoin cream without sunscreen. Reports intense burning sensation, facial swelling, and peeling. Recommended immediate cessation of actives and cool compresses.",
            "created_at": (now - datetime.timedelta(hours=5)).isoformat(),
            "transcript": [
                ("user", "Help! My skin is burning really badly and getting red and swollen.", (now - datetime.timedelta(hours=5, minutes=10)).isoformat()),
                ("bot", "I am so sorry to hear this. Burning and swelling require immediate care. Please immediately stop applying all active products, wash your face gently with cool water, and apply only a plain barrier cream like pure petroleum jelly or ceramide lotion. What products did you apply?", (now - datetime.timedelta(hours=5, minutes=9)).isoformat()),
                ("user", "I used a 30% AHA peel yesterday and then 0.1% tretinoin cream last night.", (now - datetime.timedelta(hours=5, minutes=8)).isoformat()),
                ("bot", "Combining high-concentration AHA chemical peel with prescription-strength 0.1% Tretinoin has compromised your stratum corneum barrier, causing severe chemical irritation and erythema. I am escalating your case directly to our Senior Dermatology Skin Coach immediately.", (now - datetime.timedelta(hours=5, minutes=7)).isoformat()),
                ("user", "Yes please help, I am scared it will leave marks. My number is 9820144521, I am Pooja Sharma.", (now - datetime.timedelta(hours=5, minutes=5)).isoformat()),
                ("bot", "Thank you Pooja, our clinical team has received your ticket and will call you on WhatsApp shortly. Please avoid sun exposure completely today.", (now - datetime.timedelta(hours=5, minutes=4)).isoformat())
            ]
        },
        {
            "session_id": "CLINICAL_ESC_DRUG_RAHUL",
            "user_name": "Rahul Verma",
            "user_phone": "9819234812",
            "reason": "Drug Interaction / Oral Isotretinoin Inquiry",
            "channel": "website",
            "status": "pending",
            "severity": "moderate",
            "doctor_notes": "Needs dermatological guidance: Must reassure patient that blackheads purge during month 2 of oral retinoids and topical keratolytics will cause scarring.",
            "ai_summary": "Patient is taking oral Isotretinoin 20mg and inquiring if they can use Clinderma 2% Salicylic Acid serum for remaining blackheads. Advised against concurrent keratolytics due to extreme xerosis risk.",
            "created_at": (now - datetime.timedelta(hours=14)).isoformat(),
            "transcript": [
                ("user", "Can I use Clinderma 2% Salicylic Acid serum while taking Isotretinoin 20mg capsules?", (now - datetime.timedelta(hours=14, minutes=15)).isoformat()),
                ("bot", "While taking oral Isotretinoin, your skin barrier is significantly thinned and sensitive. We strongly advise against using topical Salicylic Acid or chemical exfoliants concurrently, as this can trigger severe dryness, irritation, and scarring.", (now - datetime.timedelta(hours=14, minutes=14)).isoformat()),
                ("user", "I have stubborn blackheads on my nose, what else can I use?", (now - datetime.timedelta(hours=14, minutes=12)).isoformat()),
                ("bot", "Gentle hydration with hyaluronic acid and ceramide moisturizer is recommended. Let me connect you with a Clinderma Skin Coach to review your dosage and suggest safe barrier-friendly options. Could you share your name and number?", (now - datetime.timedelta(hours=14, minutes=10)).isoformat()),
                ("user", "Sure, my name is Rahul Verma, number 9819234812", (now - datetime.timedelta(hours=14, minutes=8)).isoformat()),
                ("bot", "Thanks Rahul! Your inquiry has been routed to our clinical skin coach team.", (now - datetime.timedelta(hours=14, minutes=7)).isoformat())
            ]
        },
        {
            "session_id": "CLINICAL_ESC_PIH_ANANYA",
            "user_name": "Ananya Iyer",
            "user_phone": "9930812944",
            "reason": "Persistent Post-Inflammatory Hyperpigmentation (PIH)",
            "channel": "assessment_form",
            "status": "pending",
            "severity": "moderate",
            "doctor_notes": "Assessment profile reviewed. Ready for skin coach WhatsApp consultation. Prescribing Tranexamic Acid 3% + Alpha Arbutin 2% protocol.",
            "ai_summary": "Patient completed Skin Assessment. Reports Fitzpatrick IV skin type with 6-month persistent dark brown macules following inflammatory acne. Seeking Tranexamic Acid + Alpha Arbutin regimen.",
            "created_at": (now - datetime.timedelta(days=1, hours=2)).isoformat(),
            "transcript": [
                ("user", "I completed the skin test on the website for dark acne spots that won't fade for 6 months.", (now - datetime.timedelta(days=1, hours=2, minutes=8)).isoformat()),
                ("bot", "Thank you Ananya! Based on your assessment, your concerns are consistent with Post-Inflammatory Hyperpigmentation (PIH). A combination of Clinderma 3% Tranexamic Acid and 2% Alpha Arbutin with strict broad-spectrum SPF 50 is clinically proven for this.", (now - datetime.timedelta(days=1, hours=2, minutes=7)).isoformat()),
                ("user", "Can a doctor review my routine? I don't want peeling.", (now - datetime.timedelta(days=1, hours=2, minutes=5)).isoformat()),
                ("bot", "Absolutely. I have escalated your file to our Skin Coach dashboard. A consultant will review your assessment responses and reach out.", (now - datetime.timedelta(days=1, hours=2, minutes=3)).isoformat())
            ]
        },
        {
            "session_id": "CLINICAL_ESC_ROUTINE_VIKRAM",
            "user_name": "Vikramaditya Rao",
            "user_phone": "9740112833",
            "reason": "Combination Skin Regimen Formulation",
            "channel": "website",
            "status": "pending",
            "severity": "routine",
            "doctor_notes": "",
            "ai_summary": "Patient seeking tailored morning and evening skincare regimen for oily T-zone and dry cheeks in humid coastal weather (Bengaluru/Chennai).",
            "created_at": (now - datetime.timedelta(days=2)).isoformat(),
            "transcript": [
                ("user", "I have oily forehead and nose but very dry cheeks. What Clinderma routine do you recommend?", (now - datetime.timedelta(days=2, minutes=12)).isoformat()),
                ("bot", "For combination skin in humid weather, we recommend a balancing protocol: a gentle foaming gel cleanser, 5% Niacinamide serum to regulate T-zone sebum without drying, lightweight gel moisturizer, and matte finish sunscreen.", (now - datetime.timedelta(days=2, minutes=11)).isoformat()),
                ("user", "My number is 9740112833, Vikramaditya Rao. Can you send product links on WhatsApp?", (now - datetime.timedelta(days=2, minutes=8)).isoformat()),
                ("bot", "Certainly Vikramaditya, your profile has been logged for our skin coach follow-up.", (now - datetime.timedelta(days=2, minutes=7)).isoformat())
            ]
        },
        {
            "session_id": "CLINICAL_ESC_RESOLVED_SNEHA",
            "user_name": "Sneha Patel",
            "user_phone": "9876543210",
            "reason": "Melasma & Sunscreen Layering Protocol",
            "channel": "assessment_form",
            "status": "resolved",
            "severity": "moderate",
            "doctor_notes": "Consultation completed via WhatsApp. Verified epidermal melasma on malar bones. Prescribed Clinderma Tinted Mineral SPF 50 + Azelaic Acid 10%. Patient agreed to 4-week follow-up.",
            "ai_summary": "Patient consulted regarding melasma patches worsening after sun exposure. Connected with coach, photo reviewed, protocol prescribed.",
            "created_at": (now - datetime.timedelta(days=1, hours=8)).isoformat(),
            "transcript": [
                ("user", "My skin has brown patches across my nose and upper cheeks.", (now - datetime.timedelta(days=1, hours=8, minutes=15)).isoformat()),
                ("bot", "These symmetric brown patches on sun-exposed facial areas are characteristic of Melasma. Rigorous broad-spectrum UV protection with iron oxides is vital to block visible blue light.", (now - datetime.timedelta(days=1, hours=8, minutes=14)).isoformat()),
                ("user", "Can your dermatologist review my photos? Sneha Patel, 9876543210", (now - datetime.timedelta(days=1, hours=8, minutes=10)).isoformat()),
                ("bot", "Ticket created for Dr. Consultant review.", (now - datetime.timedelta(days=1, hours=8, minutes=8)).isoformat())
            ]
        },
        {
            "session_id": "CLINICAL_ESC_LIVE_SUMIT",
            "user_name": "Sumit Mane",
            "user_phone": "9022905913",
            "reason": "Lead Captured in Chat / Acne Consultation",
            "channel": "website",
            "status": "resolved",
            "severity": "routine",
            "doctor_notes": "Live interactive test verified by Sumit. Chatbot triage flow and CRM lead recording confirmed functional.",
            "ai_summary": "User inquired about acne triggers, pore clogging, and salicylic acid usage. Captured name and mobile number for follow-up.",
            "created_at": (now - datetime.timedelta(hours=2)).isoformat(),
            "transcript": [
                ("user", "What causes acne breakouts?", (now - datetime.timedelta(hours=2, minutes=6)).isoformat()),
                ("bot", "Acne breakouts happen when excess oil, dead skin cells, and bacteria clog your pores, triggering inflammation. Key triggers include hormonal fluctuations, stress, diet, and comedogenic skincare products. To help our dermatologists share a personalized routine, could you share your name and 10-digit WhatsApp number?", (now - datetime.timedelta(hours=2, minutes=5)).isoformat()),
                ("user", "I am Sumit Mane & mine number is 9022905913", (now - datetime.timedelta(hours=2, minutes=3)).isoformat()),
                ("bot", "Thank you, Sumit Mane! Your details have been noted. A Clinderma Skin Coach will connect with you on WhatsApp (9022905913) to review your skin profile.", (now - datetime.timedelta(hours=2, minutes=2)).isoformat())
            ]
        }
    ]

    for h in handoffs_data:
        cursor.execute("""
            INSERT INTO handoffs (session_id, user_name, user_phone, reason, channel, status, severity, doctor_notes, ai_summary, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (h["session_id"], h["user_name"], h["user_phone"], h["reason"], h["channel"], h["status"], h["severity"], h["doctor_notes"], h["ai_summary"], h["created_at"]))

        for sender, msg, ts in h["transcript"]:
            cursor.execute("""
                INSERT INTO transcripts (session_id, sender, message, timestamp)
                VALUES (%s, %s, %s, %s)
            """, (h["session_id"], sender, msg, ts))

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[SEED] Successfully inserted {len(handoffs_data)} clinical handoffs with transcripts.")
    print("[SEED] Done! Database is now seeded with high-quality dermatology data for college review.")

if __name__ == "__main__":
    seed_database()
