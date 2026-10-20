"""maimai DX single-chart rating and B50 selection helpers."""
from __future__ import annotations
import math
import re

# Achievement thresholds and rating factors used by the standard maimai DX rating formula.
RANK_FACTORS = [
    (100.5, 22.4), (100.0, 21.6), (99.5, 21.1), (99.0, 20.8),
    (98.0, 20.3), (97.0, 20.0), (94.0, 16.8), (90.0, 15.2),
    (80.0, 13.6), (75.0, 12.8), (70.0, 11.2), (60.0, 9.6),
    (50.0, 8.0), (40.0, 6.4), (30.0, 4.8), (20.0, 3.2), (10.0, 1.6),
    (0.0, 0.0),
]

def chart_rating(constant: float, achievement: float) -> int:
    """Calculate chart rating; achievement is a percentage, e.g. 100.1234."""
    if constant < 0 or not math.isfinite(constant):
        raise ValueError("谱面定数必须是有效的非负数")
    if not math.isfinite(achievement):
        return 0
    ach = min(max(achievement, 0.0), 100.5)
    factor = next(f for threshold, f in RANK_FACTORS if ach >= threshold)
    return math.floor(constant * (ach / 100.0) * factor)

# Community implementation palette aligned with maimai DX's star progression.
# Source reference: https://github.com/Matsuk1/JiETNG/blob/main/modules/images/records.py
DX_STAR_COLORS = {
    1: "#409d0e",  # green
    2: "#79c11a",  # lime green
    3: "#dc4916",  # red-orange
    4: "#ef6f1b",  # orange
    5: "#ed9a18",  # gold
}

# Achievement grade labels shown on the individual score cards.
# The percentage is AstroDX's recorded achievement, not the DX score star tier.
ACHIEVEMENT_RANKS = [
    (100.5, "SSS+"), (100.0, "SSS"), (99.5, "SS+"), (99.0, "SS"),
    (98.0, "S+"), (97.0, "S"), (94.0, "AAA"), (90.0, "AA"),
    (80.0, "A"), (75.0, "BBB"), (70.0, "BB"), (60.0, "B"),
    (50.0, "C"), (0.0, "D"),
]

ACHIEVEMENT_RANK_COLORS = {
    "SSS+": "rainbow", "SSS": "rainbow",
    "SS+": "gold", "SS": "gold", "S+": "gold", "S": "gold",
    "AAA": "red", "AA": "red", "A": "red",
    "BBB": "blue", "BB": "blue", "B": "blue",
    "C": "green", "D": "gray",
}

def achievement_rank(achievement: float) -> str:
    """Return the maimai DX achievement rank label for a percentage."""
    try:
        value = float(achievement)
    except (TypeError, ValueError, OverflowError):
        value = 0.0
    if not math.isfinite(value):
        value = 0.0
    return next(label for threshold, label in ACHIEVEMENT_RANKS if value >= threshold)

def achievement_rank_color(achievement: float) -> str:
    """Return the requested visual tier for an achievement rank."""
    return ACHIEVEMENT_RANK_COLORS[achievement_rank(achievement)]


def dx_star_count(dx_score: int | float, total_notes: int | float | None) -> int | None:
    """Return official maimai DX stars (0-5), or None when note count is unknown.

    The theoretical maximum DX Score is 3 points per note. Star cutoffs are
    85%, 90%, 93%, 95% and 97% of that maximum.
    """
    try:
        notes = int(total_notes or 0)
        score = int(dx_score or 0)
    except (TypeError, ValueError, OverflowError):
        return None
    if notes <= 0 or score < 0:
        return None
    max_score = notes * 3
    ratio = score / max_score
    return sum(ratio >= threshold for threshold in (0.85, 0.90, 0.93, 0.95, 0.97))


def rating_tier(total_rating: int | float) -> tuple[str, str]:
    """Return (CSS tier key, Chinese tier label) for the maimai DX rating frame."""
    value = int(total_rating or 0)
    tiers = [
        (15000, "rainbow", "彩框"),
        (14500, "platinum", "白金"),
        (14000, "gold", "金色"),
        (13000, "silver", "银色"),
        (12000, "bronze", "铜色"),
        (10000, "purple", "紫色"),
        (7000, "red", "红色"),
        (4000, "yellow", "黄色"),
        (2000, "green", "绿色"),
        (1000, "blue", "蓝色"),
        (0, "white", "白色"),
    ]
    return next((key, label) for threshold, key, label in tiers if value >= threshold)


def is_utage_record(record: dict) -> bool:
    """True for UTAGE/宴会場 charts, which must never contribute to Rating."""
    difficulty = str(record.get("difficulty") or record.get("chart_type") or "").strip().upper().replace(" ", "")
    if difficulty in {"UTAGE", "宴会場", "宴会"}:
        return True
    try:
        if int(record.get("difficulty_id") or 0) == 7:
            return True
    except (TypeError, ValueError):
        pass
    for key in ("song_type", "type", "chart_type"):
        value = str(record.get(key) or "").strip().upper()
        if value in {"UTAGE", "宴会場", "宴会"} or "UTAGE" in value:
            return True
    title = str(record.get("title") or "").strip()
    return bool(re.match(r"^\[(?:宴会場|宴会|宴|UTAGE)[^\]]*\]", title, re.IGNORECASE))


def rating_tier_for_slots(total_rating: int | float, slots: int) -> tuple[str, str]:
    """Scale the 50-chart Rating color thresholds to a B35/B15 subtotal."""
    slots = max(0, int(slots))
    value = int(total_rating or 0)
    # Keep the canonical threshold/tier ordering used for total Rating.
    thresholds = [
        (15000, "rainbow", "彩框"), (14500, "platinum", "白金"),
        (14000, "gold", "金色"), (13000, "silver", "银色"),
        (12000, "bronze", "铜色"), (10000, "purple", "紫色"),
        (7000, "red", "红色"), (4000, "yellow", "黄色"),
        (2000, "green", "绿色"), (1000, "blue", "蓝色"),
        (0, "white", "白色"),
    ]
    for threshold, key, label in thresholds:
        scaled_threshold = math.floor(threshold * slots / 50)
        if value >= scaled_threshold:
            return key, label
    return "white", "白色"


def _sort_key(r: dict):
    return (r.get("rating", 0), r.get("achievement", 0), r.get("dx_score", 0))

def select_b50(records: list[dict], mode: str = "split", target_version: str | None = None) -> tuple[list[dict], list[dict]]:
    """Return (older_pool, latest_pool). In direct mode, all top 50 are in the first list."""
    # UTAGE is a separate chart mode and must not count toward any DX Rating list.
    eligible = [r for r in records if not is_utage_record(r)]
    if mode == "direct":
        top = sorted(eligible, key=_sort_key, reverse=True)[:50]
        return top, []
    if target_version is None:
        # Backwards-compatible mode for older callers that already classified is_new.
        older = [r for r in eligible if not r.get("is_new", False)]
        latest = [r for r in eligible if r.get("is_new", False)]
    else:
        target = str(target_version).strip().casefold()
        latest = [r for r in eligible if str(r.get("version", "")).strip().casefold() == target]
        older = [r for r in eligible if str(r.get("version", "")).strip().casefold() != target]
    return sorted(older, key=_sort_key, reverse=True)[:35], sorted(latest, key=_sort_key, reverse=True)[:15]
