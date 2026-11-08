#!/usr/bin/env python3
"""Ops Agent — a Switch-native agent service for the Portfolio Ops Room.

This is the agent's runtime. It connects to the self-hosted Switch gateway
exactly the way Switch intends agents to connect:

  * registered through the Switch agent API (POST /agents, bootstrap token),
  * receives room messages by long-polling its Switch event stream
    (GET /agents/{id}/events),
  * answers through the Switch agent API (POST /agents/{id}/message),
    which the Switch Mattermost bridge publishes into the channel.

Take Switch away and this agent is deaf and mute: there is no other path in
or out. It is deliberately not an LLM — it is a deterministic staff agent
that answers seven questions from a snapshot of REAL fleet data:

    deadlines   -> the deadline board (register on the fleet VM)
    gates       -> founder-gated actions waiting, most urgent first
    money       -> overdue payments + upcoming payment deadlines
    health      -> per-monitor watch state (box <-> VM watch layer)
    brief       -> one compact brief: overdues + due-48h + gates + watch
    status      -> the mutual watcher summary line
    prs         -> open pull requests on MissionWinning/67

Trigger it by mentioning the agent or just naming the topic in the room:
"@ops-agent deadlines", "gates?", "brief". Every answer is labelled with
the snapshot's generation time — a snapshot is never dressed up as a live
query. The snapshot is re-read for every answer and refreshed every five
minutes by cron (see refresh-snapshot.sh), so answers stay current.

It shares the room with the Watch Agent (watch_agent.py), which posts
monitor transitions and the twice-daily digest; both agents' own posts are
ignored here so the room never talks to itself.

Config: switch-agent.env next to this file (written by setup_switch.py):
    SWITCH_API, AGENT_ID, AGENT_API_KEY, ROOM_ID
Standard library only — nothing to install.
"""
import json
import time
import urllib.request
import urllib.error
from collections import deque
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
TZ = ZoneInfo("America/Toronto")
ROOM_ID_FALLBACK = ""


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


CFG = load_env("switch-agent.env")
API = CFG.get("SWITCH_API", "http://127.0.0.1:8000").rstrip("/")
AGENT_ID = CFG["AGENT_ID"]
AGENT_KEY = CFG["AGENT_API_KEY"]
ROOM_ID = CFG["ROOM_ID"]

# Senders whose messages are Switch system traffic or the room's own
# agents — never questions. The Watch Agent and the digest post under
# these identities; the Ops Agent must never answer its own room.
SYSTEM_SENDERS = {"ops-agent", "switch-admin", "bridge-mattermost",
                  "watch-agent", "watch agent"}


def api(method: str, path: str, body: dict | None = None, timeout: int = 40) -> dict:
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", f"Bearer {AGENT_KEY}")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def send(text: str) -> None:
    api("POST", f"/agents/{AGENT_ID}/message", {"room_id": ROOM_ID, "content": text})


def load_snapshot() -> dict:
    return json.loads((HERE / "snapshot.json").read_text())


def fmt_deadlines(s: dict) -> str:
    d = s["deadlines"]
    c = d["counts"]
    lines = [f"**Deadline board** — {d['active_total']} active items "
             f"({c['OVERDUE']} overdue, {c['T-1']} due ≤24h, {c['T-3']} due ≤3d, {c['T-7']} due ≤7d)"]
    if d["overdue"]:
        lines.append("\n🔴 **Overdue:**")
        for i in d["overdue"]:
            lines.append(f"- {i['name']} — was due {i['due_toronto']} ({abs(i['days_left'])}d ago)")
    if d["due_within_24h"]:
        lines.append("\n🟠 **Due within 24h:**")
        for i in d["due_within_24h"]:
            lines.append(f"- {i['name']} — due {i['due_toronto']}")
    if d["next_upcoming"]:
        lines.append("\n**Next up:**")
        for i in d["next_upcoming"]:
            lines.append(f"- {i['name']} — due {i['due_toronto']} ({i['days_left']}d)")
    return "\n".join(lines)


def fmt_gates(s: dict) -> str:
    gates = (s.get("deadlines") or {}).get("gates") or []
    if not gates:
        return "**Founder gates** — nothing is waiting on a founder action in this snapshot."
    lines = [f"**Founder gates — {len(gates)} actions waiting on you, most urgent first:**"]
    for n, g in enumerate(gates, 1):
        when = (f"overdue by {abs(g['days_left'])}d" if g["days_left"] < 0
                else f"due {g['due_toronto']} ({g['days_left']}d)")
        mins = f" · ~{g['minutes']} min" if g.get("minutes") else ""
        lines.append(f"{n}. **{g['action']}**{mins}\n   ↳ {g['name']} — {when}")
    lines.append("\nThese are the register's `gated_by` actions: steps only the founder can take "
                 "(payments, submissions, identity checks). Everything not gated keeps moving without him.")
    return "\n".join(lines)


def fmt_money(s: dict) -> str:
    money = s.get("money") or {}
    over, up = money.get("overdue") or [], money.get("upcoming") or []
    if not over and not up:
        return "**Money** — no overdue payments and no payment deadlines in the next two weeks."
    lines = ["**Money — what's owed and what's coming**"]
    if over:
        lines.append("\n🔴 **Overdue:**")
        for i in over:
            amt = f"{i['amount']} — " if i.get("amount") else ""
            lines.append(f"- {amt}{i['name']} (was due {i['due_toronto']}, {abs(i['days_left'])}d ago)")
            if i.get("gate"):
                lines.append(f"  ↳ Next step: {i['gate']}")
    if up:
        lines.append("\n**Payment deadlines ≤14d:**")
        for i in up:
            amt = f"{i['amount']} — " if i.get("amount") else ""
            lines.append(f"- {amt}{i['name']} — due {i['due_toronto']} ({i['days_left']}d)")
    lines.append("\nAmounts are read from the register entries themselves; the shop's payout bank "
                 "is locked by standing instruction and never appears here as an action.")
    return "\n".join(lines)


def fmt_status(s: dict) -> str:
    raw = (s.get("watch") or {}).get("raw", "").strip()
    if not raw:
        return "**Fleet status** — watcher status file is empty in this snapshot."
    return (f"**Fleet watch status** (kuma-lite mutual watcher, box ↔ VM):\n"
            f"`{raw}`\n"
            "The box watches the VM (dead-man's switch + Healthchecks + Beszel) and the VM "
            "watches the box back. A DOWN line names the monitor and how many are up.")


def fmt_health(s: dict) -> str:
    watch = s.get("watch") or {}
    monitors = watch.get("monitors") or []
    if not monitors:
        return ("**Watch health** — no per-monitor state in this snapshot.\n"
                f"Summary: `{watch.get('raw', 'unavailable')}`")
    up = sum(1 for m in monitors if m["status"] == "UP")
    lines = [f"**Watch health — {up}/{len(monitors)} monitors UP** "
             "(kuma-lite, checked every 5 min from the fleet VM):"]
    for m in monitors:
        icon = "🟢" if m["status"] == "UP" else "🔴"
        lines.append(f"- {icon} `{m['name']}` — {m['status']} since {m['since_toronto']}")
    lines.append("\nThe watch layer: the VM monitors the box (SSH, Healthchecks, ntfy, "
                 "Mattermost) and both public sites; the box runs the dead-man's switch, "
                 "Healthchecks, ntfy and Beszel back. The Watch Agent in this room posts "
                 "here the moment any of these flips.")
    return "\n".join(lines)


def fmt_prs(s: dict) -> str:
    p = s["prs"]
    lines = [f"**Open pull requests — {p['repo']}: {p['open']}**"]
    for pr in p["latest"]:
        lines.append(f"- #{pr['number']} {pr['title']}")
    return "\n".join(lines)


def fmt_brief(s: dict) -> str:
    d = s["deadlines"]
    watch = s.get("watch") or {}
    monitors = watch.get("monitors") or []
    up = sum(1 for m in monitors if m["status"] == "UP")
    down = [m["name"] for m in monitors if m["status"] != "UP"]
    lines = [f"**Portfolio brief** — {s['generated_at_toronto']}"]
    if d["overdue"]:
        lines.append(f"\n🔴 **Overdue ({len(d['overdue'])}):**")
        for i in d["overdue"]:
            lines.append(f"- {i['name']} — {abs(i['days_left'])}d overdue")
    else:
        lines.append("\n🔴 **Overdue:** none")
    if d.get("due_within_48h"):
        lines.append(f"\n🟠 **Due within 48h ({len(d['due_within_48h'])}):**")
        for i in d["due_within_48h"][:5]:
            lines.append(f"- {i['name']} — due {i['due_toronto']}")
    gates = d.get("gates") or []
    if gates:
        lines.append(f"\n🔑 **Top gates waiting on the founder ({len(gates)} total):**")
        for g in gates[:3]:
            lines.append(f"- {g['action']} — {g['name']}")
    watch_line = f"{up}/{len(monitors)} monitors up" if monitors else watch.get("raw", "watcher state unavailable")
    if down:
        watch_line += f" — DOWN: {', '.join(down)}"
    lines.append(f"\n🩺 **Watch:** {watch_line}")
    lines.append(f"📬 **PRs:** {s['prs']['open']} open on {s['prs']['repo']}")
    lines.append(f"📋 **Board:** {d['active_total']} active items "
                 f"({d['counts']['OVERDUE']} overdue, {d['counts']['T-1']} ≤24h, "
                 f"{d['counts']['T-3']} ≤3d, {d['counts']['T-7']} ≤7d)")
    return "\n".join(lines)


HELP = ("**Ops Agent — Portfolio Ops Room.** Ask me in plain words:\n"
        "- `deadlines` — the board: overdue, due ≤24h, next five\n"
        "- `gates` — founder actions waiting, most urgent first\n"
        "- `money` — overdue payments + payment deadlines coming\n"
        "- `health` — per-monitor watch state (box ↔ VM)\n"
        "- `brief` — one compact brief: overdues, due-48h, gates, watch, PRs\n"
        "- `status` — fleet watch summary line\n"
        "- `prs` — open pull requests on MissionWinning/67\n"
        "I answer from a labelled snapshot of the fleet's real register, watcher and GitHub data. "
        "The Watch Agent posts monitor flips and a twice-daily digest in this room.")


def intent(body: str) -> str | None:
    m = body.lower().replace("@ops-agent", " ").replace("@watch-agent", " ").replace("!", " ")
    words = set(m.split())
    if "deadlines" in words or "deadline" in words or "board" in words:
        return "deadlines"
    if "gates" in words or "gate" in words:
        return "gates"
    if "money" in words or "payments" in words or "payment" in words or "bills" in words or "owe" in words:
        return "money"
    if "health" in words or "monitors" in words or "monitor" in words or "uptime" in words:
        return "health"
    if "brief" in words or "briefing" in words or "summary" in words or "digest" in words:
        return "brief"
    if "status" in words or "watch" in words or "fleet" in words:
        return "status"
    if "prs" in words or "pr" in words or "pull" in words:
        return "prs"
    if "help" in words or "commands" in words:
        return "help"
    return None


FORMATTERS = {
    "deadlines": fmt_deadlines,
    "gates": fmt_gates,
    "money": fmt_money,
    "health": fmt_health,
    "brief": fmt_brief,
    "status": fmt_status,
    "prs": fmt_prs,
}


def answer(kind: str) -> str:
    s = load_snapshot()
    label = f"\n\n— Ops Agent · snapshot {s['generated_at_toronto']} (data age is labelled, never hidden)"
    fn = FORMATTERS.get(kind)
    if fn is None:
        return HELP + label
    return fn(s) + label


def main() -> None:
    print(f"[{datetime.now(TZ):%H:%M:%S}] ops-agent starting; room {ROOM_ID}", flush=True)
    try:
        api("POST", f"/agents/{AGENT_ID}/status", {"status": "online"}, timeout=10)
        print("status set online", flush=True)
    except Exception as e:
        print(f"status note: {e}", flush=True)
    seen: deque[str] = deque(maxlen=500)
    while True:
        try:
            resp = api("GET", f"/agents/{AGENT_ID}/events?timeout=20&rooms={ROOM_ID}", timeout=30)
            for ev in resp.get("events", []):
                if ev.get("type") != "message" or ev.get("room_id") != ROOM_ID:
                    continue
                p = ev.get("payload", {})
                mid = p.get("message_id") or ""
                if mid and mid in seen:
                    continue
                if mid:
                    seen.append(mid)
                sender = (p.get("sender_name") or "").lower()
                sender_ref = (p.get("sender") or "").lower()
                body = p.get("body") or ""
                if sender in SYSTEM_SENDERS or "switch-agent" in sender_ref or "bridge-" in sender_ref:
                    continue
                if body.startswith("**Available commands:**"):
                    continue  # Switch's own bang-command help, not a question
                kind = intent(body)
                if not kind:
                    continue
                print(f"[{datetime.now(TZ):%H:%M:%S}] '{body[:50]}' from {sender} -> {kind}", flush=True)
                send(answer(kind))
                print(f"[{datetime.now(TZ):%H:%M:%S}] answered {kind}", flush=True)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"poll error: {e}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
