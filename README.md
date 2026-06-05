# CampusGPT 🎓

> **Production-ready RAG (Retrieval-Augmented Generation) web application for university freshers.**
> Ask anything about academics, placements, clubs, hostel life, and campus policies — answered by AI using your university's own documents.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React+Vite-61dafb)](https://react.dev)
[![Gemini](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-blue)](https://ai.google.dev)
[![Qdrant](https://img.shields.io/badge/Vector%20DB-Qdrant%20Cloud-red)](https://qdrant.tech)

---

## ✨ Features

| Feature | Details |
|---|---|
| 🤖 **AI Chat** | Gemini 2.5 Flash with source citations |
| 🔍 **Hybrid Retrieval** | BM25 + Vector Search + BGE Reranker |
| 📚 **PDF Ingestion** | Upload PDFs, TXT, MD files via admin UI |
| 💬 **Conversation History** | Persistent chat history with SQLite |
| 👍 **Feedback System** | Per-message helpful/not-helpful ratings |
| 📊 **Analytics Dashboard** | Question trends, feedback stats, top queries |
| 🔑 **Admin Dashboard** | Document upload, re-index, delete |
| 🚀 **Deployable** | Vercel (frontend) + Render (backend) free tiers |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (Vercel)                     │
│          React + Vite + TypeScript + Tailwind            │
└────────────────────────┬────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────┐
│                    BACKEND (Render)                      │
│                 Python 3.11 + FastAPI                    │
│                                                          │
│  User Query → Query Rewrite → Hybrid Retrieval (BM25 +  │
│  Vector) → BGE Reranker → Context Assembly →            │
│  Gemini 2.5 Flash → Response + Citations                │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Qdrant Cloud │  │  BM25 Index  │  │  SQLite DB   │  │
│  │  (Vectors)   │  │  (In-memory) │  │  (Metadata)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Backend | Python 3.11 + FastAPI + Uvicorn |
| LLM | Google Gemini 2.5 Flash |
| Embeddings | BAAI/bge-small-en-v1.5 (Render-friendly, ~120MB) |
| Vector DB | Qdrant Cloud Free (persistent, managed) |
| BM25 | rank_bm25 (in-memory, rebuilt from Qdrant) |
| Reranker | BAAI/bge-reranker-base |
| SQL DB | SQLite (async via aiosqlite) |
| State | Zustand |
| Charts | Recharts |

---

## 📁 Project Structure

```
campusGPT/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory
│   │   ├── config.py            # Pydantic Settings
│   │   ├── database.py          # SQLAlchemy async engine
│   │   ├── models.py            # DB models
│   │   ├── schemas.py           # Pydantic schemas
│   │   ├── rag/
│   │   │   ├── embedder.py      # BGE-small embedding singleton
│   │   │   ├── vectorstore.py   # Qdrant wrapper
│   │   │   ├── bm25_index.py    # BM25 in-memory index
│   │   │   ├── reranker.py      # BGE Reranker
│   │   │   ├── retriever.py     # Hybrid retrieval + RRF
│   │   │   ├── query_rewriter.py# Gemini query expansion
│   │   │   ├── ingestion.py     # PDF parsing + chunking
│   │   │   └── pipeline.py      # Full RAG orchestrator
│   │   ├── routers/
│   │   │   ├── chat.py          # POST /api/chat
│   │   │   ├── documents.py     # Admin document management
│   │   │   ├── feedback.py      # POST /api/feedback
│   │   │   ├── analytics.py     # GET /api/admin/analytics
│   │   │   └── health.py        # GET /health
│   │   └── services/
│   │       ├── document_service.py
│   │       └── analytics_service.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/                 # Axios API clients
│   │   ├── components/
│   │   │   ├── chat/            # ChatWindow, MessageBubble, etc.
│   │   │   └── admin/           # DocumentUpload, DocumentList, Analytics
│   │   ├── pages/               # ChatPage, AdminPage, LoginPage
│   │   ├── stores/              # Zustand stores
│   │   ├── types/               # TypeScript types
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── .env.example
└── docs/
    ├── SETUP_MACOS.md
    └── DEPLOYMENT.md
```

---

## 🚀 Quick Start

See [`docs/SETUP_MACOS.md`](docs/SETUP_MACOS.md) for the full macOS local development guide.

### TL;DR

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Fill in GEMINI_API_KEY, QDRANT_URL, QDRANT_API_KEY
uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install
cp .env.example .env
npm run dev
```

Visit `http://localhost:5173` for the chat UI.
Admin dashboard at `http://localhost:5173/admin/login`.

---

## 📖 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Send a message, run RAG pipeline |
| `GET` | `/api/conversations` | List all conversations |
| `GET` | `/api/conversations/:id` | Get conversation with messages |
| `DELETE` | `/api/conversations/:id` | Delete conversation |
| `POST` | `/api/feedback` | Submit message feedback |
| `POST` | `/api/admin/upload` | Upload document (requires X-Admin-Key) |
| `GET` | `/api/admin/documents` | List all documents |
| `DELETE` | `/api/admin/documents/:id` | Delete document |
| `POST` | `/api/admin/reindex` | Rebuild BM25 from Qdrant |
| `GET` | `/api/admin/analytics` | Analytics summary |
| `GET` | `/health` | Health check |

Interactive API docs: `http://localhost:8000/docs`

---

## 🌐 Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full Vercel + Render guide.

---

## 📄 License

MIT — Built for learning and university community use.
