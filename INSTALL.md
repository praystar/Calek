# HandScribe — Install, Run & Deploy Guide

---

## Prerequisites

Install these once on your machine:

| Tool | Version | Download |
|------|---------|----------|
| Node.js | 18+ | https://nodejs.org |
| Python | 3.10+ | https://python.org |
| Git | any | https://git-scm.com |
| ffmpeg | any | see below |

**Install ffmpeg** (needed for audio transcription):
```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt-get install ffmpeg

# Windows  →  https://ffmpeg.org/download.html
# then add it to your PATH
```

---

## 1. Clone / Open the Project

```bash
# If you cloned from git:
git clone <your-repo-url>
cd handscribe

# Or just cd into the downloaded folder:
cd handscribe
```

---

## 2. Run the ML Backend

```bash
cd ml-backend

# Create a virtual environment
python -m venv venv

# Activate it
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# Install dependencies  (takes ~3 min first time)
pip install -r requirements.txt

# Also install tesseract OCR engine:
# macOS:   brew install tesseract
# Ubuntu:  sudo apt-get install tesseract-ocr
# Windows: https://github.com/UB-Mannheim/tesseract/wiki

# Start the backend
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

Test it: open http://localhost:8000 — should show `{"status":"ok"}`

---

## 3. Run the Frontend

Open a **new terminal** (keep backend running):

```bash
cd frontend

# Install dependencies
npm install

# Create env file
echo "REACT_APP_API_URL=http://localhost:8000" > .env

# Start
npm start
```

Browser opens at **http://localhost:3000** ✓

---

## 4. Get a Gemini API Key (free)

The Chat page needs a Gemini key. Get one free:

1. Go to → https://aistudio.google.com/app/apikey
2. Click **"Create API Key"**
3. Copy the key (starts with `AIza…`)
4. Paste it into the Chat page when prompted — it's saved to your browser only

---

## 5. How to Use (Quick Start)

### Option A — Pick a style (zero setup)
1. Open http://localhost:3000
2. On **Corpus** page → click a style card that looks closest to your writing
3. Done — go use Voice or Chat pages

### Option B — Upload your handwriting (1–3 photos)
1. Take a phone photo of anything you've written (sticky note, notebook, etc.)
2. Corpus page → **"Upload my handwriting"** tab
3. Drop the photo → click **"Auto-match my style"**
4. It finds the closest match from the IAM database automatically

---

## Deploy (Production)

### Frontend → Vercel (free, easiest)

```bash
# Install Vercel CLI
npm i -g vercel

cd frontend

# Build
npm run build

# Deploy
vercel

# Follow prompts. When asked:
# - Framework: Create React App
# - Build command: npm run build
# - Output directory: build
```

Set environment variable in Vercel dashboard:
```
REACT_APP_API_URL = https://your-backend.railway.app
```

Your frontend URL will be: `https://handscribe-xxx.vercel.app`

---

### Backend → Railway (free tier, easiest for Python)

1. Go to https://railway.app → sign up with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repo → select the `ml-backend` folder as root

Add these in Railway's **Variables** tab:
```
PORT = 8000
WHISPER_MODEL = base
```

Add a `Procfile` in `ml-backend/`:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Railway gives you a URL like: `https://handscribe-backend-production.up.railway.app`

---

### Backend → Render (alternative, also free)

1. Go to https://render.com → New → **Web Service**
2. Connect GitHub repo, set root to `ml-backend`
3. Set:
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add env var: `WHISPER_MODEL=base`

Free tier spins down after 15 min of inactivity (cold start ~30s).
Paid tier ($7/mo) stays always-on.

---

### Backend → Fly.io (best performance, free allowance)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

cd ml-backend

# Login
fly auth login

# Launch (first time)
fly launch
# Accept defaults, choose region closest to you

# Set secrets
fly secrets set WHISPER_MODEL=base

# Deploy
fly deploy
```

Fly.io gives 3 shared VMs free, perfect for this app.

---

### Full Stack on a VPS (DigitalOcean / Hetzner)

If you want everything on one server:

```bash
# On your VPS (Ubuntu 22.04):
git clone <repo> && cd handscribe

# Backend
cd ml-backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
sudo apt-get install tesseract-ocr ffmpeg -y

# Run with PM2 (keeps it alive)
npm install -g pm2
pm2 start "uvicorn main:app --host 0.0.0.0 --port 8000" --name handscribe-api

# Frontend
cd ../frontend
npm install && npm run build

# Serve with nginx
sudo apt-get install nginx -y
sudo cp -r build/* /var/www/html/

# nginx config at /etc/nginx/sites-available/default:
# location /api/ { proxy_pass http://localhost:8000/; }
# root /var/www/html;
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: whisper` | Run `pip install openai-whisper` |
| `tesseract not found` | Install tesseract (see step 2 above) |
| Mic not working | Use Chrome; allow mic access in browser |
| CORS error in frontend | Make sure backend is on port 8000 and `.env` is set |
| `torch` install slow | Normal — PyTorch is 800MB. Use `pip install torch --index-url https://download.pytorch.org/whl/cpu` for CPU-only |
| Railway build fails | Add `nixpacks.toml` with `[phases.setup] nixPkgs = ["tesseract", "ffmpeg"]` |
| Vercel `REACT_APP_API_URL` not working | Must prefix with `REACT_APP_` and redeploy after adding |

---

## Summary

```
Local dev:
  Backend  → http://localhost:8000   (uvicorn main:app --reload)
  Frontend → http://localhost:3000   (npm start)

Deploy:
  Frontend → Vercel     (free, 1-click)
  Backend  → Railway    (free tier, easy)
           or Fly.io    (better performance)
           or Render    (free, cold starts)
```
