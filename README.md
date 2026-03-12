# ✍️ HandScribe — Personal Handwriting Synthesis System

An end-to-end ML system that learns your handwriting style and renders any text in it.

---

## 📐 Architecture

```
handscribe/
├── frontend/               # React 18 UI
│   └── src/
│       ├── pages/
│       │   ├── CorpusPage.jsx     ← Upload & analyze handwriting samples
│       │   ├── VoicePage.jsx      ← Speak → handwriting
│       │   └── ChatPage.jsx       ← Gemini chatbot → handwriting
│       ├── components/
│       │   └── HandwritingCanvas.jsx
│       └── styles/global.css
│
└── ml-backend/             # FastAPI + PyTorch
    ├── main.py                    ← FastAPI entry point
    ├── models/
    │   └── handwriting_model.py   ← CVAE-GAN synthesis model
    ├── utils/
    │   ├── character_extractor.py ← Segment glyphs from images
    │   ├── style_analyzer.py      ← Extract style metrics
    │   └── font_synthesizer.py    ← Fill missing glyphs
    └── routes/
        ├── corpus.py              ← /corpus/analyze, /synthesize, /train
        ├── render.py              ← /render
        └── transcribe.py          ← /transcribe (Whisper ASR)
```

---

## 🤖 Is This an ML Project?

**Yes — multiple ML components:**

| Component | Method | Library |
|-----------|--------|---------|
| Glyph extraction | Connected component analysis + OCR | OpenCV, EasyOCR |
| Style encoding | Variational Autoencoder | PyTorch |
| Character synthesis | CVAE-GAN (conditional) | PyTorch |
| Missing glyph fill | Font + style transfer | Pillow, CV2 |
| Speech transcription | Whisper ASR | OpenAI Whisper |
| AI chat | Gemini 2.0 Flash | Google AI SDK |

---

## 📦 Datasets

### Required for training from scratch

#### 1. IAM Handwriting Database ⭐ (Primary)
**Best dataset for English handwriting synthesis**
- 1,539 pages of scanned text, 657 writers
- Word/line/form level segmentation
- Download: https://fki.tic.heia-fr.ch/databases/iam-handwriting-database
- Registration required (free academic access)
- Place in: `ml-backend/data/iam/`

#### 2. EMNIST Dataset ⭐ (Character-level)
**Best for individual character classification**
- 814,255 character images (balanced split)
- Direct download (no registration):
  ```bash
  # Using torchvision (automatic)
  python -c "from torchvision.datasets import EMNIST; EMNIST('./data', split='balanced', download=True)"
  ```
- Place in: `ml-backend/data/emnist/`

#### 3. CVL Database (Writer identification)
**Useful for style transfer and writer-specific models**
- 310 writers, multiple writing samples
- Download: https://cvl.tuwien.ac.at/research/cvl-databases/an-off-line-database-for-writer-retrieval-writer-identification-and-word-spotting/
- Place in: `ml-backend/data/cvl/`

#### 4. GNHK Dataset (Scene text)
**Additional diversity**
- Download: https://www.semanticscholar.org/paper/GNHK%3A-A-Dataset-for-English-Handwriting-in-the-Wild-Lee-Kim/
- Place in: `ml-backend/data/gnhk/`

### For your own handwriting (minimal dataset)
- **Minimum**: 5–10 pages of handwritten text
- **Recommended**: 20+ pages with varied content
- **Format**: High-res scans (300 DPI+), PNG or TIFF
- **Content**: Include all 26 letters (upper+lower), digits, punctuation

---

## 🚀 Setup

### Frontend
```bash
cd frontend
npm install
cp .env.example .env
# Edit .env: set REACT_APP_API_URL=http://localhost:8000
npm start
```

### ML Backend
```bash
cd ml-backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Install system dependencies
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr ffmpeg libsndfile1

# macOS:
brew install tesseract ffmpeg libsndfile

uvicorn main:app --reload --port 8000
```

### Environment Variables
```bash
# frontend/.env
REACT_APP_API_URL=http://localhost:8000

# ml-backend/.env (optional)
MODEL_DIR=data/models
WHISPER_MODEL=base     # base | small | medium | large
```

---

## 🎯 Usage Flow

### 1. Corpus Ingestion (Corpus page)
1. Scan your handwritten pages (300 DPI, high contrast)
2. Upload to the **Corpus** page
3. Click **Analyze Corpus** — extracts glyphs, measures style
4. Click **Synthesize missing glyphs** — fills gaps using font + style transfer
5. Preview render in your style

### 2. Voice → Handwriting (Voice page)
1. Click the mic button
2. Speak naturally
3. Stop recording — Whisper transcribes your speech
4. Edit transcript if needed → click **Render**

### 3. AI Chat → Handwriting (Chat page)
1. Add your Gemini API key (get free at aistudio.google.com)
2. Ask anything to Gemini
3. Click **"Write in my handwriting"** on any response
4. Adjust rendering options (ink color, paper style, size)
5. Export as PNG or PDF

---

## 🏗️ Model Training

### Quick start (your corpus only)
```python
# After uploading corpus via the UI, trigger training:
curl -X POST http://localhost:8000/corpus/train?epochs=50
```

### Full training on IAM + your corpus
```python
# ml-backend/train.py
from models.handwriting_model import HandwritingSynthesizer
from data.iam_loader import IAMDataLoader

loader = IAMDataLoader("data/iam/")
model = HandwritingSynthesizer()

# Pre-train on IAM
model.pretrain_iam(loader, epochs=100)

# Fine-tune on your corpus
model.train_on_corpus(your_glyph_library, epochs=50)
```

Training time estimates:
- CPU only: ~2h for 50 epochs (small corpus)
- GPU (RTX 3060+): ~15min for 50 epochs

---

## 🔌 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /corpus/analyze` | multipart | Upload images, extract glyphs & style |
| `POST /corpus/synthesize` | JSON | Generate missing glyphs |
| `POST /corpus/train` | POST | Fine-tune model on corpus |
| `POST /render` | JSON | Text → handwriting PNG |
| `POST /transcribe` | multipart | Audio → text (Whisper) |
| `GET /health` | GET | Server status + GPU info |

---

## 🧠 How the ML Works

### 1. Glyph Extraction Pipeline
```
Image → Binarize (Adaptive threshold)
      → Deskew (Hough transform)
      → Line segmentation (H-projection)
      → Word segmentation (V-projection)
      → Character segmentation (Connected components)
      → OCR labeling (EasyOCR)
      → Normalize to 64×64
```

### 2. Style Encoding (VAE)
- Reference glyphs → CNN → μ, σ → 128-dim style vector
- Captures: slant, stroke width, pressure, letter form

### 3. Character Synthesis (Generator)
- Input: character class (one-hot) + style vector + noise
- Output: 64×64 glyph image matching your style
- Training loss: adversarial + character classification + KL divergence

### 4. Missing Glyph Gap-Filling
- Font rendering → elastic distortion → stroke width matching → pressure simulation
- Matches your extracted style metrics automatically

---

## 📝 Handwriting Tips for Best Results

- Use **black ink on white paper** (or dark ink on light paper)
- Scan at **300 DPI minimum** (600 DPI preferred)
- Include **all characters** you'll want to render
- Write the **pangram** multiple times:
  `The quick brown fox jumps over the lazy dog`
- Also write: `Pack my box with five dozen liquor jugs`
- Include **numbers**: `1234567890`
- Include **punctuation**: `. , ! ? ' " ( ) - ; :`

---

## 🗺️ Roadmap

- [ ] Real-time canvas rendering (WebGL)
- [ ] Connected cursive synthesis (not just isolated glyphs)
- [ ] Ink simulation (variable width Bézier curves)
- [ ] Multi-page PDF export
- [ ] Style mixing (blend two handwriting styles)
- [ ] Mobile app (React Native)
