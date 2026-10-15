import hashlib
import json
import re
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


def _parse_coordinates_string(raw) -> tuple[float, float] | None:
    """Parse QuickTime/ISO-6709 style coordinates, either the raw form
    ("+24.7136+046.6753/") or exiftool's numeric form ("24.7136 46.6753 12.0")."""
    if not isinstance(raw, str):
        return None
    iso = re.match(r"^\s*([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", raw)
    if iso:
        return float(iso.group(1)), float(iso.group(2))
    parts = raw.replace(",", " ").split()
    try:
        return float(parts[0]), float(parts[1])
    except (IndexError, ValueError):
        return None


def _get_gps_decimal(path: Path) -> dict | None:
    """Ask exiftool specifically for numeric (decimal-degree) GPS coordinates.
    Kept as a separate targeted call so the main metadata table can stay in
    exiftool's normal human-readable format (e.g. DMS strings, f/-stops).
    Falls back to QuickTime's GPSCoordinates tag, which is where phones
    store the location of a video."""
    try:
        result = subprocess.run(
            ["exiftool", "-j", "-n", "-GPSLatitude", "-GPSLongitude", "-GPSCoordinates", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(result.stdout)[0]
    except Exception:
        return None

    lat, lon = data.get("GPSLatitude"), data.get("GPSLongitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        parsed = _parse_coordinates_string(data.get("GPSCoordinates"))
        if not parsed:
            return None
        lat, lon = parsed
    return {
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "maps_url": f"https://www.google.com/maps?q={lat},{lon}",
    }


def _format_exif_date(raw: str | None) -> str | None:
    if not raw:
        return None
    date_part, _, rest = raw.partition(" ")
    return f"{date_part.replace(':', '-')} {rest}".strip()


def _human_file_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("بايت", "كيلوبايت", "ميجابايت", "جيجابايت"):
        if size < 1024 or unit == "جيجابايت":
            return f"{size:.1f} {unit}" if unit != "بايت" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} جيجابايت"


def build_highlights(path: Path, exif_raw: dict, fingerprint: dict) -> dict:
    device_make = exif_raw.get("EXIF:Make")
    device_model = exif_raw.get("EXIF:Model")
    device = " ".join(p for p in [device_make, device_model] if p) or None

    captured_at = _format_exif_date(
        exif_raw.get("EXIF:DateTimeOriginal")
        or exif_raw.get("EXIF:CreateDate")
        or exif_raw.get("File:FileModifyDate")
    )

    dims = fingerprint.get("dimensions")
    megapixels = round((dims["width"] * dims["height"]) / 1_000_000, 1) if dims else None

    try:
        file_size = _human_file_size(path.stat().st_size)
    except Exception:
        file_size = None

    return {
        "location": _get_gps_decimal(path),
        "captured_at": captured_at,
        "device": device,
        "quality": {
            "dimensions": dims,
            "megapixels": megapixels,
            "estimated_jpeg_quality": fingerprint.get("estimated_jpeg_quality"),
            "file_size": file_size,
        },
    }


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


_HIDDEN_TAGS = {"SourceFile", "File:Directory"}


def group_metadata(exif_raw: dict, display_name: str | None = None) -> dict[str, list[dict]]:
    """Turn exiftool's flat "Group:Tag": value map into a dict of
    group -> [{tag, value}] for easy rendering. Server-side temp paths are
    hidden and the temp file name is replaced by the uploaded file's name."""
    grouped: dict[str, list[dict]] = {}
    for key, value in exif_raw.items():
        if key in _HIDDEN_TAGS:
            continue
        if key == "File:FileName" and display_name:
            value = display_name
        if ":" in key:
            group, tag = key.split(":", 1)
        else:
            group, tag = "File", key
        grouped.setdefault(group, []).append({"tag": tag, "value": value})
    return grouped


def analyze_image(path: Path, display_name: str | None = None) -> dict:
    exif_raw = run_exiftool(path)
    hashes = compute_hashes(path)
    fingerprint = analyze_pixel_fingerprint(path)

    grouped = group_metadata(exif_raw, display_name)
    has_gps = any(g.lower() == "gps" for g in grouped)
    highlights = build_highlights(path, exif_raw, fingerprint)

    return {
        "media_type": "image",
        "file_name": display_name or exif_raw.get("File:FileName") or path.name,
        "hashes": hashes,
        "metadata_groups": grouped,
        "has_gps": has_gps,
        "fingerprint": fingerprint,
        "highlights": highlights,
        "metadata_field_count": sum(len(v) for v in grouped.values()),
    }
