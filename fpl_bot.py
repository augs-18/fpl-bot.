import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://fantasy.premierleague.com/api"
STATE_FILE = Path(os.environ.get("STATE_FILE", "fpl_state.json"))
HEADERS = {"User-Agent": "Mozilla/5.0 (fpl-alert-bot)"}
STATUS_AR = {
    "a": "متاح",
    "d": "مشكوك",
    "i": "مصاب",
    "s": "موقوف",
    "u": "غير متاح",
    "n": "غير مؤهل",
}


def get(path):
    r = requests.get(f"{BASE}{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def send(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    r.raise_for_status()


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"players": {}, "deadline_alerts": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def my_players(boot, team_id):
    elements = {e["id"]: e for e in boot["elements"]}
    result = {}
    current = next((e for e in boot["events"] if e["is_current"]), None)
    if current:
        picks = get(f"/entry/{team_id}/event/{current['id']}/picks/")["picks"]
        for p in picks:
            result[p["element"]] = elements[p["element"]]
    extra = [n.strip().lower() for n in os.environ.get("EXTRA_WATCH", "").split(",") if n.strip()]
    for e in elements.values():
        if e["web_name"].lower() in extra:
            result[e["id"]] = e
    return result


def check_players(players, state):
    for pid, e in players.items():
        snapshot = {
            "status": e["status"],
            "chance": e["chance_of_playing_next_round"],
            "news": e["news"],
        }
        old = state["players"].get(str(pid))
        if old is not None and old != snapshot:
            chance = snapshot["chance"]
            chance_txt = f"{chance}%" if chance is not None else "غير محدد"
            send(
                f"⚠️ تغيّر وضع {e['web_name']}\n"
                f"الحالة: {STATUS_AR.get(snapshot['status'], snapshot['status'])}\n"
                f"احتمال اللعب: {chance_txt}\n"
                f"الخبر: {snapshot['news'] or 'لا يوجد'}"
            )
        state["players"][str(pid)] = snapshot


def check_deadline(boot, state):
    nxt = next((e for e in boot["events"] if e["is_next"]), None)
    if not nxt:
        return
    deadline = datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))
    hours_left = (deadline - datetime.now(timezone.utc)).total_seconds() / 3600
    if hours_left <= 0:
        return
    for mark in (24, 3, 1):
        key = f"{nxt['id']}-{mark}"
        if hours_left <= mark and key not in state["deadline_alerts"]:
            state["deadline_alerts"].append(key)
            send(
                f"⏰ باقي أقل من {mark} ساعة على ديدلاين الجولة {nxt['id']}.\n"
                f"راجع الإصابات وثبّت الفريق والكابتن."
            )
            break


def main():
    team_id = os.environ.get("FPL_TEAM_ID")
    if not team_id:
        sys.exit("حدد FPL_TEAM_ID")
    boot = get("/bootstrap-static/")
    state = load_state()
    players = my_players(boot, team_id)
    check_players(players, state)
    check_deadline(boot, state)
    save_state(state)
    print(f"تم الفحص: {len(players)} لاعب")


if __name__ == "__main__":
    main()
