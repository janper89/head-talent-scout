from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory


APP_ROOT = Path(__file__).parent.resolve()
DATA_DIR = APP_ROOT / "data"
TIPS_PENDING = DATA_DIR / "tips_pending.json"
TIPS_SENT = DATA_DIR / "tips_sent.json"


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json_atomic(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now().isoformat()


app = Flask(__name__, static_folder=str(APP_ROOT))


@app.get("/")
def index():
    return send_from_directory(APP_ROOT, "dashboard.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(APP_ROOT, filename)


@app.get("/api/tips")
def api_get_tips():
    pending = read_json(TIPS_PENDING, {"tips": []})
    return jsonify(pending)


@app.post("/api/tips/<tip_id>/update")
def api_update_tip(tip_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    pending = read_json(TIPS_PENDING, {"tips": []})
    tips = pending.get("tips") or []

    found = None
    for t in tips:
        if t.get("tip_id") == tip_id:
            found = t
            break

    if not found:
        return jsonify({"ok": False, "error": "tip_not_found"}), 404

    # allowed fields
    for key in ("status", "mail_subject", "mail_body", "rejected_reason"):
        if key in payload:
            found[key] = payload[key]

    found["updated_at"] = now_iso()
    pending["updated_at"] = now_iso()
    write_json_atomic(TIPS_PENDING, pending)
    return jsonify({"ok": True, "tip": found})


@app.post("/api/tips/<tip_id>/mark_sent")
def api_mark_sent(tip_id: str):
    pending = read_json(TIPS_PENDING, {"tips": [], "season": ""})
    tips = pending.get("tips") or []
    season = pending.get("season") or ""

    tip = next((t for t in tips if t.get("tip_id") == tip_id), None)
    if not tip:
        return jsonify({"ok": False, "error": "tip_not_found"}), 404

    tip["status"] = "sent"
    tip["sent_at"] = now_iso()
    pending["updated_at"] = now_iso()
    write_json_atomic(TIPS_PENDING, pending)

    sent = read_json(TIPS_SENT, {"sent": []})
    sent_list = sent.get("sent") or []
    # prevent duplicates per season
    already = any(s.get("player_id") == tip.get("player_id") and s.get("season") == season for s in sent_list)
    if not already:
        sent_list.append(
            {
                "tip_id": tip.get("tip_id"),
                "player_id": tip.get("player_id"),
                "player_name": tip.get("player_name"),
                "season": season,
                "sent_at": tip.get("sent_at"),
            }
        )
        sent["sent"] = sent_list
        sent["updated_at"] = now_iso()
        write_json_atomic(TIPS_SENT, sent)

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="127.0.0.1", port=port, debug=True)

