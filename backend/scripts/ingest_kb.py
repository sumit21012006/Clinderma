"""
Clinderma KB Ingestion Script — V2 (Gemini Embeddings + FAISS Index)

Parses DOCX dataset files into structured KB entries, generates
semantic embeddings using Gemini text-embedding-004, and builds
a FAISS vector index for production-grade semantic retrieval.
"""

import os
import sys
import json
import re
import time
import numpy as np
import docx

# Add backend to path so we can import config
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.config import settings

DATASET_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "Dataset"))
DATA_DIR = settings.DATA_DIR
OUTPUT_JSON = settings.KB_INDEX_PATH
OUTPUT_FAISS = settings.FAISS_INDEX_PATH
OUTPUT_META = settings.FAISS_META_PATH


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace('\xa0', ' ').replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"').strip()
    return re.sub(r'\s+', ' ', text)


def parse_faqs_docx(file_path: str):
    doc = docx.Document(file_path)
    entries = []
    current_category = "General FAQs"
    current_question = None
    current_answer = []

    for para in doc.paragraphs:
        raw_text = para.text.strip()
        if not raw_text:
            continue
        text = clean_text(raw_text)

        cat_match = re.match(r'^\d+\.\s+([A-Z\s\&\-\–\']+)(?:\:)?$', text)
        if cat_match and not text.lower().startswith("is ") and not text.lower().startswith("how "):
            current_category = cat_match.group(1).title()
            continue

        if "cohort" in text.lower() or "faqs for" in text.lower():
            current_category = text.title()
            continue

        q_match = re.match(r'^(?:Q\d+[:\.]?|\d+\.)\s*(.+)$', text, re.IGNORECASE)
        if q_match:
            q_candidate = q_match.group(1).strip()

            if current_question and current_answer:
                entries.append({
                    "id": f"faq_{len(entries)+1}",
                    "source": "Master FAQs Document",
                    "category": current_category,
                    "question": current_question,
                    "answer": "\n".join(current_answer).strip(),
                    "text": f"Category: {current_category}\nQuestion: {current_question}\nAnswer: {' '.join(current_answer).strip()}"
                })
                current_question = None
                current_answer = []

            if '?' in q_candidate:
                q_parts = q_candidate.split('?', 1)
                current_question = q_parts[0].strip() + '?'
                if q_parts[1].strip():
                    current_answer.append(q_parts[1].strip())
            else:
                current_question = q_candidate
        else:
            if current_question:
                current_answer.append(text)
            else:
                if len(text) > 15:
                    entries.append({
                        "id": f"faq_{len(entries)+1}",
                        "source": "Master FAQs Document",
                        "category": current_category,
                        "question": f"Protocol / Guideline ({current_category})",
                        "answer": text,
                        "text": f"Category: {current_category}\nGuideline: {text}"
                    })

    if current_question and current_answer:
        entries.append({
            "id": f"faq_{len(entries)+1}",
            "source": "Master FAQs Document",
            "category": current_category,
            "question": current_question,
            "answer": "\n".join(current_answer).strip(),
            "text": f"Category: {current_category}\nQuestion: {current_question}\nAnswer: {' '.join(current_answer).strip()}"
        })

    return entries


def parse_module_docx(file_path: str):
    doc = docx.Document(file_path)
    entries = []
    current_section = "Clinderma Clinical Philosophy & Protocols"
    buffer = []

    for para in doc.paragraphs:
        text = clean_text(para.text)
        if not text:
            continue

        is_heading = len(text) < 70 and (text.isupper() or re.match(r'^\d+[\.\)]\s+', text) or text.endswith(':'))
        if is_heading:
            if buffer:
                content = "\n".join(buffer).strip()
                if len(content) > 25:
                    entries.append({
                        "id": f"mod_{len(entries)+1}",
                        "source": "Clinderma Training Module",
                        "category": current_section,
                        "question": f"Topic: {current_section}",
                        "answer": content,
                        "text": f"Section: {current_section}\nContent: {content}"
                    })
                buffer = []
            current_section = text
        else:
            buffer.append(text)

    if buffer:
        content = "\n".join(buffer).strip()
        if len(content) > 25:
            entries.append({
                "id": f"mod_{len(entries)+1}",
                "source": "Clinderma Training Module",
                "category": current_section,
                "question": f"Topic: {current_section}",
                "answer": content,
                "text": f"Section: {current_section}\nContent: {content}"
            })

    return entries


def generate_embeddings(entries: list):
    """Generate Gemini text-embedding-004 vectors for all KB entries."""
    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    embedding_dim = 768  # text-embedding-004 output dimension
    vectors = []
    batch_size = 20  # Gemini embedding API supports batching

    print(f"Generating embeddings using {settings.EMBEDDING_MODEL}...")

    for i in range(0, len(entries), batch_size):
        batch = entries[i:i + batch_size]
        texts = [e["text"][:2048] for e in batch]  # Truncate to embedding model limit

        try:
            result = client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=texts
            )
            for emb in result.embeddings:
                vectors.append(emb.values)
        except Exception as e:
            print(f"  Embedding batch {i//batch_size + 1} error: {e}")
            # Fallback: zero vectors for failed batch
            for _ in batch:
                vectors.append([0.0] * embedding_dim)

        # Respect rate limits (free tier: 15 RPM for embeddings)
        if i + batch_size < len(entries):
            time.sleep(1)

        print(f"  Embedded {min(i + batch_size, len(entries))}/{len(entries)} entries")

    return np.array(vectors, dtype='float32')


def build_faiss_index(vectors: np.ndarray):
    """Build and save a FAISS index from embedding vectors."""
    import faiss

    dim = vectors.shape[1]
    # Use IndexFlatIP (inner product / cosine similarity after normalization)
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    return index


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    faq_path = os.path.join(DATASET_DIR, "CLINDERMA \u2013 MASTER FAQs DOCUMENT (1).docx")
    module_path = os.path.join(DATASET_DIR, "Clinderma module.docx")

    print(f"Ingesting FAQs from: {faq_path}")
    faq_entries = parse_faqs_docx(faq_path)
    print(f"  Parsed {len(faq_entries)} FAQ entries.")

    print(f"Ingesting Training Module from: {module_path}")
    module_entries = parse_module_docx(module_path)
    print(f"  Parsed {len(module_entries)} Module entries.")

    all_entries = faq_entries + module_entries

    # Save JSON index (for backward compatibility & debugging)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON KB index: {OUTPUT_JSON} ({len(all_entries)} items)")

    # Generate embeddings and build FAISS index
    vectors = generate_embeddings(all_entries)

    import faiss
    index = build_faiss_index(vectors)
    faiss.write_index(index, OUTPUT_FAISS)
    print(f"Saved FAISS index: {OUTPUT_FAISS} ({index.ntotal} vectors, dim={vectors.shape[1]})")

    # Save metadata (maps FAISS vector index → KB entry)
    meta = [{"idx": i, "id": e["id"], "question": e["question"], "category": e["category"]} for i, e in enumerate(all_entries)]
    with open(OUTPUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"Saved FAISS metadata: {OUTPUT_META}")

    print(f"\nIngestion complete! {len(all_entries)} KB entries with semantic embeddings indexed.")


if __name__ == "__main__":
    main()
