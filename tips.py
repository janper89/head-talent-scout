from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from utils import normalize_text


WINDOW_DAYS = 60


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def iso_today() -> str:
    return datetime.now().isoformat()


def parse_iso_date(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None


def club_contact_lookup(clubs_directory: dict[str, Any], club_name: str) -> dict[str, Any] | None:
    if not clubs_directory:
        return None
    by = clubs_directory.get("by_name_norm") or {}
    if not club_name:
        return None
    norm = normalize_text(club_name)
    if norm in by:
        return by[norm]

    # best-effort fuzzy: pick the closest by overlap
    best = None
    best_score = 0
    for k, v in by.items():
        if not k:
            continue
        if k in norm or norm in k:
            score = min(len(k), len(norm))
            if score > best_score:
                best_score = score
                best = v
    return best


def compute_tiers(records_window: list[dict[str, Any]]) -> dict[str, int]:
    """
    Returns player_id -> tier (1/2/3) for the 60-day window.
    Tier 1: 2x placement 1-2
    Tier 2: 2x placement 1-4 OR beat Tier 1 in same tournament (placement better)
    Tier 3: (not from window) evaluated separately per season
    """
    by_player: dict[str, list[dict[str, Any]]] = {}
    for r in records_window:
        by_player.setdefault(r["player_id"], []).append(r)

    tier: dict[str, int] = {}

    # Tier 1 and Tier 2 based on placements
    tier1_players = set()
    for pid, recs in by_player.items():
        placements = [int(r.get("placement") or 999) for r in recs]
        top2 = sum(1 for p in placements if p <= 2)
        if top2 >= 2:
            tier[pid] = 1
            tier1_players.add(pid)

    for pid, recs in by_player.items():
        if pid in tier1_players:
            continue
        placements = [int(r.get("placement") or 999) for r in recs]
        top4 = sum(1 for p in placements if p <= 4)
        if top4 >= 2:
            tier[pid] = 2

    # Beat Tier 1 heuristic (same event, better placement)
    # Build per-event ranking map
    by_event: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in records_window:
        key = (r.get("category") or "", r.get("tournament_code") or "", r.get("tournament_date") or "")
        by_event.setdefault(key, []).append(r)

    for event_key, recs in by_event.items():
        # identify tier1 participants in this event
        tier1_in_event = [r for r in recs if r["player_id"] in tier1_players]
        if not tier1_in_event:
            continue
        for r in recs:
            if r["player_id"] in tier1_players:
                continue
            # if placed better than any Tier1 player in event => Tier2
            p = int(r.get("placement") or 999)
            if any(p < int(t.get("placement") or 999) for t in tier1_in_event):
                if tier.get(r["player_id"], 99) > 2:
                    tier[r["player_id"]] = 2
                elif r["player_id"] not in tier:
                    tier[r["player_id"]] = 2

    return tier


def compute_tier3(records_season: list[dict[str, Any]]) -> set[str]:
    """
    Tier 3: 5+ tournaments in season and consistent top half.
    """
    by_player: dict[str, list[dict[str, Any]]] = {}
    for r in records_season:
        by_player.setdefault(r["player_id"], []).append(r)

    tier3 = set()
    for pid, recs in by_player.items():
        if len(recs) < 5:
            continue
        top_half_hits = 0
        considered = 0
        for r in recs:
            field = int(r.get("field_size") or 0)
            placement = int(r.get("placement") or 999)
            if field <= 1:
                continue
            considered += 1
            if placement <= (field + 1) // 2:
                top_half_hits += 1
        if considered >= 5 and top_half_hits >= 3:
            tier3.add(pid)
    return tier3


def reason_summary(pid: str, tier_value: int, recs_window: list[dict[str, Any]]) -> str:
    recs = sorted(recs_window, key=lambda r: (r.get("tournament_date") or "", r.get("tournament_code") or ""))
    best = [r for r in recs if int(r.get("placement") or 999) <= 4][:3]
    parts = []
    for r in best:
        parts.append(f"{r.get('placement')}. místo ({r.get('tournament_code')}, {r.get('tournament_date')})")
    if tier_value == 1:
        return "Tier 1: 2× umístění 1.–2. v posledních 60 dnech. " + ", ".join(parts)
    if tier_value == 2:
        return "Tier 2: výkonnostní trend v posledních 60 dnech. " + ", ".join(parts)
    return "Tier 3: konzistentní výsledky v sezóně."


def generate_mail(player: dict[str, Any], tip: dict[str, Any]) -> tuple[str, str]:
    player_name = player.get("name") or ""
    club_name = player.get("club") or "—"
    birth_year = player.get("birth_year") or ""
    reason = tip.get("reason_summary") or ""

    subject = f"HEAD ČR — spolupráce (talent: {player_name})"
    body = (
        f"Dobrý den,\n\n"
        f"jmenuji se [JMÉNO], zastupuji značku HEAD v ČR.\n"
        f"Zaregistrovali jsme velmi dobré výsledky hráče {player_name} (ročník {birth_year}) "
        f"z klubu {club_name} v posledních týdnech.\n\n"
        f"Konkrétně: {reason}\n\n"
        f"Rádi bychom nabídli spolupráci formou vybavení značky HEAD (např. raketa + 1× oblečení).\n"
        f"Pokud to dává smysl, prosím předejte kontakt na rodiče/trenéra, případně nám napište zpět.\n\n"
        f"S pozdravem\n"
        f"[JMÉNO PŘÍJMENÍ]\n"
        f"HEAD ČR\n"
        f"[EMAIL] | [TELEFON]\n"
    )
    return subject, body


def generate_tips(
    unified_records: list[dict[str, Any]],
    season: str,
    clubs_directory: dict[str, Any] | None,
    tips_sent: dict[str, Any] | None,
) -> dict[str, Any]:
    tips_sent = tips_sent or {"sent": []}
    sent_ids = {s.get("player_id") for s in tips_sent.get("sent") or [] if s.get("season") == season}

    today = datetime.now().date()
    cutoff = today - timedelta(days=WINDOW_DAYS)

    # filter to records with a valid date
    records_with_date = []
    for r in unified_records:
        d = parse_iso_date(r.get("tournament_date") or "")
        if not d:
            continue
        r = dict(r)
        r["_date"] = d
        records_with_date.append(r)

    records_window = [r for r in records_with_date if r["_date"] >= cutoff]
    records_season = records_with_date  # currently all; can be refined later by season boundaries

    tiers = compute_tiers(records_window)
    tier3 = compute_tier3(records_season)

    # promote Tier3 only if not already 1/2
    for pid in tier3:
        if pid not in tiers:
            tiers[pid] = 3

    # build recs_by_player for reason
    recs_by_player_window: dict[str, list[dict[str, Any]]] = {}
    for r in records_window:
        recs_by_player_window.setdefault(r["player_id"], []).append(r)

    tips = []
    for pid, tier_value in sorted(tiers.items(), key=lambda x: x[1]):
        if pid in sent_ids:
            continue

        # sample player info
        sample = next((r for r in unified_records if r.get("player_id") == pid), None) or {}
        player = {
            "player_id": pid,
            "name": sample.get("name") or "",
            "birth_year": sample.get("birth_year"),
            "club": sample.get("club") or "",
            "category": sample.get("category") or "",
        }

        tip = {
            "tip_id": str(uuid4()),
            "player_id": pid,
            "player_name": player["name"],
            "birth_year": player["birth_year"],
            "category": player["category"],
            "club_name": player["club"],
            "tier": tier_value,
            "tier_label": {1: "Top talent", 2: "Rising star", 3: "Na radaru"}.get(tier_value, ""),
            "reason_summary": reason_summary(pid, tier_value, recs_by_player_window.get(pid, [])),
            "status": "pending",
            "created_at": iso_today(),
        }

        contact = club_contact_lookup(clubs_directory or {}, player.get("club") or "")
        if contact:
            tip["recipient_email"] = contact.get("email") or ""
            tip["club_detail_url"] = contact.get("detail_url") or ""
        else:
            tip["recipient_email"] = ""
            tip["club_detail_url"] = ""

        subject, body = generate_mail(player, tip)
        tip["mail_subject"] = subject
        tip["mail_body"] = body

        tips.append(tip)

    # sort: Tier 1 first, then Tier 2, then Tier 3
    tips.sort(key=lambda t: (t.get("tier") or 99, t.get("player_name") or ""))

    return {
        "generated_at": iso_today(),
        "season": season,
        "window_days": WINDOW_DAYS,
        "tips": tips,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Tips generator (Tier 1/2/3)")
    parser.add_argument("--unified", default="data/results_unified.json")
    parser.add_argument("--clubs", default="data/clubs_directory.json")
    parser.add_argument("--sent", default="data/tips_sent.json")
    parser.add_argument("--out", default="data/tips_pending.json")
    args = parser.parse_args()

    unified = load_json(Path(args.unified), {})
    season = unified.get("season") or ""
    records = unified.get("records") or []

    clubs = load_json(Path(args.clubs), {})
    sent = load_json(Path(args.sent), {"sent": []})

    out = generate_tips(records, season, clubs, sent)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"✅ Tips generated: {args.out} (n={len(out.get('tips') or [])})")


if __name__ == "__main__":
    main()

