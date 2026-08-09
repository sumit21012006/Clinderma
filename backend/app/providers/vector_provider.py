"""
Clinderma Vector Store Provider — V2 (FAISS Semantic Search + Gemini Embeddings)

Pluggable provider architecture:
  - FAISSVectorStore: Production-grade semantic search using Gemini embeddings + FAISS
  - LocalJSONVectorStore: Fallback keyword matching using RapidFuzz (zero external deps)
  - ProductionVectorStore: Stub for Qdrant/Pinecone cloud migration
"""

import json
import os
import re
import numpy as np
from typing import List, Dict, Any
from app.providers.base import AbstractVectorStore
from app.core.config import settings


class FAISSVectorStore(AbstractVectorStore):
    """
    Semantic vector search using Gemini text-embedding-004 embeddings + FAISS index.
    Supports cosine similarity retrieval over the full Clinderma Knowledge Base.
    """

    def __init__(self):
        self.index = None
        self.documents = []
        self.client = None
        self._load()

    def _load(self):
        import faiss
        from google import genai

        # Load FAISS index
        if os.path.exists(settings.FAISS_INDEX_PATH):
            self.index = faiss.read_index(settings.FAISS_INDEX_PATH)
            print(f"[VectorStore] Loaded FAISS index: {self.index.ntotal} vectors")
        else:
            print(f"[VectorStore] WARNING: FAISS index not found at {settings.FAISS_INDEX_PATH}")
            print(f"[VectorStore] Run 'python backend/scripts/ingest_kb.py' to build the index.")

        # Load KB documents (for answer retrieval after vector search)
        if os.path.exists(settings.KB_INDEX_PATH):
            with open(settings.KB_INDEX_PATH, "r", encoding="utf-8") as f:
                self.documents = json.load(f)

        # Initialize Gemini client for query embedding
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def _embed_query(self, query: str) -> np.ndarray:
        """Generate embedding for user query using Gemini text-embedding-004."""
        result = self.client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=[query]
        )
        vec = np.array(result.embeddings[0].values, dtype='float32').reshape(1, -1)
        import faiss
        faiss.normalize_L2(vec)
        return vec

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.index or not self.documents or not query.strip():
            return []

        try:
            query_vec = self._embed_query(query)
            scores, indices = self.index.search(query_vec, top_k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self.documents):
                    continue
                doc = self.documents[idx]
                results.append({
                    "id": doc.get("id"),
                    "source": doc.get("source"),
                    "category": doc.get("category"),
                    "question": doc.get("question"),
                    "answer": doc.get("answer"),
                    "score": float(score)  # Cosine similarity (0 to 1)
                })

            return results

        except Exception as e:
            print(f"[VectorStore] FAISS search error: {e}")
            return []


class LocalJSONVectorStore(AbstractVectorStore):
    """Fallback keyword search using RapidFuzz (no external API needed)."""

    def __init__(self, kb_path: str = None):
        from rapidfuzz import fuzz
        self.fuzz = fuzz
        self.kb_path = kb_path or settings.KB_INDEX_PATH
        self.documents = []
        self.load_index()

    def load_index(self):
        if os.path.exists(self.kb_path):
            with open(self.kb_path, "r", encoding="utf-8") as f:
                self.documents = json.load(f)

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.documents or not query.strip():
            return []

        results = []
        query_clean = query.lower().strip()
        query_words = set(re.findall(r'\w+', query_clean))

        for doc in self.documents:
            q_text = doc.get("question", "").lower()
            a_text = doc.get("answer", "").lower()
            cat_text = doc.get("category", "").lower()
            full_text = f"{q_text} {a_text} {cat_text}"

            score_q_set = self.fuzz.token_set_ratio(query_clean, q_text)
            score_q_sort = self.fuzz.token_sort_ratio(query_clean, q_text)
            score_full_set = self.fuzz.token_set_ratio(query_clean, full_text)

            max_base = max(score_q_set, score_q_sort, score_full_set)

            q_words_doc = set(re.findall(r'\w+', q_text))
            a_words_doc = set(re.findall(r'\w+', a_text))
            all_doc_words = q_words_doc.union(a_words_doc)
            common_words = query_words.intersection(all_doc_words)
            stopwords = {"what", "is", "the", "how", "long", "does", "do", "it", "to", "take", "can", "and", "a", "an", "in", "for", "of", "my", "with", "on", "are", "you"}
            important_common = common_words - stopwords
            bonus = len(important_common) * 15.0
            final_score = min(max_base + bonus, 100.0)

            if final_score >= 35.0 and len(important_common) > 0:
                # Normalize to 0-1 scale for compatibility with FAISS scoring
                results.append({
                    "id": doc.get("id"),
                    "source": doc.get("source"),
                    "category": doc.get("category"),
                    "question": doc.get("question"),
                    "answer": doc.get("answer"),
                    "score": round(final_score / 100.0, 4)
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


class ProductionVectorStore(AbstractVectorStore):
    """Stub for Qdrant / Pinecone production migration (swap via .env)."""
    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        raise NotImplementedError("Production Qdrant/Pinecone driver not configured. Set API keys in .env.")


def get_vector_store() -> AbstractVectorStore:
    """Factory function — selects provider based on .env configuration."""
    provider = settings.VECTOR_STORE_PROVIDER
    if provider == "faiss":
        return FAISSVectorStore()
    elif provider == "local_json":
        return LocalJSONVectorStore()
    else:
        return ProductionVectorStore()
