#!/usr/bin/env python3
"""Producer Agent — a Switch-native agent service for the Creator Room.

The second room on the fleet's self-hosted Switch deployment (the first
is the Portfolio Ops Room). Same connection pattern, proven tonight:
registered through the Switch agent API (POST /agents, bootstrap token),
receives room messages by long-polling its Switch event stream
(GET /agents/{id}/events), answers through the Switch agent API
(POST /agents/{id}/message), which the Switch Mattermost bridge
publishes into the #creator-room channel. Take Switch away and this
agent is deaf and mute.

It is deliberately not an LLM — a deterministic staff agent that answers
five questions from a snapshot of the founder's REAL media pipeline:

    ideas    -> the H3 prompt pack queue + the lane-2 pilot slate
    script   -> the script template state (template ready, no episode)
    renders  -> the clips that actually exist on disk + generation state
    clips    -> the clipping lane's true state (labelled, dated)
    next     -> the honest next action

TRUTHFULNESS IS THE WHOLE POINT of this agent: the media pipeline is
mostly WAITING — generation is blocked on a founder route decision, no
episode script exists, the clipper has never posted and has earned $0 —
and every answer says so plainly. No answer may overstate the pipeline.
Every answer is labelled with the snapshot's generation time; the
snapshot is re-read for every answer.

It shares the deployment with the Ops Agent and the Watch Agent;
SYSTEM_SENDERS includes all three room agents so no room ever answers
itself or another agent.

Config: producer-agent.env next to this file (written by
setup_producer.py): SWITCH_API, AGENT_ID, AGENT_API_KEY, ROOM_ID.
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


CFG = load_env("producer-agent.env")
API = CFG.get("SWITCH_API", "http://127.0.0.1:8000").rstrip("/")
AGENT_ID = CFG["AGENT_ID"]
AGENT_KEY = CFG["AGENT_API_KEY"]
ROOM_ID = CFG["ROOM_ID"]

# Senders whose messages are Switch system traffic or the deployment's
# own agents — never questions. All three room agents are listed so the
# rooms never answer each other.
SYSTEM_SENDERS = {"producer", "ops-agent", "watch-agent", "watch agent",
                  "switch-admin", "bridge-mattermost"}


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
    return json.loads((HERE / "producer-snapshot.json").read_text())


def fmt_ideas(s: dict) -> str:
    i = s["ideas"]
    lines = ["**Ideas — the H3 animated-shorts queue** "
             f"(prompt pack v1 {'on file' if i['prompt_pack_v1'] else 'MISSING'}, "
             f"v1.2 grammar addendum {'on file' if i['prompt_pack_v12_addendum'] else 'missing'}):"]
    for it in i["items"]:
        lines.append(f"- §{it['n']} **{it['title']}** — {it['state']}")
    p = i["lane2_pilot"]
    lines.append(f"\n**Lane 2 — owned animated shorts (the studio lane):** pilot is {p['state']}.")
    for c in p["clips"]:
        lines.append(f"- {c}")
    lines.append(f"Also blocked on: {p['also_blocked_on']}.")
    lines.append("\nHonest summary: the ideas are written and specced. None of the queued ones "
                 "has been generated — see `renders` for why.")
    return "\n".join(lines)


def fmt_script(s: dict) -> str:
    sc = s["scripts"]
    lines = ["**Scripts — where the writing actually stands:**"]
    lines.append(f"- Template: {'READY' if sc['template_ready'] else 'missing'} — {sc['template']}")
    lines.append(f"- Episode scripts: **{sc['honest_state']}**")
    lines.append("\nSo `script` today means: the shape of episode 1 is fully specified "
                 "(cold open mid-failure, 5–7 one-failure-one-fix beats, bookend close, "
                 "≤2 short narration sentences per beat) and the writing itself has not started.")
    return "\n".join(lines)


def fmt_renders(s: dict) -> str:
    r = s["renders"]
    lines = ["**Renders — what actually exists on disk:**"]
    for c in r["clips"]:
        st = c["stat"]
        if st:
            lines.append(f"- `{c['file']}` — {st['size_mb']} MB, on disk since {st['modified_toronto']}\n  {c['verdict']}")
        else:
            lines.append(f"- `{c['file']}` — NOT FOUND on disk in this snapshot")
    g = r["generation"]
    lines.append(f"\n**Generation: {g['state']}.** {g['why']}")
    lines.append(f"Unblocks with: {g['unblocks_with']}.")
    a = r["assembly"]
    lines.append(f"\n**Assembly:** {'proven' if a['proven'] else 'not proven'} — {a['note']}")
    lines.append("\nTwo clips exist. Both are October test clips. Nothing has been generated since, "
                 "and this agent will not pretend otherwise.")
    return "\n".join(lines)


def fmt_clips(s: dict) -> str:
    c = s.get("clipping")
    if not c:
        return ("**Clipping lane** — not in this snapshot: "
                f"{s.get('clipping_note') or 'state file unavailable.'} "
                "I won't guess at its state.")
    lines = [f"**Clipping lane — true state as of {c['updated']} (labelled stale — nothing newer is on record):**"]
    lines.append(f"- Pipeline: {c['pipeline_status']} — {c['pipeline_note']}")
    lines.append(f"- Samples: {c['samples_status']}; **posted: {'yes' if c['samples_posted'] else 'NO — never posted'}**")
    lines.append(f"- Earned: **${c['earned_usd']}**")
    lines.append(f"- Payout method: {c['payout_method']}; accounts: {c['accounts_status']}")
    lines.append("- Still open: " + "; ".join(c["open_tasks"]))
    lines.append("\nPlainly: the clipping machine was built and proven on samples in October, "
                 "then parked. Reviving it needs a campaign pick — see `next`.")
    return "\n".join(lines)


def fmt_next(s: dict) -> str:
    n = s["next"]
    lines = ["**Next — the honest next action:**", n["honest_next_action"], "\n**Also waiting, in the open:**"]
    for w in n["also_waiting"]:
        lines.append(f"- {w}")
    lines.append("\nNothing on this list is hidden work the fleet forgot — it is a short queue "
                 "behind one founder decision, and this room exists so that stays visible.")
    return "\n".join(lines)


HELP = ("**Producer Agent — Creator Room.** I report the media pipeline's true state. Ask me:\n"
        "- `ideas` — the H3 prompt-pack queue + the lane-2 pilot slate\n"
        "- `script` — script template state (and the honest episode count)\n"
        "- `renders` — the clips that exist on disk + generation state\n"
        "- `clips` — the clipping lane's true state, labelled with its date\n"
        "- `next` — the honest next action\n"
        "I answer from a labelled snapshot of real files. Where the pipeline is waiting, I say so.")


def intent(body: str) -> str | None:
    m = (body.lower().replace("@producer", " ").replace("@ops-agent", " ")
         .replace("@watch-agent", " ").replace("!", " "))
    words = set(m.split())
    if "ideas" in words or "idea" in words or "queue" in words or "prompts" in words or "prompt" in words:
        return "ideas"
    if "script" in words or "scripts" in words or "episode" in words or "template" in words:
        return "script"
    if "renders" in words or "render" in words or "generated" in words or "generation" in words:
        return "renders"
    if "clips" in words or "clip" in words or "clipping" in words or "clipper" in words:
        return "clips"
    if "next" in words or "blocked" in words or "waiting" in words:
        return "next"
    if "help" in words or "commands" in words:
        return "help"
    return None


FORMATTERS = {
    "ideas": fmt_ideas,
    "script": fmt_script,
    "renders": fmt_renders,
    "clips": fmt_clips,
    "next": fmt_next,
}


def answer(kind: str) -> str:
    s = load_snapshot()
    label = f"\n\n— Producer Agent · snapshot {s['generated_at_toronto']} (data age is labelled, never hidden)"
    fn = FORMATTERS.get(kind)
    if fn is None:
        return HELP + label
    return fn(s) + label


def main() -> None:
    print(f"[{datetime.now(TZ):%H:%M:%S}] producer starting; room {ROOM_ID}", flush=True)
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
