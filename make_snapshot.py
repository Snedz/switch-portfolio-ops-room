#!/usr/bin/env python3
"""Generate the Portfolio Ops Room snapshot from REAL fleet data on the Muse VM.

Sources:
  - ~/workspace/deadlines/deadlines.json   (the deadline register)
  - ~/workspace/resilience/watch-status.txt (kuma-lite mutual watcher output)
  - prs.json next to this script            (open PRs, fetched via GitHub connector)

Output: snapshot.json — copied to 67-build-1 where the bridge service reads it.
The snapshot is labelled with its generation time; the agent states that time
in every answer so nobody mistakes a snapshot for a live query.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
HERE = Path(__file__).parent
TERMINAL = {"submitted", "done", "closed", "paid", "passed_deliberate"}


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
        items.append({
            "name": it["name"],
            "due_toronto": dl.strftime("%a %b %d, %H:%M"),
            "days_left": round(days, 1),
            "band": b,
            "status": it["status"],
            "gate": (it.get("gated_by") or {}).get("action"),
        })
    items.sort(key=lambda x: x["days_left"])
    overdue = [i for i in items if i["band"] == "OVERDUE"]
    due_24h = [i for i in items if i["band"] == "T-1"]
    upcoming = [i for i in items if i["band"] not in ("OVERDUE",)][:5]

    watch_raw = ""
    watch_path = Path.home() / "workspace/resilience/watch-status.txt"
    if watch_path.exists():
        watch_raw = watch_path.read_text().strip()

    prs = {"repo": "MissionWinning/67", "open": 0, "latest": []}
    prs_path = HERE / "prs.json"
    if prs_path.exists():
        prs = json.loads(prs_path.read_text())

    snap = {
        "generated_at_toronto": now.strftime("%Y-%m-%d %H:%M Toronto"),
        "generated_at_utc": now.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": [
            "deadline register (deadlines.json) on the fleet VM",
            "kuma-lite mutual watcher (watch-status.txt)",
            "GitHub MissionWinning/67 via connector",
        ],
        "deadlines": {
            "active_total": len(items),
            "counts": counts,
            "overdue": overdue,
            "due_within_24h": due_24h,
            "next_upcoming": upcoming,
        },
        "watch": {"raw": watch_raw},
        "prs": prs,
    }
    out = HERE / "snapshot.json"
    out.write_text(json.dumps(snap, indent=1))
    print(f"snapshot written: {out} — {len(items)} active items, "
          f"{counts['OVERDUE']} overdue, {counts['T-1']} due <=24h, {prs['open']} open PRs")


if __name__ == "__main__":
    main()
