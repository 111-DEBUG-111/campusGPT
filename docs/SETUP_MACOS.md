# CampusGPT — macOS Local Development Setup

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | `brew install python@3.11` |
| Node.js | 18+ | `brew install node` |
| Git | Any | Pre-installed on macOS |

---

## Step 1: Clone and Navigate

```bash
git clone https://github.com/yourusername/campusgpt.git
cd campusgpt
```

---

## Step 2: Get Required API Keys

### Google Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com)
2. Click **Get API Key** → Create new key
3. Copy the key

### Qdrant Cloud (Free Tier)
1. Go to [cloud.qdrant.io](https://cloud.qdrant.io)
2. Sign up (free)
3. Click **Create Cluster** → Choose **Free tier** (1GB)
4. Once created, go to **API Keys** → Create API Key
5. Note your **Cluster URL** (e.g., `https://abc123.us-east4-0.gcp.cloud.qdrant.io`)

---

## Step 3: Backend Setup

```bash
cd backend

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
# NOTE: FlagEmbedding will download ~120MB model on first run
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

Edit `.env`:

```bash
GEMINI_API_KEY=your_gemini_api_key
ADMIN_API_KEY=your_strong_random_secret   # Use: openssl rand -hex 32
QDRANT_URL=https://your-cluster.us-east4-0.gcp.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
FRONTEND_URL=http://localhost:5173
```

Start the backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> **First startup takes 1-3 minutes** — it's downloading and loading the embedding model (~120MB) and reranker (~400MB).

Visit `http://localhost:8000/docs` to verify the API is running.

---

## Step 4: Frontend Setup

```bash
cd frontend   # from project root

npm install

# Configure environment
cp .env.example .env
```

Edit `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_ADMIN_KEY=your_strong_random_secret   # Same as ADMIN_API_KEY above
```

Start the frontend:

```bash
npm run dev
```

Visit `http://localhost:5173` — you should see the CampusGPT chat UI.

---

## Step 5: Upload Your First Document

1. Open `http://localhost:5173/admin/login`
2. Enter your `ADMIN_API_KEY`
3. Click **Upload** tab
4. Drag and drop a PDF (e.g., your university handbook)
5. Select the appropriate **Category** (academics, placements, etc.)
6. Click **Upload & Index Document**
7. Wait for status to show **Indexed** (takes 10-60 seconds depending on PDF size)
8. Go back to chat and ask a question!

---

## Troubleshooting

### `GEMINI_API_KEY` not found
```
pydantic_settings.env_settings.SettingsError: error parsing value for field "gemini_api_key"
```
→ Make sure `.env` file exists in the `backend/` directory and contains `GEMINI_API_KEY=...`

### Qdrant connection error
```
qdrant_client.http.exceptions.UnexpectedResponse: Unexpected Response: 401
```
→ Check `QDRANT_URL` and `QDRANT_API_KEY` in your `.env`. The URL should include `https://`.

### Model download stuck
The first run downloads ~500MB of models. If it's slow:
- Check your internet connection
- Models are cached in `~/.cache/huggingface/` — subsequent starts are fast

### Port already in use
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9
# Kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

### CORS errors in browser
Make sure `FRONTEND_URL=http://localhost:5173` is set in `backend/.env`.

---

## Development Tips

- **Hot reload**: Both frontend (`npm run dev`) and backend (`uvicorn --reload`) support hot reload
- **API docs**: Visit `http://localhost:8000/docs` for Swagger UI
- **SQLite viewer**: Use [TablePlus](https://tableplus.com/) or `sqlite3 backend/data/campusgpt.db`
- **BM25 index**: Automatically rebuilt from Qdrant on every backend restart
