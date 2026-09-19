"""
Approximate, best-effort signatures for guessing which app processed an
image after its metadata has been stripped.

These values come from commonly-observed re-encoding behaviour (typical
resize caps, JPEG quality bands, and chroma subsampling) of a handful of
popular apps. They are NOT forensic proof — just a heuristic hint, shown
to the user with a confidence label. Real forensic tools build these
tables from large labelled datasets; this is a demonstration set that
you can expand over time as you collect more samples.
"""

# Each entry: max dimension the app is known to cap exports at, the
# approximate JPEG quality band it re-encodes to, and the chroma
# subsampling mode it tends to use.
KNOWN_APP_PROFILES = [
    {
        "name": "WhatsApp",
        "max_dimension": (1600, 1600),
        "quality_range": (65, 80),
        "subsampling": "4:2:0",
    },
    {
        "name": "Facebook Messenger",
        "max_dimension": (1280, 1280),
        "quality_range": (60, 75),
        "subsampling": "4:2:0",
    },
    {
        "name": "Instagram",
        "max_dimension": (1080, 1350),
        "quality_range": (75, 90),
        "subsampling": "4:2:0",
    },
    {
        "name": "Telegram",
        "max_dimension": (1280, 1280),
        "quality_range": (85, 95),
        "subsampling": "4:2:0",
    },
    {
        "name": "X (Twitter)",
        "max_dimension": (2048, 2048),
        "quality_range": (75, 90),
        "subsampling": "4:2:0",
    },
]


def guess_source_app(width: int, height: int, subsampling: str | None, quality: int | None):
    """Return a ranked list of {name, confidence, reason} guesses."""
    guesses = []
    longest_side = max(width, height)

    for profile in KNOWN_APP_PROFILES:
        score = 0
        reasons = []

        cap = max(profile["max_dimension"])
        if longest_side <= cap and longest_side >= cap * 0.85:
            score += 2
            reasons.append(f"longest side ({longest_side}px) matches {profile['name']}'s ~{cap}px export cap")

        if subsampling and subsampling == profile["subsampling"]:
            score += 1
            reasons.append(f"chroma subsampling {subsampling} is typical of {profile['name']}")

        if quality is not None:
            lo, hi = profile["quality_range"]
            if lo <= quality <= hi:
                score += 2
                reasons.append(f"estimated JPEG quality ({quality}) falls in {profile['name']}'s usual {lo}-{hi} band")

        if score > 0:
            confidence = "low"
            if score >= 4:
                confidence = "medium"
            if score >= 5:
                confidence = "high (still not definitive)"
            guesses.append({
                "name": profile["name"],
                "score": score,
                "confidence": confidence,
                "reasons": reasons,
            })

    guesses.sort(key=lambda g: g["score"], reverse=True)
    return guesses[:3]
