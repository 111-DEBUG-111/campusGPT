# CampusGPT 🎓

### *Production-Ready Hybrid RAG Platform for University Communities*

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React+Vite-61dafb?logo=react&logoColor=black)](https://react.dev)
[![Gemini](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-blue?logo=googlegemini&logoColor=white)](https://ai.google.dev)
[![Postgres](https://img.shields.io/badge/DB-Neon%20Postgres-006400?logo=postgresql&logoColor=white)](https://neon.tech)
[![pgvector](https://img.shields.io/badge/Vector%20DB-pgvector-blue)](https://github.com/pgvector/pgvector)
[![Upstash Redis](https://img.shields.io/badge/Cache-Upstash%20Redis-red?logo=redis&logoColor=white)](https://upstash.com)

---

## 1. Project Overview

**CampusGPT** is a production-grade, highly optimized Retrieval-Augmented Generation (RAG) platform tailored for university ecosystems. It acts as an intelligent, context-aware chatbot designed to help students—particularly incoming freshers—find instant, verified, and source-attributed answers about academics, hostel rules, placements, campus clubs, and administrative policies. 

### Core Objectives:
*   **Fact-Aligned Accuracy:** Eliminates model hallucinations by grounding LLM responses in real, admin-verified university documentation.
*   **Peer & Institutional Boundary Enforcement:** Segregates official rules from student-contributed insights to prevent misinformation.
*   **Production-Ready Resilience:** Implements multi-provider LLM fallback routing (Gemini 2.5 Flash as primary, Qwen 3 32B via Groq as secondary) to ensure zero downtime.
*   **Cost-Efficient Serverless Architecture:** Optimized to deploy seamlessly on standard cloud free tiers without compromising latency or search precision.

---

## 2. High-Level Architecture

CampusGPT decouples concerns into a responsive React frontend client and a high-performance Python/FastAPI backend API orchestrating the pipeline.

```
                    ┌───────────────────────────────────────────────┐
                    │               CLIENT / BROWSER                │
                    │  React (Vite) + Zustand + Tailwind + Recharts │
                    └───────────────────────┬───────────────────────┘
                                            │ REST API / Session Token
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │             BACKEND API (Render)              │
                    │            FastAPI (Python 3.11+)             │
                    └──────┬─────────────────┬───────────────┬──────┘
                           │                 │               │
                           ▼                 ▼               ▼
                    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                    │ pgvector DB  │  │  BM25 Index  │  │  Upstash     │
                    │ (Neon Cloud) │  │  (In-Memory) │  │  Redis Cache │
                    └──────────────┘  └──────────────┘  └──────────────┘
                           ▲                                 ▲
                           │                                 │
                           ▼                                 ▼
                    ┌──────────────┐                  ┌──────────────┐
                    │ Supabase S3  │                  │ LLM Gateway  │
                    │ (Doc Store)  │                  │ Gemini/Groq  │
                    └──────────────┘                  └──────────────┘
```

*   **Frontend SPA:** Built with React 18, Vite, TypeScript, and Tailwind CSS. Employs Zustand for lightweight state management and Recharts for admin analytics. Scopes operations using a unique visitor `X-Session-Token` stored in the browser's `localStorage`.
*   **Backend REST API:** Powered by FastAPI and asynchronous SQLAlchemy. Connects to serverless Neon PostgreSQL using the native `asyncpg` driver with connection pooling configured to survive Neon's cold idle phases.
*   **Database & Storage Layer:**
    *   **Relational & Vector Data:** Neon PostgreSQL houses application data (conversations, messages, feedback, documents, analytics events) and the `document_chunks` table utilizing the `pgvector` extension.
    *   **In-Memory Keyword Index:** A local Rank-BM25 index is built dynamically from database chunks to support instant sparse keyword search.
    *   **Cold Storage:** Raw files (PDFs, Markdown, TXT) are uploaded to an S3-compatible Supabase Storage bucket.
    *   **Distributed Cache:** Upstash Redis handles shared API rate-limiting and caches RAG responses.

---

## 3. RAG Pipeline

The RAG pipeline operates as a deterministic, multi-stage orchestration that optimizes queries, retrieves relevant contexts, and generates responses.

```
 User Query ────► Query Rewrite ────► Hybrid Retrieval ────► Reranking ────► Generation
                  (Gemini 2.5)       (pgvector + BM25)      (BGE-Rerank)    (Gemini / Qwen)
                                                                                  │
                                                                                  ▼
                                                                           Cited Response
```

1.  **Progress Tracking:** The API emits real-time progress stages to the client during execution: `Rewriting Query` → `Retrieving Documents` → `Reranking Results` → `Generating Response` → `Complete`.
2.  **Query Rewriting & Expansion:** The user's query is expanded by Gemini 2.5 Flash into up to 3 query variations to address colloquial terms and spelling mistakes.
3.  **Parallel Hybrid Retrieval:**
    *   **Dense Semantic Search:** Generates BGE embeddings (1024-dim BGE-M3 or 384-dim BGE-Small) and queries Neon `pgvector` via cosine similarity (`<=>` operator).
    *   **Sparse Keyword Search:** Queries the in-memory Rank-BM25 index with the expanded terms.
4.  **Reciprocal Rank Fusion (RRF):** Merges the ranked outputs of dense and sparse results using reciprocal ranking.
5.  **Cross-Encoder Reranking:** Feeds the top candidates through `bge-reranker-base` to calculate exact semantic scores, sorting the final context to the top 5 chunks.
6.  **Resilient Generation & Fallback:**
    *   **Primary:** Gemini 2.5 Flash synthesizes the context and generates the answer.
    *   **Groq Fallback:** If Gemini hits rate limits (HTTP 429) or transient errors (HTTP 502/503), the gateway reroutes to Qwen-32B via Groq. Groq prompts are dynamically truncated to fit within Groq's TPM limits.
    *   **Safety Filter Handling:** Catches safety blocks immediately and outputs clean, non-technical error messages.

---

## 4. Knowledge Source Architecture

CampusGPT partitions institutional facts from peer experiences using **Knowledge Source Modes**. This ensures that official policies are never mixed with casual student feedback.

| Mode | Target Scope | UI Response Presentation | Citation Formatting |
|---|---|---|---|
| **`hybrid`** | Official + Experience | Split into two clear blocks: `### Official Information` & `### Student Insight`. | Citations show source type and author details. |
| **`official`** | Official Documents Only | Formally structured, precise, and strictly institutional. | "According to the Student Handbook..." |
| **`experience`** | Student Insights Only | Relatable, conversational tone with a standard disclaimer. | "Based on student experiences..." |

*   **Metadata Inheritance:** During document ingestion, all generated chunks inherit the parent document's properties (`source_type = "official" | "experience"` and `author` value if peer-contributed).
*   **Search Isolation:** Vector and BM25 searches filter candidate chunks on the `source_type` property *before* merging or reranking, preventing cross-contamination.

---

## 5. Document Ingestion Pipeline

CampusGPT supports importing PDF, Markdown (`.md`), and plain text (`.txt`) documents, processing them through a structure-aware extraction sequence.

```
 Upload File ──► Cold Storage ──► Parsing & Extracting ──► Semantic Chunking ──► Embed & Index
 (Admin UI)     (Supabase S3)     (PyMuPDF + pdfplumber)   (NLTK Section Tree)  (pgvector + BM25)
```

1.  **S3 Upload:** Raw files are uploaded via the Admin panel directly into Supabase Storage.
2.  **Dual-Engine Extraction:**
    *   *PyMuPDF (fitz)* acts as the primary parser (fast and lightweight).
    *   *pdfplumber* acts as a fallback for complex structures or scanned sheets.
    *   *Table Extractor:* Automatically converts PDF tables into Markdown pipe tables, marking them as atomic regions so they are never split by the chunker.
3.  **Structure-Aware Chunking (SemanticChunker):**
    *   Parses document headings using a `HeadingDetector` regex engine that identifies Markdown headers (`#`), numbered items (`1.2.1`), and styled short lines.
    *   Assembles a hierarchical `SectionNode` tree representing the document.
    *   Splits body paragraphs into sentences using NLTK's `sent_tokenize`.
    *   Greedily packs sentences into token-budgeted chunks (e.g. 800 tokens for BGE-M3) with a 1-sentence contextual lookback overlap.
    *   Prepend the section title and full breadcrumb path (e.g. `Academic Policies > Exam Guidelines`) to the text of each chunk, ensuring high embedding alignment.
4.  **Batch Embedding:** Generates embeddings using `FlagEmbedding` with FP16 precision.
5.  **Upsert:** Inserts the vector records into the Neon `document_chunks` table and triggers a BM25 index refresh.

---

## 6. Deployment Architecture

CampusGPT is designed to run efficiently on free tiers, utilizing optimization layers to maintain fast response times:

*   **Frontend (Vercel):** Deployed as a static React client. Built with Vite to optimize static asset compression.
*   **Backend (Render):** Deployed as a containerized Python Web Service.
    *   *Cold Start Optimization:* Render free tier web services spin down after 15 minutes of inactivity. To bypass the slow boot caused by re-downloading model weights (~500MB), mount a **Render Persistent Disk** at `/data`. Set `HF_HOME=/data/hf_cache` and `BM25_CACHE_DIR=/data/bm25_cache` to keep models and indexes cached.
*   **Vector & Core Database (Neon):** Hosted on serverless Neon PostgreSQL. The database automatically spins down when idle and is kept awake during queries via SQLAlchemy's `pool_pre_ping`.
*   **Storage (Supabase):** 1GB free S3-compatible storage holds original documents.
*   **Caching & Limiter (Upstash Redis):** A serverless Redis instance manages API rate throttling and caches RAG responses.

---

## 7. Features

*   💬 **Progressive RAG Chat:** Conversational interface displaying live pipeline phases.
*   📌 **Granular Citations:** Popovers containing filenames, page numbers, breadcrumb paths, and original text snippets.
*   🔄 **Automatic Failover:** Transparent routing between Google Gemini 2.5 Flash and Groq Qwen-32B to ensure uptime.
*   🔑 **Admin Dashboard:** Secure interface for uploading documents, viewing files, reindexing, and purging database chunks.
*   📊 **Feedback & Analytics:** Review helpful/unhelpful feedback, request latencies, and monitor "Knowledge Gaps" (queries that returned empty contexts).
*   ⏱️ **Cold Start Caching:** Disk-persistent caches for model weights and BM25 indexes to minimize cold starts.

---

## 8. Screenshots

*Visual walkthrough of the client and administrative dashboards:*

| User Chat Interface & Citations | Admin Portal & Live Analytics |
|---|---|
| ![Chat UI](https://raw.githubusercontent.com/google/antigravity/main/docs/images/chat_ui_placeholder.png) | ![Admin UI](https://raw.githubusercontent.com/google/antigravity/main/docs/images/admin_ui_placeholder.png) |

*(Note: Replace these URLs with real images after capturing snapshots of your deployment).*

---

## 9. Tech Stack

*   **Frontend:** React 18, Vite, TypeScript, Tailwind CSS, Zustand, Recharts, Axios, Lucide Icons.
*   **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2.0 (Async), asyncpg, Pydantic v2.
*   **Embeddings & Search:** BAAI/bge-m3 / BAAI/bge-small-en-v1.5, BAAI/bge-reranker-base, Rank-BM25, NLTK (punkt/punkt_tab).
*   **Databases:** PostgreSQL (Neon) with pgvector, Upstash Redis.
*   **Extractors:** PyMuPDF (fitz), pdfplumber.
*   **API Integrations:** Google GenAI SDK (Gemini), Groq API, Supabase S3 client (Boto3).

---

## 10. Setup Instructions

Refer to [SETUP_MACOS.md](docs/SETUP_MACOS.md) and [DEPLOYMENT.md](docs/DEPLOYMENT.md) for full configuration guidelines.

### Local Development Quick Start

#### Prerequisites
*   **Python 3.11+** (`brew install python@3.11` on macOS)
*   **Node.js 18+** (`brew install node` on macOS)
*   **PostgreSQL** instance with `pgvector` enabled (or a free Neon project)
*   **Supabase Bucket** credentials
*   **Gemini API Key** (from [Google AI Studio](https://aistudio.google.com))

#### 1. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit the local `.env` file:
```env
GEMINI_API_KEY=your_gemini_api_key
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
STORAGE_ENDPOINT_URL=https://<ref>.supabase.co/storage/v1/s3
STORAGE_ACCESS_KEY_ID=your_access_id
STORAGE_SECRET_ACCESS_KEY=your_secret_key
# Optional:
GROQ_API_KEY=your_groq_key
UPSTASH_REDIS_URL=your_redis_url
UPSTASH_REDIS_TOKEN=your_redis_token
```

Start the FastAPI application:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
*Note: First startup downloads model weights (~500MB) and may take up to 2 minutes.*

#### 2. Frontend Setup
In a new terminal:
```bash
cd frontend
npm install
cp .env.example .env
```

Edit `frontend/.env`:
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_ADMIN_KEY=change-me-in-production
```

Run the Vite development server:
```bash
npm run dev
```

Visit `http://localhost:5173` to chat, or navigate to `http://localhost:5173/admin/login` to authenticate and upload your documents.
