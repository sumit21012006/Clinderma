# Implementation Plan — Clinderma Customer Support Chatbot (Scalable Architecture)

Build an end-to-end, multi-channel customer support chatbot for Clinderma with a enterprise-ready, modular architecture. The system uses a **Pluggable Provider Pattern (Strategy Pattern)** for LLMs, Embedding Engines, Vector Stores, and CRM Integrations. This guarantees that transitioning from free testing drivers (SentenceTransformers, Local Vector Index, Mock Kylas CRM) to production paid drivers (OpenAI/Gemini LLMs, Pinecone/Qdrant Vector DBs, Live Kylas API) is seamless via simple environment configuration changes.

## User Decisions & Architectural Principles

> [!TIP]
> **Scalability & Provider Strategy**: All external components (LLM Provider, Embedding Model, Vector DB, CRM Integration, Order Service) are abstracted behind abstract interface providers (`AbstractLLMProvider`, `AbstractVectorStore`, `AbstractCRMProvider`).
> - **Development Mode**: Uses local free sentence-transformers / TF-IDF embeddings, lightweight local vector store, and mock Kylas CRM service.
> - **Production Mode**: Easily toggled via `.env` to OpenAI/Gemini, Qdrant/Pinecone, and Live Kylas REST API.

> [!IMPORTANT]
> **Strict Grounding Policy**: The bot answers ONLY from the provided Knowledge Base documents (`Dataset/CLINDERMA – MASTER FAQs DOCUMENT (1).docx` and `Dataset/Clinderma module.docx`). If a query is outside the Knowledge Base, it responds with *"I don't have that information. Let me connect you with a Skin Coach"* and triggers human handoff.

> [!WARNING]
> **Form Isolation Policy**: Chat widget includes strict route checking to ensure it **never renders** on the `/assessment` form page.

---

## Proposed Changes & File Architecture

Project location: `e:\Projects\Clinderma`

```
e:\Projects\Clinderma\
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py             # Config & Environment Provider toggles
│   │   │   ├── prompts.py            # Multi-lingual prompt templates
│   │   │   └── security.py           # API keys, CORS setup
│   │   ├── providers/                # Pluggable Provider Interfaces & Drivers
│   │   │   ├── base.py               # Abstract base classes
│   │   │   ├── llm_provider.py       # Mock/Local & OpenAI/Gemini LLM drivers
│   │   │   ├── vector_provider.py    # Local KB Index & Vector DB drivers
│   │   │   ├── crm_provider.py       # Mock Kylas & Live Kylas API drivers
│   │   │   └── order_provider.py     # Mock Order Lookup driver
│   │   ├── services/
│   │   │   ├── rag_engine.py         # Grounded retrieval & answer generator
│   │   │   ├── language_service.py   # Language detector & translation
│   │   │   └── handoff_manager.py    # Live escalation state & transcript buffer
│   │   ├── api/                      # FastAPI Endpoints
│   │   │   ├── chat.py               # POST /api/chat
│   │   │   ├── leads.py              # POST /api/leads
│   │   │   ├── orders.py             # GET  /api/orders/{id}
│   │   │   ├── handoff.py            # GET/POST /api/handoff
│   │   │   └── health.py             # GET  /api/health
│   │   └── models/                   # Schemas (Pydantic) & DB models
│   ├── scripts/
│   │   └── ingest_kb.py              # Ingests DOCX files from Dataset/
│   ├── requirements.txt
│   └── main.py                       # FastAPI application entry
├── frontend/
│   ├── index.html                    # Website homepage simulation with chat widget
│   ├── assessment.html               # Skin Assessment Form (Widget explicitly blocked)
│   ├── dashboard.html                # Skin Coach Escalation & CRM Leads Dashboard
│   └── widget/
│       ├── chat-widget.js            # Standalone JS Widget with multi-lingual UI
│       └── chat-widget.css           # Premium Clinderma medical-aesthetic UI styling
├── data/
│   ├── kb_index.json                 # Ingested KB store
│   └── clinderma.db                  # SQLite persistent data store
└── README.md                         # Project documentation & scalability guide
```

---

## Verification Plan

### Automated Tests
1. **Ingestion & Data Validation**: Execute `backend/scripts/ingest_kb.py` and verify all 260+ FAQs and 940+ clinical module paragraphs are parsed into `data/kb_index.json`.
2. **Unit & API Integration Tests**: Test `/api/chat`, `/api/leads`, `/api/orders`, and `/api/handoff` endpoints using Python `pytest` / test runner.
3. **Grounding & Fallback Verification**: Run test suite comparing in-scope questions vs out-of-scope questions to confirm zero hallucinations.

### Manual Verification
1. **Website Demo (`index.html`)**: Verify interactive chat in English, Hindi, and Marathi; test order lookup and lead capture.
2. **Skin Assessment Protection (`assessment.html`)**: Confirm chat widget does NOT load.
3. **Agent Dashboard (`dashboard.html`)**: Confirm real-time handoff transcripts and Kylas CRM leads appear.
