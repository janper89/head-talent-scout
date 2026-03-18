from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from utils import parse_birth_year


LEVELS = ("MCR", "A", "B", "C", "D")


def infer_tournament_level(tournament_info: dict[str, Any], result_files: list[dict[str, Any]] | None = None) -> str:
    """
    Best-effort heuristic. If you later add a reliable source in the scraper,
    replace this with that field.
    """
    text = " ".join(
        [
            str(tournament_info.get("poradatel", "")),
            str(tournament_info.get("kod", "")),
            str(tournament_info.get("datum", "")),
        ]
    ).lower()
    if result_files:
        for f in result_files:
            text += " " + str(f.get("label", "")).lower()
            text += " " + str(f.get("filename", "")).lower()

    if "mčr" in text or "mcr" in text or "mistrovstv" in text:
        return "MCR"

    # Heuristics for A/B/C/D are not reliably present in current scrape.
    # Default to C until scraper is extended to capture the official category.
    return "C"


def _season_year_for_month(season: str, month: int) -> int | None:
    """
    season examples: Z2526 (winter 2025/26), L2025, etc.
    For Z2526: months 7-12 => 2025, months 1-6 => 2026.
    """
    if not season:
        return None
    s = season.strip().upper()
    if s.startswith("Z") and len(s) >= 5:
        # Z2526 -> 25/26
        try:
            y1 = int("20" + s[1:3])
            y2 = int("20" + s[3:5])
        except Exception:
            return None
        return y1 if month >= 7 else y2
    if s.startswith("L") and len(s) >= 5:
        # L2025 -> 2025
        try:
            return int(s[1:])
        except Exception:
            return None
    return None


def parse_cz_date(value: str, season: str | None = None) -> str:
    """
    Parses CZ date like '17.03.2026' or '17.3.2026' into ISO 'YYYY-MM-DD'.
    Also supports CTS ranges without year, e.g. '29.-29.11.' or '29.-30.11.' by inferring year from season.
    Returns '' if parsing fails.
    """
    if not value:
        return ""
    v = value.strip()

    # If it's a range like '29.-29.11.' take the end date part
    # Patterns observed: '29.-29.11.' or '29.-30.11.' or '29.11.' etc.
    m_range = re.search(r"(\d{1,2})\.\s*-\s*(\d{1,2})\.(\d{1,2})\.", v)
    if m_range:
        d2 = int(m_range.group(2))
        mo = int(m_range.group(3))
        y = _season_year_for_month(season or "", mo)
        if y:
            try:
                return datetime(year=y, month=mo, day=d2).date().isoformat()
            except Exception:
                return ""

    m_short = re.search(r"(\d{1,2})\.(\d{1,2})\.", v)
    if m_short and season:
        d = int(m_short.group(1))
        mo = int(m_short.group(2))
        y = _season_year_for_month(season, mo)
        if y:
            try:
                return datetime(year=y, month=mo, day=d).date().isoformat()
            except Exception:
                return ""

    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d.%m.%Y", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(v, fmt)
            return dt.date().isoformat()
        except Exception:
            pass
    # Try a more tolerant split
    try:
        parts = [p for p in v.replace(" ", "").split(".") if p]
        if len(parts) >= 3:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            return datetime(year=y, month=m, day=d).date().isoformat()
    except Exception:
        return ""
    return ""


def unify_analysis_results(analysis_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Converts analyzer's raw per-tournament results into a flat list of per-player-per-tournament records.
    This is the canonical input for ELO + tip generation.
    """
    unified: list[dict[str, Any]] = []

    for r in analysis_results:
        if not r.get("success"):
            continue

        data = r.get("data") or {}
        tinfo = r.get("tournament_info") or {}

        tournament_code = data.get("turnaj_kod") or tinfo.get("kod") or ""
        tournament_date = parse_cz_date(tinfo.get("datum") or "", tinfo.get("sezona") or "")
        category = tinfo.get("kategorie") or ""
        organizer = tinfo.get("poradatel") or ""
        level = tinfo.get("turnaj_level") or infer_tournament_level(tinfo, r.get("result_files"))

        final_order = data.get("konecne_poradi") or []
        field_size = len([x for x in final_order if (x.get("jmeno") or "").strip() and x.get("jmeno") != "NEČITELNÉ"])

        for item in final_order:
            name = (item.get("jmeno") or "").strip()
            if not name or name == "NEČITELNÉ":
                continue

            birth_year = item.get("rok_narozeni")
            birth_year = birth_year if isinstance(birth_year, int) else parse_birth_year(birth_year)
            player_id = item.get("player_id") or ""
            if not player_id or not birth_year:
                # MVP: skip ambiguous identities
                continue

            unified.append(
                {
                    "player_id": player_id,
                    "name": name,
                    "birth_year": birth_year,
                    "club": item.get("klub") or "",
                    "category": category,
                    "tournament_code": tournament_code,
                    "tournament_name": data.get("turnaj") or "",
                    "tournament_date": tournament_date,
                    "tournament_organizer": organizer,
                    "tournament_level": level,
                    "placement": int(item.get("poradi") or 999),
                    "wins": int(item.get("vyhra_count") or 0),
                    "losses": int(item.get("prohra_count") or 0),
                    "field_size": field_size,
                }
            )

    return unified

