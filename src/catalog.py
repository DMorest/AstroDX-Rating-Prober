from __future__ import annotations
import csv, json, unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from .rating import chart_rating

DIFF_ALIASES = {"REMASTER": "RE:MASTER", "RE:MASTER": "RE:MASTER", "RE:MASTER ": "RE:MASTER", "UTAGE": "UTAGE"}

def normalize_title(value: Any) -> str:
    """Normalize cosmetic title differences across community catalogues.

    Music metadata sources disagree on typographic apostrophes (Don't vs Don’t)
    and dash glyphs. These should not prevent an otherwise exact song match.
    """
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    # Treat straight/curly/backtick apostrophes as cosmetic for title matching.
    apostrophes = "'’‘‛ʼʻ＇`´"
    dashes = "‐‑‒–—―﹘﹣－"
    value = "".join("" if ch in apostrophes else "-" if ch in dashes else ch for ch in value)
    return "".join(ch for ch in value if not ch.isspace() and ch not in "　\u200b")


def _similar_title_charts(title_key: str, difficulty: str, catalog: list[dict], limit: int = 5) -> list[dict]:
    """Return close title candidates for manual recovery only; never auto-match these."""
    if not title_key:
        return []
    scored = []
    for chart in catalog:
        if normalize_difficulty(chart.get("difficulty")) != difficulty:
            continue
        chart_key, _, _ = _title_markers(chart.get("title", ""))
        if not chart_key:
            continue
        similarity = SequenceMatcher(None, title_key, chart_key).ratio()
        # A conservative threshold: typos/minor source spelling differences only.
        if similarity >= 0.78 and min(len(title_key), len(chart_key)) / max(len(title_key), len(chart_key)) >= 0.72:
            scored.append((similarity, chart))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    # Avoid showing a wall of near-identical results from different regions/providers.
    result, seen = [], set()
    for _, chart in scored:
        signature = (normalize_title(chart.get("title")), normalize_difficulty(chart.get("difficulty")),
                     str(chart.get("song_type") or chart.get("type") or ""),
                     str(chart.get("version") or ""), str(chart.get("constant") or chart.get("ds") or ""))
        if signature in seen:
            continue
        seen.add(signature)
        result.append(chart)
        if len(result) >= limit:
            break
    return result

def normalize_difficulty(value: Any) -> str:
    key = str(value or "").strip().upper().replace(" ", "")
    return DIFF_ALIASES.get(key, key)

def _extract_total_notes(row: dict) -> int:
    """Normalize note-count fields across catalogue providers."""
    for field in ("total_notes", "totalNotes", "note_count", "noteCount", "totalNotesCount"):
        value = row.get(field)
        try:
            count = int(value or 0)
            if count > 0:
                return count
        except (TypeError, ValueError):
            pass
    notes = row.get("notes")
    if isinstance(notes, dict):
        for field in ("total", "totalNotes", "count"):
            try:
                count = int(notes.get(field) or 0)
                if count > 0:
                    return count
            except (TypeError, ValueError):
                pass
    if isinstance(notes, (list, tuple)):
        try:
            count = sum(int(v or 0) for v in notes)
            if count > 0:
                return count
        except (TypeError, ValueError):
            pass
    return 0


def _normalize_level_text(value: Any) -> str:
    """Normalize displayed maimai level text (e.g. 13+, 14, 14+), not chart constant."""
    return "".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _normalize_row(row: dict, source: str = "文件") -> dict | None:
    title = row.get("title") or row.get("song_name") or row.get("songName")
    difficulty = row.get("difficulty") or row.get("chart_type")
    constant = row.get("constant") or row.get("ds") or row.get("level_value")
    if not title or not difficulty or constant in (None, ""):
        return None
    try:
        ds = float(str(constant).replace("+", ""))
    except (ValueError, TypeError):
        return None
    return {
        **row,
        "title": str(title), "title_key": normalize_title(title),
        "difficulty": normalize_difficulty(difficulty), "constant": ds,
        "song_id": str(row.get("song_id") or row.get("id") or ""),
        "chart_id": str(row.get("chart_id") or ""),
        "chart_hash": str(row.get("chart_hash") or row.get("hash") or ""),
        "song_type": str(row.get("song_type") or row.get("type") or ""),
        "level_text": str(row.get("level_text") or row.get("level") or "").strip(),
        "total_notes": _extract_total_notes(row),
        "version": str(row.get("version") or "未知版本").strip(),
        "source": str(row.get("source") or source),
    }

def load_catalog_bytes(filename: str, raw: bytes) -> list[dict]:
    suffix = Path(filename).suffix.lower()
    text = raw.decode("utf-8-sig")
    if suffix == ".json":
        obj = json.loads(text)
        if isinstance(obj, dict):
            obj = obj.get("songs", obj.get("charts", []))
        if not isinstance(obj, list):
            raise ValueError("JSON 曲库应为数组，或包含 songs/charts 数组的对象")
        rows = obj
    else:
        rows = list(csv.DictReader(text.splitlines()))
    return [x for row in rows if isinstance(row, dict) if (x := _normalize_row(row)) is not None]

def normalize_fetched_catalog(rows: list[dict]) -> list[dict]:
    return [x for row in rows if (x := _normalize_row(row, "在线曲库")) is not None]

import re

UTAGE_PREFIX = re.compile(r"^\[[一-龯々〆ヵヶぁ-ゖァ-ヺー]+\]")
TYPE_SUFFIX = re.compile(r"\s*\[(SD|DX)\]\s*$", re.IGNORECASE)


def _title_markers(title: str) -> tuple[str, str | None, bool]:
    """Return normalized base title, explicit SD/DX marker, and UTAGE marker."""
    raw = unicodedata.normalize("NFKC", str(title or "")).strip()
    is_utage = bool(UTAGE_PREFIX.match(raw))
    raw = UTAGE_PREFIX.sub("", raw, count=1).strip()
    marker = None
    match = TYPE_SUFFIX.search(raw)
    if match:
        marker = match.group(1).upper()
        raw = raw[:match.start()].strip()
    return normalize_title(raw), marker, is_utage


def _chart_kind(chart: dict) -> str | None:
    value = str(chart.get("song_type") or chart.get("type") or "").strip().upper()
    if value in ("SD", "STANDARD", "STD"):
        return "SD"
    if value == "DX":
        return "DX"
    return None


def _dx_theoretical_max(chart: dict) -> int | None:
    for field in ("total_notes", "notes", "note_count", "totalNotesCount"):
        try:
            notes = int(chart.get(field) or 0)
            if notes > 0:
                return notes * 3
        except (TypeError, ValueError):
            pass
    return None


def match_records(scores: list[dict], catalog: list[dict]) -> tuple[list[dict], list[dict]]:
    """Match cache scores to catalog charts, using title markers, difficulty and DX score.

    Ambiguous entries retain candidate charts in ``candidates`` for UI resolution.
    """
    index: dict[tuple[str, str], list[dict]] = {}
    for chart in catalog:
        key, _, _ = _title_markers(chart.get("title", ""))
        index.setdefault((key, normalize_difficulty(chart.get("difficulty"))), []).append(chart)

    # AstroDX cache records a per-chart hash. Some catalogues expose the same hash;
    # when they do, it is the most reliable way to distinguish SD/DX variants.
    hash_index: dict[str, list[dict]] = {}
    for chart in catalog:
        chart_hash = str(chart.get("chart_hash") or chart.get("hash") or "").strip()
        if chart_hash:
            hash_index.setdefault(chart_hash, []).append(chart)

    matched, unmatched = [], []
    for score in scores:
        if float(score.get("achievement", 0) or 0) <= 0:
            continue
        key, explicit_kind, is_utage = _title_markers(score.get("title", ""))
        difficulty = normalize_difficulty(score.get("difficulty"))
        score_hash = str(score.get("chart_hash") or "").strip()
        hash_choices = hash_index.get(score_hash, []) if score_hash else []
        if hash_choices:
            exact = [c for c in hash_choices if normalize_difficulty(c.get("difficulty")) == difficulty]
            if len(exact) == 1:
                chart = exact[0]
                matched.append({**score, **chart, "rating": chart_rating(chart["constant"], score["achievement"]), "match_status": "谱面 hash 精确匹配"})
                continue
            if exact:
                choices = exact
            else:
                choices = list(index.get((key, difficulty), []))
        else:
            choices = list(index.get((key, difficulty), []))
        if is_utage or difficulty == "UTAGE":
            choices = [c for c in choices if normalize_difficulty(c.get("difficulty")) == "UTAGE"]
        elif any(normalize_difficulty(c.get("difficulty")) == "UTAGE" for c in choices):
            choices = [c for c in choices if normalize_difficulty(c.get("difficulty")) != "UTAGE"]
        if explicit_kind:
            typed = [c for c in choices if _chart_kind(c) == explicit_kind]
            if typed:
                choices = typed

        # Cache v4 does store the displayed level label (for example, "14" or "13+").
        # Compare that label against the catalogue's chart level before considering SD/DX
        # variants. This is deliberately NOT inferred from the decimal chart constant.
        score_level = _normalize_level_text(score.get("level_text") or score.get("level"))
        rejected_for_level: list[dict] = []
        if score_level and choices:
            labelled = [(c, _normalize_level_text(c.get("level_text") or c.get("level"))) for c in choices]
            exact_level = [c for c, level in labelled if level == score_level]
            if exact_level:
                choices = exact_level
            else:
                unknown_level = [c for c, level in labelled if not level]
                if unknown_level:
                    # If one provider omits labels, keep only those unknown candidates;
                    # do not let known, contradictory levels through.
                    rejected_for_level = [c for c, level in labelled if level]
                    choices = unknown_level
                elif labelled:
                    rejected_for_level = [c for c, _ in labelled]
                    choices = []

        # The AstroDX total note count can further distinguish variants when a provider
        # exposes it. Only use exact counts when at least one exact candidate exists.
        try:
            score_notes = int(score.get("notes") or 0)
        except (TypeError, ValueError):
            score_notes = 0
        if score_notes > 0 and choices:
            exact_notes = []
            for c in choices:
                try:
                    chart_notes = int(c.get("total_notes") or 0)
                except (TypeError, ValueError):
                    chart_notes = 0
                if chart_notes == score_notes:
                    exact_notes.append(c)
            if exact_notes:
                choices = exact_notes

        # DX Score is not a reliable SD/DX discriminator by itself. Use exact chart hash,
        # cache's displayed level, and exact note count where available; unresolved matches
        # stay in the ambiguity pool instead of silently counting the wrong chart.
        if len(choices) != 1:
            item = dict(score)
            if not choices and rejected_for_level:
                # Keep contradictory-level charts visible for explicit manual override.
                # They must never be accepted automatically, but hiding them makes
                # the manual selector impossible to use when the catalogue is stale.
                item["match_status"] = "曲名/难度找到候选，但曲库等级不符；请手动核对"
                item["candidates"] = rejected_for_level
            elif not choices:
                # Some providers use different punctuation/spelling conventions. Offer
                # conservative same-difficulty title neighbors for manual selection only.
                near_matches = _similar_title_charts(key, difficulty, catalog)
                if near_matches:
                    item["match_status"] = "曲名未精确匹配；以下为相似曲名候选（需手动确认）"
                    item["candidates"] = near_matches
                else:
                    item["match_status"] = "未匹配（曲库没有找到同难度候选）"
                    item["candidates"] = []
            else:
                item["match_status"] = "曲名/难度对应多个谱面候选"
                item["candidates"] = choices
            unmatched.append(item)
            continue
        chart = choices[0]
        item = {**score, **chart, "rating": chart_rating(chart["constant"], score["achievement"]), "match_status": "已匹配"}
        matched.append(item)
    return matched, unmatched


def apply_manual_matches(matched: list[dict], unmatched: list[dict], selections: dict[str, int]) -> tuple[list[dict], list[dict]]:
    """Apply UI-selected candidate indices; selection keys are stable score signatures."""
    remaining = []
    for item in unmatched:
        sig = score_signature(item)
        idx = selections.get(sig)
        candidates = item.get("candidates") or []
        if idx is None or idx < 0 or idx >= len(candidates):
            remaining.append(item)
            continue
        chart = candidates[idx]
        merged = {**item, **chart, "rating": chart_rating(chart["constant"], item["achievement"]), "match_status": "手动匹配"}
        merged.pop("candidates", None)
        matched.append(merged)
    return matched, remaining


def score_signature(item: dict) -> str:
    return "|".join(str(item.get(k, "")) for k in ("cache_key", "title", "difficulty", "achievement", "dx_score", "chart_hash"))
