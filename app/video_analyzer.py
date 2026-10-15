import json
import subprocess
from pathlib import Path

from .analyzer import (
    _get_gps_decimal,
    _human_file_size,
    compute_hashes,
    group_metadata,
    run_exiftool,
)

# Groups to look in first when searching for a tag, in order of preference.
# Phones write video metadata under different QuickTime sub-groups.
_PREFERRED_GROUPS = ("Keys", "QuickTime", "UserData", "ItemList", "XMP", "EXIF")


def run_ffprobe(path: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe غير مثبّت على الخادم") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("استغرقت قراءة الفيديو وقتًا أطول من المسموح") from exc

    try:
        probe = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        probe = {}
    if not probe.get("streams"):
        raise RuntimeError("تعذّرت قراءة هذا الفيديو — قد يكون الملف تالفًا أو بصيغة غير مدعومة.")
    return probe


def _find_tag(exif_raw: dict, names: tuple[str, ...]):
    """Return the first non-empty value for any of `names`, preferring
    the QuickTime-style groups where phones store camera info."""
    for name in names:
        for group in _PREFERRED_GROUPS:
            value = exif_raw.get(f"{group}:{name}")
            if value not in (None, ""):
                return value
    for name in names:
        for key, value in exif_raw.items():
            if key.endswith(f":{name}") and value not in (None, ""):
                return value
    return None


def _valid_date(raw) -> bool:
    return isinstance(raw, str) and raw and not raw.startswith(("0000", "1904", "1970:01:01"))


def _format_video_date(exif_raw: dict, container_tags: dict) -> str | None:
    # CreationDate (written by iPhones) carries a timezone offset.
    for key in ("Keys:CreationDate", "QuickTime:CreationDate"):
        value = exif_raw.get(key)
        if _valid_date(value):
            date_part, _, rest = value.partition(" ")
            return f"{date_part.replace(':', '-')} {rest}".strip()

    # QuickTime atoms store UTC without an offset.
    for key in ("QuickTime:CreateDate", "QuickTime:MediaCreateDate", "QuickTime:TrackCreateDate"):
        value = exif_raw.get(key)
        if _valid_date(value):
            date_part, _, rest = value.partition(" ")
            return f"{date_part.replace(':', '-')} {rest} UTC".strip()

    created = container_tags.get("creation_time")
    if created and not created.startswith(("0000", "1970")):
        return created.replace("T", " ").split(".")[0].rstrip("Z") + " UTC"
    return None


def _parse_fraction(raw: str | None) -> float | None:
    if not raw or raw == "0/0":
        return None
    try:
        if "/" in raw:
            num, den = raw.split("/")
            return float(num) / float(den) if float(den) else None
        return float(raw)
    except ValueError:
        return None


def _format_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _format_bitrate(bits_per_second) -> str | None:
    try:
        bps = float(bits_per_second)
    except (TypeError, ValueError):
        return None
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f} Mbps"
    return f"{bps / 1000:.0f} Kbps"


def _rotation_degrees(video: dict) -> int:
    tags = video.get("tags") or {}
    if "rotate" in tags:
        try:
            return int(tags["rotate"]) % 360
        except ValueError:
            pass
    for item in video.get("side_data_list") or []:
        if "rotation" in item:
            try:
                return int(round(float(item["rotation"]))) % 360
            except (TypeError, ValueError):
                pass
    return 0


def extract_stream_info(probe: dict) -> dict:
    fmt = probe.get("format") or {}
    streams = probe.get("streams") or []

    video = next(
        (s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    info = {
        "container": fmt.get("format_long_name") or fmt.get("format_name"),
        "major_brand": (fmt.get("tags") or {}).get("major_brand", "").strip() or None,
        "duration_seconds": None,
        "duration": None,
        "overall_bitrate": _format_bitrate(fmt.get("bit_rate")),
        "video": None,
        "audio": None,
        "encoder": None,
        "handlers": [],
        "stream_count": len(streams),
    }

    try:
        duration = float(fmt.get("duration") or (video or {}).get("duration"))
        info["duration_seconds"] = duration
        info["duration"] = _format_duration(duration)
    except (TypeError, ValueError):
        pass

    if video:
        width, height = video.get("width"), video.get("height")
        rotation = _rotation_degrees(video)
        display_w, display_h = (height, width) if rotation in (90, 270) else (width, height)
        fps = _parse_fraction(video.get("avg_frame_rate")) or _parse_fraction(video.get("r_frame_rate"))
        info["video"] = {
            "codec": video.get("codec_name"),
            "profile": video.get("profile"),
            "width": display_w,
            "height": display_h,
            "fps": round(fps, 2) if fps else None,
            "pix_fmt": video.get("pix_fmt"),
            "rotation": rotation,
            "bitrate": _format_bitrate(video.get("bit_rate")),
        }
        handler = (video.get("tags") or {}).get("handler_name")
        if handler:
            info["handlers"].append(handler)

    if audio:
        info["audio"] = {
            "codec": audio.get("codec_name"),
            "sample_rate": audio.get("sample_rate"),
            "channels": audio.get("channels"),
            "bitrate": _format_bitrate(audio.get("bit_rate")),
        }
        handler = (audio.get("tags") or {}).get("handler_name")
        if handler:
            info["handlers"].append(handler)

    tags_pool = [fmt.get("tags") or {}] + [(s.get("tags") or {}) for s in streams]
    for tags in tags_pool:
        if tags.get("encoder"):
            info["encoder"] = tags["encoder"]
            break

    return info


def _confidence(score: int) -> str:
    if score >= 5:
        return "عالية (وحتى هذي غير قطعية)"
    if score >= 3:
        return "متوسطة"
    return "منخفضة"


def guess_video_origin(info: dict, container_tags: dict) -> dict:
    """
    Heuristic reading of what the file's structure says about where it came
    from. Works from container brand, handler names, encoder strings and
    codec choices — things that survive even when camera/GPS metadata has
    been stripped. Hints only, never proof.
    """
    video = info.get("video") or {}
    handlers = " ".join(info.get("handlers") or []).lower()
    encoder = (info.get("encoder") or "").lower()
    brand = (info.get("major_brand") or "").lower()
    tag_keys = " ".join(container_tags.keys()).lower()

    indicators = []
    guesses = []

    # ---- Observations (what the file structure shows) ----
    if brand == "qt":
        indicators.append("حاوية بصيغة QuickTime (‎.mov) — نمط شائع في أجهزة وبرامج أبل")
    elif brand:
        indicators.append(f"حاوية MP4 بعلامة التوافق «{brand}»")
    if encoder:
        indicators.append(f"اسم المشفّر المسجَّل في الملف: {info['encoder']}")
    if info.get("handlers"):
        indicators.append("أسماء معالجات المسارات: " + "، ".join(info["handlers"]))
    if video.get("codec") == "hevc":
        indicators.append("ترميز الفيديو HEVC (‎H.265) — افتراضي في آيفون الحديثة وبعض هواتف أندرويد")
    if video.get("width") and video.get("height") and video["height"] > video["width"]:
        indicators.append("فيديو رأسي — نمط تصوير الجوال أو تصدير فيديوهات القصص والريلز")

    # ---- Guesses (scored) ----
    apple_score, apple_reasons = 0, []
    if brand == "qt":
        apple_score += 2
        apple_reasons.append("علامة الحاوية QuickTime")
    if "core media" in handlers:
        apple_score += 2
        apple_reasons.append("اسم معالج Apple CoreMedia")
    if "com.apple" in tag_keys:
        apple_score += 2
        apple_reasons.append("وسوم بصيغة com.apple في الحاوية")
    if apple_score:
        guesses.append({"name": "تسجيل أو تصدير من جهاز/برنامج أبل", "score": apple_score, "reasons": apple_reasons})

    android_score, android_reasons = 0, []
    if "com.android" in tag_keys:
        android_score += 3
        android_reasons.append("وسم إصدار أندرويد موجود في الحاوية")
    if "videohandle" in handlers.replace("videohandler", ""):
        android_score += 2
        android_reasons.append("اسم المعالج «VideoHandle» الشائع في تسجيلات أندرويد")
    if android_score:
        guesses.append({"name": "تسجيل من كاميرا هاتف أندرويد", "score": android_score, "reasons": android_reasons})

    ffmpeg_score, ffmpeg_reasons = 0, []
    if "lavf" in encoder or "lavc" in encoder or "ffmpeg" in encoder:
        ffmpeg_score += 3
        ffmpeg_reasons.append("المشفّر المسجَّل مبني على FFmpeg")
    if "videohandler" in handlers or "soundhandler" in handlers:
        ffmpeg_score += 2
        ffmpeg_reasons.append("أسماء المعالجات «VideoHandler/SoundHandler» التي تضعها أدوات FFmpeg")
    if ffmpeg_score:
        guesses.append({
            "name": "أُعيد تشفيره بأداة مبنية على FFmpeg (شائع في المنصات وتطبيقات المراسلة والتحويل)",
            "score": ffmpeg_score,
            "reasons": ffmpeg_reasons,
        })

    for g in guesses:
        g["confidence"] = _confidence(g["score"])
    guesses.sort(key=lambda g: g["score"], reverse=True)

    return {"indicators": indicators, "guesses": guesses[:3]}


def build_video_highlights(path: Path, exif_raw: dict, info: dict, container_tags: dict) -> dict:
    make = _find_tag(exif_raw, ("Make",))
    model = _find_tag(exif_raw, ("Model",))
    device = " ".join(p for p in [make, model] if p) or None

    video = info.get("video") or {}
    dims = {"width": video["width"], "height": video["height"]} if video.get("width") else None

    try:
        file_size = _human_file_size(path.stat().st_size)
    except Exception:
        file_size = None

    return {
        "location": _get_gps_decimal(path),
        "captured_at": _format_video_date(exif_raw, container_tags),
        "device": device,
        "quality": {
            "kind": "video",
            "dimensions": dims,
            "fps": video.get("fps"),
            "duration": info.get("duration"),
            "bitrate": info.get("overall_bitrate"),
            "codec": (video.get("codec") or "").upper() or None,
            "file_size": file_size,
        },
    }


def analyze_video(path: Path, display_name: str | None = None) -> dict:
    exif_raw = run_exiftool(path)
    probe = run_ffprobe(path)
    hashes = compute_hashes(path)

    info = extract_stream_info(probe)
    container_tags = (probe.get("format") or {}).get("tags") or {}
    origin = guess_video_origin(info, container_tags)

    grouped = group_metadata(exif_raw, display_name)
    has_gps = any(g.lower() == "gps" for g in grouped) or any(
        t["tag"].lower().startswith("gps") for fields in grouped.values() for t in fields
    )
    highlights = build_video_highlights(path, exif_raw, info, container_tags)

    return {
        "media_type": "video",
        "file_name": display_name or path.name,
        "hashes": hashes,
        "metadata_groups": grouped,
        "has_gps": has_gps,
        "video_fingerprint": {**info, **origin},
        "highlights": highlights,
        "metadata_field_count": sum(len(v) for v in grouped.values()),
    }
