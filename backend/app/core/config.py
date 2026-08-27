import os
from dotenv import load_dotenv

# Load .env file from backend directory
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

class Settings:
    PROJECT_NAME: str = "Clinderma Support Chatbot API"
    VERSION: str = "2.0.0"
    API_PREFIX: str = "/api"

    # ── Gemini Configuration ──
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.6-flash")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

    # ── Groq Configuration ──
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # ── Pluggable Provider Toggles (Environment Controlled) ──
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")             # 'gemini', 'groq', 'local_grounded'
    VECTOR_STORE_PROVIDER: str = os.getenv("VECTOR_STORE_PROVIDER", "faiss")  # 'local_json', 'faiss', 'qdrant', 'pinecone'
    CRM_PROVIDER: str = os.getenv("CRM_PROVIDER", "mock_kylas")      # 'mock_kylas', 'kylas_api'
    ORDER_PROVIDER: str = os.getenv("ORDER_PROVIDER", "mock_orders")  # 'mock_orders', 'clinderma_db'

    # ── Grounding & Guardrail Settings ──
    GROUNDING_THRESHOLD: float = float(os.getenv("GROUNDING_THRESHOLD", "0.60"))  # Cosine similarity threshold (0-1)
    STRICT_GROUNDING: bool = True

    # ── Conversation Memory ──
    MAX_HISTORY_TURNS: int = 8  # Number of past messages to include in LLM context

    # ── Database & Paths ──
    DATA_DIR: str = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))
    KB_INDEX_PATH: str = os.path.join(DATA_DIR, "kb_index.json")
    FAISS_INDEX_PATH: str = os.path.join(DATA_DIR, "kb_vectors.faiss")
    FAISS_META_PATH: str = os.path.join(DATA_DIR, "kb_meta.json")
    DB_PATH: str = os.path.join(DATA_DIR, "clinderma.db")

    # ── Kylas CRM Configuration ──
    KYLAS_API_KEY: str = os.getenv("KYLAS_API_KEY", "MOCK_KYLAS_KEY_12345")
    KYLAS_API_URL: str = os.getenv("KYLAS_API_URL", "https://api.kylas.io/v1/leads")

settings = Settings()
