#!/usr/bin/env python3
"""Watch Agent — the Portfolio Ops Room's second Switch-native agent.

Registered with the Switch gateway exactly like the Ops Agent (agent API,
own API key, zero tools, zero models, no credentials beyond its own key),
but it never answers questions: it WATCHES. Every minute it re-reads the
fleet snapshot (refreshed every five minutes by cron) and diffs the
per-monitor watch states against the last ones it saw. When a monitor
flips — a site goes down, a service recovers — it posts the transition
into the room itself, through the Switch agent API, so the room is a
living workflow rather than a question-answering bot.

First start is seeded silently from the current snapshot and announced
with one honest status post ("Watch Agent online — currently 5/6 up,
site-x DOWN since …"). After that it posts ONLY on change.

Config: watch-agent.env next to this file (written by setup_watch_agent.py):
    SWITCH_API, AGENT_ID, AGENT_API_KEY, ROOM_ID
Optional env: SNAPSHOT_PATH (default ./snapshot.json), POLL_SECS (60),
WATCH_DRY_RUN=1 prints would-be posts instead of sending (logic tests).
Standard library only — nothing to install.
"""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
TZ = ZoneInfo("America/Toronto")
DRY_RUN = os.environ.get("WATCH_DRY_RUN") == "1"
SNAPSHOT_PATH = Path(os.environ.get("SNAPSHOT_PATH", HERE / "snapshot.json"))
POLL_SECS = int(os.environ.get("POLL_SECS", "60"))
STATE_PATH = HERE / "watch-agent-state.json"
if DRY_RUN:
    STATE_PATH = Path(os.environ.get("WATCH_STATE_PATH", "/tmp/watch-agent-state-test.json"))


def load_env(name: str) -> dict:
    env = {}
    p = HERE / name
    if not p.exists():
        return env
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


CFG = load_env("watch-agent.env")
API = CFG.get("SWITCH_API", "http://127.0.0.1:8000").rstrip("/")
AGENT_ID = CFG.get("AGENT_ID", "")
AGENT_KEY = CFG.get("AGENT_API_KEY", "")
ROOM_ID = CFG.get("ROOM_ID", "")


def send(text: str) -> None:
    if DRY_RUN:
        print(f"[dry-run post] {text}", flush=True)
        return
    req = urllib.request.Request(API + f"/agents/{AGENT_ID}/message", method="POST")
    req.add_header("Authorization", f"Bearer {AGENT_KEY}")
    req.add_header("Content-Type", "application/json")
    data = json.dumps({"room_id": ROOM_ID, "content": text}).encode()
    with urllib.request.urlopen(req, data=data, timeout=30) as r:
        r.read()


def monitors_of(snap: dict) -> dict:
    return {m["name"]: m for m in (snap.get("watch") or {}).get("monitors") or []}


def up_count(monitors: dict) -> tuple[int, int]:
    up = sum(1 for m in monitors.values() if m["status"] == "UP")
    return up, len(monitors)


def online_message(snap: dict, monitors: dict) -> str:
    up, total = up_count(monitors)
    down = [m for m in monitors.values() if m["status"] != "UP"]
    msg = (f"👁️ **Watch Agent online** — I'll post in this room the moment a fleet "
           f"monitor flips. Current watch: **{up}/{total} up**.")
    for m in down:
        msg += f"\n🔴 `{m['name']}` is DOWN (since {m['since_toronto']})."
    msg += f"\n\n— Watch Agent · snapshot {snap['generated_at_toronto']}"
    return msg


def transition_message(name: str, old: str, new: dict, snap: dict, monitors: dict) -> str:
    up, total = up_count(monitors)
    gen = snap["generated_at_toronto"]
    if new["status"] == "UP":
        return (f"🟢 **Monitor recovered — `{name}`** is UP again (since {new['since_toronto']}). "
                f"Watch is now {up}/{total} up.\n\n— Watch Agent · snapshot {gen}")
    return (f"🔴 **Monitor DOWN — `{name}`** (since {new['since_toronto']}). "
            f"Watch is now {up}/{total} up.\n\n— Watch Agent · snapshot {gen}")


def load_state() -> dict | None:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            return None
    return None


def save_state(monitors: dict) -> None:
    STATE_PATH.write_text(json.dumps(
        {"monitors": {k: v["status"] for k, v in monitors.items()},
         "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M Toronto")}, indent=1))


def cycle(first: bool) -> None:
    snap = json.loads(SNAPSHOT_PATH.read_text())
    monitors = monitors_of(snap)
    if not monitors:
        print("no monitors in snapshot; skipping", flush=True)
        return
    state = load_state()
    if first or state is None:
        send(online_message(snap, monitors))
        save_state(monitors)
        print(f"[{datetime.now(TZ):%H:%M:%S}] seeded + online post sent "
              f"({up_count(monitors)[0]}/{up_count(monitors)[1]} up)", flush=True)
        return
    prev = state.get("monitors", {})
    changes = []
    for name, m in monitors.items():
        old = prev.get(name)
        if old is not None and old != m["status"]:
            changes.append((name, old, m))
    for name, old, m in changes:
        send(transition_message(name, old, m, snap, monitors))
        print(f"[{datetime.now(TZ):%H:%M:%S}] transition {name}: {old} -> {m['status']} posted", flush=True)
    if changes:
        save_state(monitors)


def main() -> None:
    print(f"[{datetime.now(TZ):%H:%M:%S}] watch-agent starting; room {ROOM_ID}; dry_run={DRY_RUN}", flush=True)
    if not DRY_RUN:
        try:
            req = urllib.request.Request(API + f"/agents/{AGENT_ID}/status", method="POST")
            req.add_header("Authorization", f"Bearer {AGENT_KEY}")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, data=json.dumps({"status": "online"}).encode(), timeout=10) as r:
                r.read()
        except Exception as e:
            print(f"status note: {e}", flush=True)
    first = load_state() is None
    while True:
        try:
            cycle(first)
            first = False
        except (OSError, json.JSONDecodeError, urllib.error.URLError) as e:
            print(f"cycle error: {e}", flush=True)
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
