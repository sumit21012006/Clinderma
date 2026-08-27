# 🩺 Clinderma — Customer Support AI Chatbot

Welcome to the **Clinderma Customer Support Chatbot** repository! 

This project is an AI-powered, multi-channel customer support system built for **Clinderma** — a dermatologist-led D2C skincare brand in India. It handles customer FAQs, tracks order statuses, captures sales leads into **Kylas CRM**, and hands off complex queries to human **Skin Coaches** seamlessly.

---

## 🌟 Key Features (What Has Been Built)

### 1. 🧠 Smart & Grounded AI Answers (RAG Engine)
- Uses **Google Gemini 2.0 Flash** and **FAISS Vector Search** over 220+ FAQ and clinical training documents from `Dataset/`.
- **Zero-Hallucination Policy**: If an answer is not found in the Knowledge Base, the chatbot strictly says *"I don't have that specific information"* and connects the customer to a human Skin Coach instead of making up answers.

### 2. 🗣️ Multi-Lingual Support
- Understands and responds natively in **English**, **Hindi (हिन्दी)**, and **Marathi (मराठी)**.
- Features quick language-switch buttons (EN / हिंदी / मराठी) right inside the web chat widget.

### 3. 📞 Automatic Lead Collection & Kylas CRM Integration
- When a customer types their phone number (e.g., `9022905913`), the system automatically detects it, saves it to the SQLite database, and syncs the lead to **Kylas CRM**.

### 4. 📦 Real-Time Order Tracking
- Customers can type their order number (e.g., `CLIN-1001`), and the bot instantly fetches:
  - Current order status (e.g., *In Transit*)
  - Customer name and ordered items
  - Estimated delivery date
  - Live package tracking link

### 5. 🛡️ Skin Assessment Form Protection (Route Guard)
- Per Clinderma's core requirements, the chatbot **MUST NOT interrupt patients** during skin assessment diagnosis.
- The web widget includes a smart route guard script that automatically **hides the chat icon** whenever a user visits the `/assessment.html` page.

### 6. 🩺 Skin Coach & Agent Escalation Dashboard
- Dedicated web dashboard (`/dashboard.html`) for human agents and Skin Coaches.
- Live view of escalated customer sessions with **full chat transcripts** and synced **Kylas CRM leads**.

### 7. 🏗️ Scalable Architecture (Built for Enterprise Growth)
- Uses a **Pluggable Provider Pattern (Strategy Pattern)** via `.env`.
- You can switch from free testing drivers to paid production providers (e.g., OpenAI GPT-4, Qdrant/Pinecone Vector DB, Live Kylas REST API) simply by changing environment variables — **no code rewrite required!**

---

## 🔬 QA & Data Pipeline — Completed Tasks

Beyond the chatbot itself, a comprehensive **Quality Assurance & Data Extraction pipeline** was built to evaluate chatbot accuracy and extract public website content.

### ✅ Task 1: Master FAQ Database Creation
- Parsed Clinderma's official Master FAQ document into a structured JSON database.
- **55 FAQs** organized across **18 categories** and **5 user cohorts** (General, Men, Women, Teens, Acne Timeline & Expectations).
- Each FAQ includes: question, ground-truth answer, expected keywords, and key clinical points.
- **Output**: `WEBSCRAPPER/master_faqs.json`

### ✅ Task 2: Blog Content Extraction
- Built an automated scraper to discover and extract **all 51 publicly accessible blog articles** from `theclinderma.com`.
- Handles Next.js React Server Components (RSC) payloads (`self.__next_f.push(...)`) to extract embedded HTML content.
- Pipeline: Sitemap discovery → URL deduplication → RSC parsing → HTML-to-text extraction.
- **Output**: `WEBSCRAPPER/clinderma_all_blogs.json` (51 articles with title + full content)

### ✅ Task 3: Live Chatbot Benchmarking (WebSocket)
- Developed an automated evaluation harness that connects to the **live Kandid AI WebSocket** endpoint.
- Sends each Master FAQ question as a real user message and captures the full chatbot response.
- Scores each response using two metrics:
  - **Keyword Coverage** — % of expected clinical keywords present in the bot's response.
  - **Key Point Coverage** — % of required clinical talking points covered.
  - **Overall Alignment Score** — weighted combination of both metrics.
- Ran benchmarks for all 5 cohorts independently, generating JSON + Markdown reports for each.
- **Output**: `WEBSCRAPPER/comparison_results/FAQ_Comparision_*.json` and `.md` files

### ✅ Task 4: Presentation-Quality PDF Analysis Report
- Built a custom `reportlab` + `matplotlib` report generator producing a **10-page professional PDF**.
- Report includes:
  - Executive KPI cards (67.7% overall alignment, 74.2% keyword coverage, 63.3% key-point coverage)
  - Cohort performance grouped bar chart with 70% target line
  - Category-level breakdown sorted worst-to-best (18 categories)
  - Full FAQ-by-FAQ detail table (all 59 evaluated FAQs)
  - Keyword vs Key-Point scatter plot with alignment colour gradient
  - Critical gap deep-dive (6 lowest-scoring FAQs with expected vs actual responses)
  - Top performers table (FAQs scoring ≥ 90%)
  - 4 strategic recommendations for system-prompt improvement
- **Output**: `reports/Clinderma_Chatbot_FAQ_Analysis_Report.pdf`

### 📊 Key Benchmark Findings

| Cohort | FAQs | Alignment | Keywords | Key Points | Assessment |
|--------|------|-----------|----------|------------|------------|
| General | 42 | 64.9% | 75.8% | 57.5% | Adequate |
| Men | 8 | 75.0% | 68.8% | 79.2% | Strong |
| Women | 2 | 70.0% | 75.0% | 66.7% | Adequate |
| Teens | 3 | 88.9% | 72.2% | 100.0% | Strong |
| Acne Timeline | 4 | 65.4% | 69.8% | 62.5% | Adequate |

---

## 📁 Project Structure

```
Clinderma/
├── Dataset/                                  # Raw client datasets (.docx, .pdf, .jpeg)
│   ├── CLINDERMA – MASTER FAQs DOCUMENT (1).docx
│   ├── Clinderma Customer Support Chatbot.pdf
│   ├── Clinderma module.docx
│   └── System_Flow.jpeg
├── WEBSCRAPPER/                              # QA & Data Extraction Pipeline
│   ├── master_faqs.json                      # 55 structured Master FAQs (ground-truth)
│   ├── clinderma_all_blogs.json              # 51 extracted blog articles
│   ├── compare_chatbot_with_faqs.py          # Live WebSocket chatbot benchmarking harness
│   ├── scrape_all_blogs.py                   # Blog content scraper (Next.js RSC parser)
│   ├── generate_pdf_report.py                # Professional PDF report generator
│   ├── analyze_comparison_json.py            # Comparison data analysis utility
│   ├── blog_parser.py                        # Individual blog article parser
│   ├── discover_blogs.py                     # Blog URL discovery script
│   ├── kandid_scraper.py                     # Kandid AI WebSocket client
│   ├── comparison_results/                   # Benchmark results (JSON + Markdown per cohort)
│   │   ├── FAQ_Comparision_General.json
│   │   ├── FAQ_Comparision_Men.json
│   │   ├── FAQ_Comparision_Women.json
│   │   ├── FAQ_Comparision_Teens.json
│   │   └── FAQ_Comparision_Acne_Timeline_Expectations.json
│   └── sample_queries.txt                    # Test query samples
├── backend/
│   ├── app/
│   │   ├── api/                              # FastAPI REST routes (chat, leads, orders, handoff)
│   │   ├── core/                             # Environment settings & config
│   │   ├── models/                           # Pydantic schemas
│   │   ├── providers/                        # Pluggable Strategy drivers (LLM, Vector, CRM, Order)
│   │   └── services/                         # RAG engine, language detector, handoff manager
│   ├── scripts/
│   │   └── ingest_kb.py                      # Dataset parser & FAISS embedding index generator
│   ├── .env.example                          # Environment template
│   ├── main.py                               # FastAPI application entry point
│   └── requirements.txt                      # Python dependencies
├── frontend/
│   ├── index.html                            # Main website landing page simulation
│   ├── assessment.html                       # Skin Assessment questionnaire (Widget disabled)
│   ├── dashboard.html                        # Skin Coach & CRM Agent Dashboard
│   └── widget/
│       ├── chat-widget.js                    # Embeddable JS Chat Widget + Route Protection
│       └── chat-widget.css                   # Clinderma medical skincare UI styling
├── data/                                     # Generated FAISS vector index & SQLite database
├── reports/                                  # Generated analysis reports
│   └── Clinderma_Chatbot_FAQ_Analysis_Report.pdf   # 10-page QA evaluation report
├── implementation_plan.md                    # Technical architecture assessment document
├── README.md                                 # Project documentation (this file)
└── .gitignore                                # Secret & data protection rules
```

---

## 🚀 How to Run the Project Locally (Step-by-Step)

### Prerequisites
- Python 3.9+ installed on your computer.

### Step 1: Navigate to Project Directory
```bash
cd Clinderma
```

### Step 2: Set Up Environment Variables
Create a file named `.env` inside the `backend/` folder (or copy from `backend/.env.example`):
```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
LLM_MODEL=gemini-2.0-flash
EMBEDDING_MODEL=gemini-embedding-001
LLM_PROVIDER=gemini
VECTOR_STORE_PROVIDER=faiss
CRM_PROVIDER=mock_kylas
ORDER_PROVIDER=mock_orders
GROUNDING_THRESHOLD=0.35
```

### Step 3: Install Python Dependencies
```bash
pip install -r backend/requirements.txt
```

### Step 4: Generate the Vector Database Index
Run this script once to process the `.docx` documents in `Dataset/` and build the semantic FAISS vector index:
```bash
python backend/scripts/ingest_kb.py
```

### Step 5: Start the Backend Server
```bash
python backend/main.py
```

### Step 6: Test in Your Web Browser
Open your browser and visit:
- 🌐 **Clinderma Website + Live Chat Widget**: `http://localhost:8000/`
- 📋 **Skin Assessment Form (Widget Suppressed)**: `http://localhost:8000/assessment.html`
- 🩺 **Skin Coach Dashboard**: `http://localhost:8000/dashboard.html`
- 📖 **Interactive Swagger API Documentation**: `http://localhost:8000/docs`

---

## 🧪 Testing Scenarios You Can Try Right Away

| What to Test | What to Type / Click | Expected Behavior |
|---|---|---|
| **Greetings** | Type *"Hi"* or *"Hello"* | Bot welcomes user warmly and presents key topics. |
| **Grounded FAQ** | Type *"What is purging?"* | Bot gives accurate dermatological explanation from FAQ doc. |
| **Paraphrased FAQ** | Type *"my face is breaking out badly after starting, is this normal?"* | Semantic search matches the purging FAQ and provides grounded answer. |
| **Multi-lingual** | Type *"acne ka treatment kitna time lagta hai?"* | Bot responds in Hindi with treatment timeline details. |
| **Order Tracking** | Type *"Track order CLIN-1001"* | Bot displays live order status, customer name, items, and tracking link. |
| **Lead Collection** | Type *"9022905913"* | Bot captures phone number, confirms lead creation, and syncs to Kylas CRM. |
| **Human Escalation** | Type *"I want to talk to a skin coach"* | Bot transfers chat session to human queue. |
| **Out-of-Scope Query** | Type *"What is the capital of France?"* | Bot declines to answer ungrounded queries and offers Skin Coach handoff. |
| **Form Protection** | Open `/assessment.html` | Chat widget button is completely hidden from UI. |
| **Agent View** | Open `/dashboard.html` | Displays active handoffs and Kylas CRM leads in real time. |

---

## 🌐 Deploying Online (Free Hosting Options)

### Render.com (Recommended for Free Permanent Link)
1. Push repository to GitHub.
2. Log into [Render.com](https://render.com) and create a **Web Service**.
3. Connect repo and set:
   - **Build Command**: `pip install -r backend/requirements.txt && python backend/scripts/ingest_kb.py`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variable**: `GEMINI_API_KEY` = `<your_key>`
4. Render will generate a public URL (e.g. `https://clinderma-chatbot.onrender.com`).

---

## 👥 Point of Contact & Project Info
- **Project**: Clinderma Customer Support Chatbot + QA Pipeline
- **Tech Stack**: Python, FastAPI, Google Gemini 2.0 Flash, FAISS Vector Search, SQLite, HTML5/CSS3/JS
- **QA Pipeline**: WebSocket automation, reportlab, matplotlib, Next.js RSC parsing
- **GitHub Repository**: [github.com/sumit21012006/Clinderma](https://github.com/sumit21012006/Clinderma)
