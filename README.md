# Aperture — Image Metadata & Origin Analysis

A small web tool that reads every metadata field a photo carries (EXIF,
IPTC, XMP, GPS…) using ExifTool, and — when that metadata has been
stripped — falls back to a heuristic "origin fingerprint" built from the
image's own pixel stream (JPEG quantization table, chroma subsampling,
resulting dimensions) to guess which app likely re-encoded it.

## Stack

- **Backend**: FastAPI (Python) + [ExifTool](https://exiftool.org/) + Pillow
- **Frontend**: plain HTML/CSS/JS (no build step), served by FastAPI
- **Deploy target**: Render, as a Docker web service

## Project layout

```
.
├── Dockerfile
├── render.yaml
├── requirements.txt
├── app/
│   ├── main.py          # FastAPI routes
│   ├── analyzer.py       # ExifTool call, hashing, fingerprint logic
│   └── signatures.py     # heuristic "known app" profiles
└── static/
    ├── index.html
    ├── style.css
    └── script.js
```

## Run locally

You need [ExifTool](https://exiftool.org/install.html) installed on your
machine (`brew install exiftool` on macOS, `apt install libimage-exiftool-perl`
on Debian/Ubuntu), or just use Docker (below), which installs it for you.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

### Or with Docker

```bash
docker build -t aperture .
docker run -p 8000:8000 aperture
```

## Deploy to Render

1. Push this folder to a GitHub repository.
2. In Render: **New +** → **Web Service** → connect your repo.
3. Render will detect the `Dockerfile` automatically (or pick
   **Environment: Docker** manually). No build/start command needed —
   they're defined in the Dockerfile.
4. Leave the free plan selected and click **Create Web Service**.
5. First deploy takes a few minutes (installing ExifTool + deps). After
   that, every push to your default branch redeploys automatically.

There's also a `render.yaml` in the repo if you prefer Render's
[Blueprint](https://render.com/docs/blueprint-spec) flow (**New +** →
**Blueprint**).

## Notes / things to extend next

- The "possible source app" guesses in `app/signatures.py` are a small,
  approximate demo table (a handful of popular apps) — not a forensic
  database. Worth mentioning as a known limitation, and a good place to
  keep improving: add more apps, refine the quality/subsampling bands
  from your own test samples.
- Uploaded files are written to a temp path, analyzed, then deleted
  immediately — nothing is persisted or logged.
- Ideas for a v2: GPS coordinates plotted on a map, PDF report export,
  Error Level Analysis (ELA) for tamper detection, batch upload.
