#!/usr/bin/env python3
"""Offline quickstart — see all seven Ops Agent answers in ~60 seconds.

No Switch stack, no Mattermost, no secrets, no network:

    python3 quickstart.py

This prints exactly what the Ops Agent answers in the room for each of
its seven questions, computed from `snapshot.example.json` (a real
snapshot of the fleet's data, Nov 7 2026) — or from `snapshot.json` if
you drop a fresher one next to this file.

How this file relates to the live service: `switch_agent.py` cannot be
imported offline (it is a service — it reads its Switch credentials at
import time and then long-polls the gateway). The seven answer
formatters below are therefore *duplicated* from it verbatim, so this
demo can never touch, import, or destabilise the running agent. If the
two ever drift, the transcript in `evidence/` is the ground truth for
what the live agent actually said.

Standard library only — nothing to install.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent


def load_snapshot() -> dict:
    for name in ("snapshot.json", "snapshot.example.json"):
        p = HERE / name
        if p.exists():
            print(f"(reading {name})\n")
            return json.loads(p.read_text())
    raise SystemExit("no snapshot.json or snapshot.example.json next to quickstart.py")


# --- The seven formatters, duplicated verbatim from switch_agent.py ---

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
    lines.append("\nAmounts are read from the register entries themselves; the Etsy payout bank "
                 "(Airwallex) is locked by standing instruction and never appears here as an action.")
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


FORMATTERS = {
    "deadlines": fmt_deadlines,
    "gates": fmt_gates,
    "money": fmt_money,
    "health": fmt_health,
    "brief": fmt_brief,
    "status": fmt_status,
    "prs": fmt_prs,
}


def main() -> None:
    s = load_snapshot()
    label = f"\n\n— Ops Agent · snapshot {s['generated_at_toronto']} (data age is labelled, never hidden)"
    for kind, fn in FORMATTERS.items():
        print(f"\n{'=' * 70}\n@ops-agent {kind}\n{'=' * 70}")
        print(fn(s) + label)
    print("\nThat's the whole agent: seven deterministic answers over a")
    print("labelled snapshot. In the room, Switch delivers the question and")
    print("publishes the answer — see README.md and evidence/.")


if __name__ == "__main__":
    main()
