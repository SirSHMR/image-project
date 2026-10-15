import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .analyzer import analyze_image
from .video_analyzer import analyze_video

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".webp", ".gif", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv", ".webm"}

MAX_IMAGE_BYTES = 20 * 1024 * 1024    # 20 MB
MAX_VIDEO_BYTES = 100 * 1024 * 1024   # 100 MB

app = FastAPI(title="Image & Video Forensics")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    display_name = Path(file.filename or "upload").name
    suffix = Path(display_name).suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        analyzer, max_bytes, limit_label = analyze_image, MAX_IMAGE_BYTES, "20 ميجابايت"
    elif suffix in VIDEO_EXTENSIONS:
        analyzer, max_bytes, limit_label = analyze_video, MAX_VIDEO_BYTES, "100 ميجابايت"
    else:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم.")

    tmp_path = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}{suffix}"

    size = 0
    try:
        with open(tmp_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"حجم الملف أكبر من {limit_label}.")
                out.write(chunk)

        try:
            # Analysis shells out to exiftool/ffprobe and hashes the file, so run
            # it off the event loop to keep the server responsive for large videos.
            return await run_in_threadpool(analyzer, tmp_path, display_name)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


# Serve the frontend last so /api/* routes above take priority.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
