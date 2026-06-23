# CampusGPT — Deployment Guide (Vercel + Render Free Tiers)

This guide walks you through deploying the **CampusGPT** application for the first time. We will use the free tier options for Vercel (frontend SPA hosting) and Render (containerized backend API).

## 1. Production Stack Overview

| Component | Provider / Platform | Cost | Role & Description |
|---|---|---|---|
| **Frontend** | [Vercel](https://vercel.com) | **Free** (Hobby) | Serves the React SPA statically. |
| **Backend** | [Render](https://render.com) | **Free** (Web Service) | Runs the FastAPI app. Spins down after 15 min of inactivity. |
| **Database** | [Neon PostgreSQL](https://neon.tech) | **Free tier** | Relational data + Vector storage (`pgvector`) for embeddings. |
| **Storage** | [Supabase Storage](https://supabase.com) | **Free tier** (1GB) | S3-compatible object storage bucket for uploaded PDFs. |
| **Cache** | [Upstash Redis](https://upstash.com) | **Free tier** | Rate limiting and fast RAG response caching. |
| **LLM Gateway** | [Google AI Studio](https://aistudio.google.com) | **Free tier** | Primary LLM (Gemini 2.5 Flash) + embeddings (gemini-embedding-001). |

> [!WARNING]
> **Render Free Tier Warm-up**: Under Render's free tier, the web service spins down after 15 minutes of inactivity. When a new request arrives, it triggers a "cold start" which can take 30–60 seconds to boot. To keep the service always-on, you can upgrade to Render's **Starter** tier ($7/month).

---

## Step 1: Push Project to GitHub

Make sure all your code is version-controlled and pushed to GitHub. Both Render and Vercel will connect directly to your repository to build and deploy the app automatically.

```bash
git init
git add .
git commit -m "Initial CampusGPT commit"
# Replace with your actual repository URL
git remote add origin https://github.com/yourusername/campusgpt.git
git branch -M main
git push -u origin main
```

---

## Step 2: Set Up Infrastructure

Before deploying the services, create accounts and gather keys from your cloud providers:

### A. Neon PostgreSQL (Core DB & Vector Store)
1. Register at [neon.tech](https://neon.tech) and create a new project.
2. In the Neon dashboard, copy your database connection string under **Connection Details**.
3. **Crucial Formatting**:
   - The connection string will look like: `postgresql://neondb_owner:password@ep-xxxx.neon.tech/neondb`
   - Modify the scheme prefix from `postgresql://` to `postgresql+asyncpg://` so SQLAlchemy can connect asynchronously.
   - Example: `postgresql+asyncpg://neondb_owner:password@ep-xxxx.neon.tech/neondb`

### B. Upstash Redis (Cache & Rate Limiter)
1. Sign up at [upstash.com](https://upstash.com) and create a **Redis Database**.
2. Scroll down to the **REST API** section of your database page and copy the `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.
3. Set `UPSTASH_REDIS_URL` to the `UPSTASH_REDIS_REST_URL` value.
4. Set `UPSTASH_REDIS_TOKEN` to the `UPSTASH_REDIS_REST_TOKEN` value.

### C. Supabase Storage (PDF Documents Bucket)
1. Sign up at [supabase.com](https://supabase.com) and create a project.
2. Navigate to **Storage** in the sidebar → click **New Bucket**. Name the bucket `campusgpt-uploads` (keep it private).
3. In the storage sidebar, click **S3 Connection** and copy your:
   - **Endpoint URL** (looks like `https://<ref>.supabase.co/storage/v1/s3`)
   - **Access Key ID**
   - **Secret Access Key**

### D. Google Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com) and click **Get API Key** to generate your token.

---

## Step 3: Deploy Backend to Render

1. Log in to [render.com](https://render.com) and click **New** → **Blueprint**.
2. Connect your GitHub repository.
3. Render will auto-detect the `render.yaml` file in the root of the repository.
4. Click **Apply** to provision the `campusgpt-api` web service.
5. Provide the following environment variables when prompted by Render:
   - `GEMINI_API_KEY`: Your Google Gemini API Key.
   - `ADMIN_API_KEY`: A strong, random password for securing your administrative uploads dashboard.
   - `FRONTEND_URL`: Put a placeholder like `https://temp-frontend.vercel.app` (you will update this in Step 5 after deploying the frontend).
   - `DATABASE_URL`: The modified `postgresql+asyncpg://...` Neon connection string.
   - `UPSTASH_REDIS_URL`: Your Upstash Redis REST URL.
   - `UPSTASH_REDIS_TOKEN`: Your Upstash Redis REST Token.
   - `STORAGE_ENDPOINT_URL`: The Supabase S3 Connection Endpoint URL.
   - `STORAGE_ACCESS_KEY_ID`: The Supabase Access Key ID.
   - `STORAGE_SECRET_ACCESS_KEY`: The Supabase Secret Access Key.
6. Trigger the deployment. The initial build will build the Python environment and run the startup sequence, which automatically configures table schemas and enables `pgvector` on your Neon database.
7. Once deployed, note down your Render Web Service URL (e.g., `https://campusgpt-api.onrender.com`).

---

## Step 4: Deploy Frontend to Vercel

1. Log in to [vercel.com](https://vercel.com) and click **Add New** → **Project**.
2. Import your GitHub repository.
3. Configure the project:
   - **Framework Preset**: Select `Vite`.
   - **Root Directory**: Select `frontend`.
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Add the following **Environment Variables** (click "Environment Variables" block):
   - `VITE_API_BASE_URL`: The URL of your deployed Render backend (e.g., `https://campusgpt-api.onrender.com`).
   - `VITE_ADMIN_KEY`: The exact same random key you generated for `ADMIN_API_KEY` on Render.
5. Click **Deploy**.
6. Note down your final frontend URL (e.g., `https://campusgpt.vercel.app`).

---

## Step 5: Update CORS Settings on Render

1. Go back to your [Render Dashboard](https://dashboard.render.com).
2. Click on the `campusgpt-api` web service.
3. In the left menu, select **Environment**.
4. Find the `FRONTEND_URL` variable, click edit, and replace the placeholder with your actual Vercel URL (e.g., `https://campusgpt.vercel.app`).
5. Click **Save Changes**. This will trigger a quick, automatic redeployment of the backend with the correct CORS rules allowed.

---

## Step 6: Verify and Use the Application

### 1. Check Backend Health
Open a browser tab or run:
```bash
curl https://campusgpt-api.onrender.com/health
```
You should see:
```json
{
  "status": "healthy",
  "app": "CampusGPT",
  "version": "1.0.0",
  "vectors_count": 0
}
```

### 2. Connect and Upload Official Documents
1. Visit your Vercel URL in your browser.
2. Navigate to `/admin/login` (e.g., `https://campusgpt.vercel.app/admin/login`).
3. Enter your configured admin API key.
4. Upload policy PDF/text files (for example, academic guidelines, hostel manuals). The ingestion pipeline will parse, chunk, embed, and upload them to Supabase Storage and Neon Postgres.
5. Go back to the main chat page, ask questions, and verify that the chatbot correctly retrieves sources and cites documents!
