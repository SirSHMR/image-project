import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, JpegImagePlugin

from .signatures import guess_source_app

# Standard IJG luminance quantization table (quality ~50), used as a
# reference point to *estimate* JPEG quality from the file's own
# quantization table. This is an approximation for demo purposes, not
# a byte-exact reconstruction of the original encoder's quality slider.
_BASE_LUMA_TABLE = [
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
]


def compute_hashes(path: Path) -> dict:
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    return {"md5": md5.hexdigest(), "sha1": sha1.hexdigest(), "sha256": sha256.hexdigest()}


def run_exiftool(path: Path) -> dict:
    try:
        result = subprocess.run(
            ["exiftool", "-j", "-G", "-a", "-u", "-struct", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("exiftool is not installed on the server") from exc

    if result.returncode != 0 and not result.stdout:
        raise RuntimeError(result.stderr.strip() or "exiftool failed to read the file")

    data = json.loads(result.stdout)
    return data[0] if data else {}


def _estimate_jpeg_quality(qtable) -> int | None:
    if not qtable or len(qtable) != 64:
        return None
    ratios = [(q * 100.0) / b for q, b in zip(qtable, _BASE_LUMA_TABLE) if b]
    if not ratios:
        return None
    avg_scale = sum(ratios) / len(ratios)
    quality = (200 - avg_scale) / 2 if avg_scale <= 100 else 5000 / avg_scale
    return max(1, min(100, round(quality)))


def _get_subsampling(im: Image.Image) -> str | None:
    try:
        sampling = JpegImagePlugin.get_sampling(im)
        return {0: "4:4:4", 1: "4:2:2", 2: "4:2:0"}.get(sampling, f"unknown ({sampling})")
    except Exception:
        return None


def analyze_pixel_fingerprint(path: Path) -> dict:
    """
    Heuristic analysis that works even when EXIF/IPTC/XMP has been
    completely stripped — it looks at the pixel-stream characteristics
    the re-encoder left behind (quantization table, chroma subsampling,
    resulting dimensions) and compares them against a small table of
    known app export behaviours.
    """
    fingerprint = {
        "format": None,
        "dimensions": None,
        "subsampling": None,
        "estimated_jpeg_quality": None,
        "quantization_table_present": False,
        "guesses": [],
    }

    try:
        with Image.open(path) as im:
            fingerprint["format"] = im.format
            fingerprint["dimensions"] = {"width": im.width, "height": im.height}

            if im.format == "JPEG":
                fingerprint["subsampling"] = _get_subsampling(im)

                qtables = getattr(im, "quantization", None)
                if qtables and 0 in qtables:
                    fingerprint["quantization_table_present"] = True
                    fingerprint["estimated_jpeg_quality"] = _estimate_jpeg_quality(qtables[0])

                fingerprint["guesses"] = guess_source_app(
                    width=im.width,
                    height=im.height,
                    subsampling=fingerprint["subsampling"],
                    quality=fingerprint["estimated_jpeg_quality"],
                )
    except Exception:
        pass

    return fingerprint


def analyze_image(path: Path) -> dict:
    exif_raw = run_exiftool(path)
    hashes = compute_hashes(path)
    fingerprint = analyze_pixel_fingerprint(path)

    # Turn the flat "Group:Tag": value map from exiftool into a list
    # that's easy to render as a table, grouped by category.
    grouped: dict[str, list[dict]] = {}
    for key, value in exif_raw.items():
        if ":" in key:
            group, tag = key.split(":", 1)
        else:
            group, tag = "File", key
        grouped.setdefault(group, []).append({"tag": tag, "value": value})

    has_gps = any(g.lower() == "gps" for g in grouped)

    return {
        "file_name": exif_raw.get("File:FileName") or path.name,
        "hashes": hashes,
        "metadata_groups": grouped,
        "has_gps": has_gps,
        "fingerprint": fingerprint,
        "metadata_field_count": sum(len(v) for v in grouped.values()),
    }
