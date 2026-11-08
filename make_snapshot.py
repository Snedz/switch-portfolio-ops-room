#!/usr/bin/env python3
"""Generate the Portfolio Ops Room snapshot from REAL fleet data on the Muse VM.

Sources:
  - ~/workspace/deadlines/deadlines.json   (the deadline register)
  - ~/workspace/resilience/watch-status.txt (kuma-lite mutual watcher output)
  - ~/workspace/resilience/kuma-lite/state/ (per-monitor UP/DOWN + since)
  - prs.json next to this script            (open PRs, fetched via GitHub connector)

Output: snapshot.json — copied to 67-build-1 where the agents read it.
The snapshot is labelled with its generation time; the agents state that
time in every answer so nobody mistakes a snapshot for a live query.
Sections: deadlines (board + gates + due-48h), money (overdue payments +
upcoming payment deadlines), watch (summary line + per-monitor states),
prs. Refreshed every 5 minutes by cron (refresh-snapshot.sh) so the room's
answers — and the Watch Agent's transition detection — stay current.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
HERE = Path(__file__).parent
TERMINAL = {"submitted", "done", "closed", "paid", "passed_deliberate"}
AMOUNT_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")
# Register entries that are money obligations even when filed under another
# category (a collections item is a decision gate AND a debt).
MONEY_IDS = {"telus-dca-collection"}


def band(days: float) -> str:
    if days < 0:
        return "OVERDUE"
    if days <= 1:
        return "T-1"
    if days <= 3:
        return "T-3"
    if days <= 7:
        return "T-7"
    return "OK"


def load_monitors() -> list:
    state_dir = Path.home() / "workspace/resilience/kuma-lite/state"
    monitors = []
    if state_dir.exists():
        for f in sorted(state_dir.glob("*.status")):
            name = f.name[: -len(".status")]
            status = f.read_text().strip().upper()
            since_raw = ""
            since_file = state_dir / f"{name}.since"
            if since_file.exists():
                since_raw = since_file.read_text().strip()
            since_toronto = since_raw
            try:
                dt = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
                since_toronto = dt.astimezone(TZ).strftime("%a %b %d, %H:%M")
            except ValueError:
                pass
            monitors.append({"name": name, "status": status,
                             "since_toronto": since_toronto})
    return monitors


def main() -> None:
    now = datetime.now(TZ)
    data = json.loads((Path.home() / "workspace/deadlines/deadlines.json").read_text())
    items = []
    counts = {"OVERDUE": 0, "T-1": 0, "T-3": 0, "T-7": 0, "OK": 0}
    for it in data["items"]:
        if it["status"] in TERMINAL:
            continue
        dl = datetime.fromisoformat(it["deadline"]).astimezone(TZ)
        days = (dl - now).total_seconds() / 86400
        b = band(days)
        counts[b] += 1
        m = AMOUNT_RE.search(it["name"])
        items.append({
            "id": it["id"],
            "name": it["name"],
            "category": it.get("category", ""),
            "due_toronto": dl.strftime("%a %b %d, %H:%M"),
            "days_left": round(days, 1),
            "band": b,
            "status": it["status"],
            "gate": (it.get("gated_by") or {}).get("action"),
            "gate_minutes": (it.get("gated_by") or {}).get("minutes"),
            "amount": m.group(0) if m else None,
        })
    items.sort(key=lambda x: x["days_left"])
    overdue = [i for i in items if i["band"] == "OVERDUE"]
    due_24h = [i for i in items if i["band"] == "T-1"]
    due_48h = [i for i in items if 0 <= i["days_left"] <= 2]
    upcoming = [i for i in items if i["band"] not in ("OVERDUE",)][:5]

    # Founder gates: every active item whose next step is a founder action,
    # most urgent first.
    gates = [i for i in items if i["gate"]][:10]
    gates_out = [{
        "name": i["name"], "due_toronto": i["due_toronto"],
        "days_left": i["days_left"], "band": i["band"],
        "action": i["gate"], "minutes": i["gate_minutes"],
    } for i in gates]

    # Money: overdue obligations first (payments + named money items),
    # then payment deadlines coming due in the next two weeks.
    def is_money(i):
        return i["category"] == "payment" or i["id"] in MONEY_IDS

    money_overdue = [{
        "name": i["name"], "amount": i["amount"], "due_toronto": i["due_toronto"],
        "days_left": i["days_left"], "gate": i["gate"],
    } for i in overdue if is_money(i)]
    money_upcoming = [{
        "name": i["name"], "amount": i["amount"], "due_toronto": i["due_toronto"],
        "days_left": i["days_left"], "gate": i["gate"],
    } for i in items if is_money(i) and 0 < i["days_left"] <= 14][:5]

    watch_raw = ""
    watch_path = Path.home() / "workspace/resilience/watch-status.txt"
    if watch_path.exists():
        watch_raw = watch_path.read_text().strip()
    monitors = load_monitors()

    prs = {"repo": "MissionWinning/67", "open": 0, "latest": []}
    prs_path = HERE / "prs.json"
    if prs_path.exists():
        prs = json.loads(prs_path.read_text())

    snap = {
        "generated_at_toronto": now.strftime("%Y-%m-%d %H:%M Toronto"),
        "generated_at_utc": now.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": [
            "deadline register (deadlines.json) on the fleet VM",
            "kuma-lite mutual watcher (watch-status.txt + per-monitor state)",
            "GitHub MissionWinning/67 via connector",
        ],
        "deadlines": {
            "active_total": len(items),
            "counts": counts,
            "overdue": overdue,
            "due_within_24h": due_24h,
            "due_within_48h": due_48h,
            "next_upcoming": upcoming,
            "gates": gates_out,
        },
        "money": {"overdue": money_overdue, "upcoming": money_upcoming},
        "watch": {"raw": watch_raw, "monitors": monitors},
        "prs": prs,
    }
    out = HERE / "snapshot.json"
    out.write_text(json.dumps(snap, indent=1))
    up = sum(1 for mon in monitors if mon["status"] == "UP")
    print(f"snapshot written: {out} — {len(items)} active items, "
          f"{counts['OVERDUE']} overdue, {len(gates_out)} gates, "
          f"{len(money_overdue)} overdue money items, "
          f"monitors {up}/{len(monitors)} up, {prs['open']} open PRs")


if __name__ == "__main__":
    main()
