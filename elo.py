from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


DEFAULT_RATING = 1000.0
K_BASE = 32.0

LEVEL_WEIGHTS: dict[str, float] = {
    "MCR": 2.0,
    "A": 1.5,
    "B": 1.2,
    "C": 1.0,
    "D": 0.8,
}


def expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def score_from_record(rec: dict[str, Any]) -> float:
    """
    Produces S in [0,1] for a player's tournament performance.
    - If W/L available: S = win_rate.
    - Else: S derived from placement percentile within field.
    """
    wins = int(rec.get("wins") or 0)
    losses = int(rec.get("losses") or 0)
    if wins + losses > 0:
        return clamp01(wins / float(wins + losses))

    placement = int(rec.get("placement") or 999)
    field = int(rec.get("field_size") or 0)
    if field <= 1 or placement <= 0 or placement > field:
        return 0.5
    # 1st => 1.0, last => 0.0
    return clamp01((field - placement) / float(field - 1))


def sort_key(rec: dict[str, Any]):
    # ISO date preferred; empty dates sort last deterministically
    d = rec.get("tournament_date") or "9999-12-31"
    return (d, rec.get("tournament_code") or "", rec.get("player_id") or "")


def compute_elo(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Deterministic recompute from scratch. Returns:
    {
      "generated_at": "...",
      "categories": { "minitenis": [..players..], ... },
      "players": { player_id: {..} }
    }
    """
    # group by category then by tournament_code+date (event id)
    categories: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        cat = rec.get("category") or "unknown"
        categories.setdefault(cat, []).append(rec)

    player_state: dict[str, dict[str, Any]] = {}

    # per category independent ELO pools
    category_player_rating: dict[str, dict[str, float]] = {cat: {} for cat in categories.keys()}
    category_player_matches: dict[str, dict[str, int]] = {cat: {} for cat in categories.keys()}

    for cat, recs in categories.items():
        recs_sorted = sorted(recs, key=sort_key)

        # process by tournament (code+date) so "field avg" is coherent
        events: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in recs_sorted:
            key = (r.get("tournament_code") or "", r.get("tournament_date") or "")
            events.setdefault(key, []).append(r)

        for (tcode, tdate), event_recs in sorted(events.items(), key=lambda x: (x[0][1] or "9999-12-31", x[0][0] or "")):
            participants = [r.get("player_id") for r in event_recs if r.get("player_id")]
            if not participants:
                continue

            ratings = category_player_rating[cat]
            for pid in participants:
                ratings.setdefault(pid, DEFAULT_RATING)

            # field average per player excludes self to reduce feedback loops
            for r in event_recs:
                pid = r.get("player_id")
                if not pid:
                    continue

                r_a = ratings.get(pid, DEFAULT_RATING)
                others = [ratings.get(op, DEFAULT_RATING) for op in participants if op != pid]
                r_b = sum(others) / float(len(others)) if others else r_a

                e = expected_score(r_a, r_b)
                s = score_from_record(r)

                level = (r.get("tournament_level") or "C").upper()
                w = LEVEL_WEIGHTS.get(level, LEVEL_WEIGHTS["C"])
                k = K_BASE * w

                ratings[pid] = r_a + k * (s - e)
                category_player_matches[cat][pid] = category_player_matches[cat].get(pid, 0) + 1

    # build output structures
    out_categories: dict[str, list[dict[str, Any]]] = {}
    for cat, ratings in category_player_rating.items():
        players: list[dict[str, Any]] = []
        for pid, elo in ratings.items():
            # find a representative record for name/club/birth_year
            sample = next((r for r in records if r.get("player_id") == pid), None) or {}
            players.append(
                {
                    "player_id": pid,
                    "name": sample.get("name") or "",
                    "birth_year": sample.get("birth_year"),
                    "club": sample.get("club") or "",
                    "category": cat,
                    "elo": round(float(elo), 2),
                    "events_count": category_player_matches[cat].get(pid, 0),
                }
            )
            player_state[pid] = players[-1]

        players.sort(key=lambda p: p["elo"], reverse=True)
        for i, p in enumerate(players, 1):
            p["rank"] = i
        out_categories[cat] = players

    return {
        "categories": out_categories,
        "players": player_state,
    }

