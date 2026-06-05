# CampusGPT — Deployment Guide (Vercel + Render Free Tiers)

## Overview

| Component | Platform | Cost | Notes |
|---|---|---|---|
| Frontend | Vercel | **Free** | Hobby plan |
| Backend | Render | **Free** | 512MB RAM, sleeps after 15min |
| Vector DB | Qdrant Cloud | **Free** | 1GB storage |
| LLM | Gemini API | **Free tier** | 15 req/min free |

> ⚠️ **Render free tier caveat**: The service sleeps after 15 minutes of inactivity and takes ~30-60 seconds to cold-start. Upgrade to Render Starter ($7/mo) for always-on.

---

## Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial CampusGPT commit"
git remote add origin https://github.com/yourusername/campusgpt.git
git push -u origin main
```

---

## Step 2: Deploy Backend to Render

1. Go to [render.com](https://render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Configure:
   - **Name**: `campusgpt-api`
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`

4. Add **Environment Variables** (click "Advanced" → "Add Environment Variable"):

   | Key | Value |
   |---|---|
   | `GEMINI_API_KEY` | your Gemini API key |
   | `ADMIN_API_KEY` | a strong random secret |
   | `QDRANT_URL` | your Qdrant Cloud URL |
   | `QDRANT_API_KEY` | your Qdrant API key |
   | `FRONTEND_URL` | `https://your-app.vercel.app` (fill in after step 3) |
   | `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` |
   | `RERANKER_MODEL` | `BAAI/bge-reranker-base` |
   | `DATABASE_URL` | `sqlite+aiosqlite:///./data/campusgpt.db` |
   | `UPLOAD_DIR` | `./data/uploads` |

5. Click **Create Web Service**

> ⏳ First deploy takes ~5-10 minutes (downloading model weights). Subsequent deploys are faster.

6. Note your Render URL: `https://campusgpt-api.onrender.com`

---

## Step 3: Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) → **New Project**
2. Import your GitHub repo
3. Configure:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

4. Add **Environment Variables**:

   | Key | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://campusgpt-api.onrender.com` |
   | `VITE_ADMIN_KEY` | same as `ADMIN_API_KEY` on Render |

5. Click **Deploy**

6. Note your Vercel URL: `https://campusgpt.vercel.app`

---

## Step 4: Update CORS

Go back to Render → your service → **Environment** → Update `FRONTEND_URL`:
```
FRONTEND_URL=https://campusgpt.vercel.app
```

Trigger a redeploy (Render → Manual Deploy → Deploy latest commit).

---

## Step 5: Verify Deployment

```bash
# Check backend health
curl https://campusgpt-api.onrender.com/health

# Expected response:
# {"status":"healthy","app":"CampusGPT","version":"1.0.0","bm25_chunks":0}
```

Visit your Vercel URL → you should see the CampusGPT chat UI.

---

## Post-Deployment: Upload Documents

1. Open `https://campusgpt.vercel.app/admin/login`
2. Enter your `ADMIN_API_KEY`
3. Upload your university PDFs
4. Test the chat interface

---

## Upgrading Beyond Free Tier

| Issue | Solution | Cost |
|---|---|---|
| Backend sleeps | Render Starter plan | $7/mo |
| SQLite not persistent on Render | Mount a Render Disk | $1/mo (0.5GB) |
| Need more Qdrant storage | Qdrant Cloud paid | $25/mo |
| High LLM costs | Switch to `gemini-flash-8b` | Cheaper |

---

## Custom Domain

### Vercel
- Settings → Domains → Add your domain → Update DNS records

### Render
- Settings → Custom Domains → Add domain

---

## Environment Variables Reference

### Backend (Render)
```
GEMINI_API_KEY=          # Required
ADMIN_API_KEY=           # Required — keep secret!
QDRANT_URL=              # Required
QDRANT_API_KEY=          # Required
FRONTEND_URL=            # Required for CORS
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RERANKER_MODEL=BAAI/bge-reranker-base
DATABASE_URL=sqlite+aiosqlite:///./data/campusgpt.db
UPLOAD_DIR=./data/uploads
RATE_LIMIT_PER_MINUTE=20
DEBUG=false
```

### Frontend (Vercel)
```
VITE_API_BASE_URL=https://campusgpt-api.onrender.com
VITE_ADMIN_KEY=          # Same as ADMIN_API_KEY
```
