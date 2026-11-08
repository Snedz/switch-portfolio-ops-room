#!/usr/bin/env python3
"""Producer Agent v2 — a Switch-native agent service for the Creator Room.

The second room on the fleet's self-hosted Switch deployment (the first
is the Portfolio Ops Room). Registered through the Switch agent API
(POST /agents, bootstrap token), it receives room messages by
long-polling its Switch event stream (GET /agents/{id}/events) and
answers through the Switch agent API (POST /agents/{id}/message), which
the Switch Mattermost bridge publishes into the #creator-room channel.
Take Switch away and this agent is deaf and mute.

It is deliberately not an LLM — a deterministic staff agent that
answers from a snapshot of the founder's REAL media pipeline. v2 adds,
over the original five questions:

    status   -> one-screen overview of the whole pipeline
    credits  -> the true credit numbers and the pending route decision
    review   -> the human review gate state (nothing posts unreviewed)
    sources  -> where every fact in the snapshot comes from
    health   -> the agent's own self-check (uptime, snapshot, documents)

…plus two pieces of infrastructure:

  * ROOM DOCUMENTS — the agent publishes the snapshot and the
    state/review-gate as agent-maintained documents attached to this
    room (Switch gateway documents API; see room_documents.py), and
    re-renders them whenever the snapshot changes.
  * SNAPSHOT FALLBACK CHAIN — fresh snapshot file -> last-good cache ->
    an explicit "snapshot unavailable" answer. Numbers are never
    invented: if there is no snapshot, the agent says so and stops.

TRUTHFULNESS IS THE WHOLE POINT of this agent: the media pipeline is
mostly WAITING — generation is blocked on a founder route decision, no
episode script exists, the clipper has never posted and has earned $0 —
and every answer says so plainly. Every answer is labelled with the
snapshot's generation time, and a staleness banner is prepended when
the snapshot is older than STALE_AFTER_MINUTES.

It shares the deployment with the Ops Agent and the Watch Agent;
SYSTEM_SENDERS includes all three room agents so no room ever answers
itself or another agent.

Config: producer-agent.env next to this file (written by
setup_producer.py): SWITCH_API, AGENT_ID, AGENT_API_KEY, ROOM_ID.
Room-document publishing additionally reads the deployment stack env
(STACK_ENV, default /root/switch-smoke/.env) the same way
setup_producer.py does. Standard library only — nothing to install.
"""
import json
import os
import time
import urllib.request
import urllib.error
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import room_documents

HERE = Path(__file__).parent
TZ = ZoneInfo("America/Toronto")
STALE_AFTER_MINUTES = 30
SNAPSHOT_FILE = HERE / "producer-snapshot.json"
LAST_GOOD_FILE = HERE / "producer-snapshot.last-good.json"
STACK_ENV = Path(os.environ.get("STACK_ENV", "/root/switch-smoke/.env"))


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
# .get with empty defaults keeps the module importable off-box (unit
# tests); the deployed service always has the env file setup wrote.
AGENT_ID = CFG.get("AGENT_ID", "")
AGENT_KEY = CFG.get("AGENT_API_KEY", "")
ROOM_ID = CFG.get("ROOM_ID", "")

# Senders whose messages are Switch system traffic or the deployment's
# own agents — never questions. All three room agents are listed so the
# rooms never answer each other.
SYSTEM_SENDERS = {"producer", "ops-agent", "watch-agent", "watch agent",
                  "switch-admin", "bridge-mattermost"}

# Runtime state the health intent reports. Mutated by main() only.
RUNTIME = {"started_at": datetime.now(TZ), "last_poll_ok": None,
           "poll_errors": 0, "answers": 0}


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


# ---------------------------------------------------------------------------
# Snapshot store — the fallback chain.
#
#   1. fresh file      producer-snapshot.json, re-read for every answer;
#                      every successful read refreshes the last-good cache.
#   2. last-good cache producer-snapshot.last-good.json, served with a
#                      loud banner when the fresh file is missing/corrupt.
#   3. unavailable     an explicit answer saying there is no snapshot.
#                      The agent never reconstructs numbers from memory.
# ---------------------------------------------------------------------------
class SnapshotStore:
    def __init__(self, fresh: Path = SNAPSHOT_FILE, cache: Path = LAST_GOOD_FILE):
        self.fresh_path = fresh
        self.cache_path = cache
        self.last_good_at: str | None = None

    def _read(self, path: Path) -> dict | None:
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def load(self) -> dict | None:
        """Return a view: {data, origin, generated_at, age_minutes} or None."""
        snap = self._read(self.fresh_path)
        origin = "fresh"
        if snap is None:
            snap = self._read(self.cache_path)
            origin = "last-good cache"
        if snap is None:
            return None
        if origin == "fresh":
            try:  # keep the cache warm, atomically
                tmp = self.cache_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(snap))
                tmp.replace(self.cache_path)
                self.last_good_at = snap.get("generated_at_toronto")
            except OSError:
                pass
        age = None
        try:
            gen = datetime.strptime(snap["generated_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
            gen = gen.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - gen).total_seconds() / 60
        except (KeyError, ValueError):
            pass
        return {"data": snap, "origin": origin,
                "generated_at": snap.get("generated_at_toronto", "unknown"),
                "age_minutes": age}


STORE = SnapshotStore()
PUBLISHER = room_documents.DocumentPublisher(STACK_ENV, API, ROOM_ID)


# ---------------------------------------------------------------------------
# Formatters. Each takes (snapshot, ctx); ctx carries the snapshot's
# origin/age and the document-sync state so status/health can report them.
# ---------------------------------------------------------------------------
def fmt_ideas(s: dict, ctx: dict) -> str:
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


def fmt_script(s: dict, ctx: dict) -> str:
    sc = s["scripts"]
    lines = ["**Scripts — where the writing actually stands:**"]
    lines.append(f"- Template: {'READY' if sc['template_ready'] else 'missing'} — {sc['template']}")
    lines.append(f"- Episode scripts: **{sc['honest_state']}**")
    lines.append("\nSo `script` today means: the shape of episode 1 is fully specified "
                 "(cold open mid-failure, 5–7 one-failure-one-fix beats, bookend close, "
                 "≤2 short narration sentences per beat) and the writing itself has not started.")
    return "\n".join(lines)


def fmt_renders(s: dict, ctx: dict) -> str:
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


def fmt_clips(s: dict, ctx: dict) -> str:
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


def fmt_next(s: dict, ctx: dict) -> str:
    n = s["next"]
    lines = ["**Next — the honest next action:**", n["honest_next_action"], "\n**Also waiting, in the open:**"]
    for w in n["also_waiting"]:
        lines.append(f"- {w}")
    lines.append("\nNothing on this list is hidden work the fleet forgot — it is a short queue "
                 "behind one founder decision, and this room exists so that stays visible.")
    return "\n".join(lines)


def fmt_status(s: dict, ctx: dict) -> str:
    g = s["renders"]["generation"]
    items = s["ideas"]["items"]
    done = sum(1 for it in items if it["state"].startswith("done"))
    age = ctx["age_minutes"]
    age_txt = f"{age:.0f} min old" if age is not None else "age unknown"
    docs = ctx["docs"]
    doc_txt = (f"{docs['documents']} published, last sync {docs['last_sync_toronto']}"
               if docs["enabled"] and docs["documents"] else "not published (see `health`)")
    c = s.get("clipping")
    clip_txt = (f"parked since {c['updated'][:10]}; never posted; earned $0"
                if c else "not in this snapshot")
    lines = ["**Status — the Creator Room in one screen:**",
             f"- Snapshot: {ctx['generated_at']} ({age_txt}, via {ctx['origin']})",
             f"- Generation: **{g['state']}** — blocked on the founder's production-route decision",
             f"- Ideas queue: {len(items)} items ({done} done, {len(items) - done} queued); "
             f"lane-2 pilot {s['ideas']['lane2_pilot']['state']}",
             f"- Renders on disk: {sum(1 for cl in s['renders']['clips'] if cl['stat'])} "
             f"of {len(s['renders']['clips'])} expected clips",
             f"- Clipping lane: {clip_txt}",
             f"- Room documents: {doc_txt}",
             "\nDetail lives behind `ideas` / `script` / `renders` / `clips` / `credits` / "
             "`review` / `next`. The one decision everything waits on is in `next`."]
    return "\n".join(lines)


def fmt_credits(s: dict, ctx: dict) -> str:
    c = s.get("credits")
    g = s["renders"]["generation"]
    if not c:
        return ("**Credits — from the generation record (structured credit data is not "
                f"in this snapshot):**\n- {g['why']}\n- Unblocks with: {g['unblocks_with']}.")
    lines = ["**Credits — the true numbers:**",
             f"- Free Hailuo credits: **{c['free_credits_left']} of {c['free_credits_total']}** left",
             f"- Cheapest clip: **{c['cheapest_clip_credits']} credits** — the free balance "
             "cannot generate even one clip",
             f"- Paid route, if chosen: {c['api_cost_per_kept_clip_usd']} per kept clip (API-first)",
             f"- Spent on generation to date: **${c['spent_usd']}**",
             f"- Production-route decision: **{c['route_decision']}**",
             f"\n({c['checked']}) Nothing generates until that decision lands — see `next`."]
    return "\n".join(lines)


def fmt_review(s: dict, ctx: dict) -> str:
    rg = s.get("review_gate")
    if not rg:
        return ("**Review gate** — structured gate data is not in this snapshot. What the "
                "snapshot does record: both H3 test clips carry human PASS verdicts, the "
                "clipping lane has never posted, and earned is $0. Nothing posts unreviewed.")
    lines = ["**Review gate — the human stays in the loop:**",
             f"- Human review required before anything posts: "
             f"**{'YES' if rg['human_review_required'] else 'no'}**",
             f"- H3 test clips: {rg['h3_test_clips']}",
             f"- Clipping samples: {rg['clipping_samples']}",
             f"- Posted, ever: **{'yes' if rg['posted_ever'] else 'NO — never posted'}** · "
             f"Earned: **${rg['earned_usd']}**"]
    for gate in rg["gates"]:
        lines.append(f"- Gate: {gate}")
    lines.append(f"\n{rg['publishing']}")
    return "\n".join(lines)


def fmt_sources(s: dict, ctx: dict) -> str:
    lines = ["**Sources — where every fact in my answers comes from:**",
             f"- Snapshot generated {s['generated_at_toronto']} "
             f"({s['generated_at_utc']} UTC), served via {ctx['origin']}"]
    for src in s.get("sources", []):
        lines.append(f"- {src}")
    lines.append("- The snapshot is regenerated from those files by "
                 "make_producer_snapshot.py — a file check at generation time, "
                 "never an assumption. If a section's source file is absent, the "
                 "section is omitted and the snapshot says why.")
    lines.append("- This room's two documents (Pipeline Snapshot; Pipeline State & "
                 "Review Gate) are rendered from this same snapshot — ask `status` "
                 "for their sync state.")
    return "\n".join(lines)


def fmt_health(s: dict, ctx: dict) -> str:
    up = (datetime.now(TZ) - RUNTIME["started_at"]).total_seconds() / 60
    docs = ctx["docs"]
    age = ctx["age_minutes"]
    lines = ["**Health — Producer Agent self-check:**",
             f"- Process: up {up:.0f} min (service switch-producer-agent, systemd)",
             f"- Event poll: last OK {RUNTIME['last_poll_ok'] or 'not yet'} · "
             f"errors this run: {RUNTIME['poll_errors']} · answers given: {RUNTIME['answers']}",
             f"- Snapshot: {ctx['generated_at']} via {ctx['origin']}"
             + (f", {age:.0f} min old" if age is not None else "")
             + (" — WITHIN freshness threshold" if age is not None and age <= STALE_AFTER_MINUTES
                else " — STALE (banner shown on answers)"),
             f"- Last-good cache: {STORE.last_good_at or 'not yet written this run'}",
             f"- Room documents: {'enabled' if docs['enabled'] else 'DISABLED (stack env missing)'}"
             f" · {docs['documents']} published · last sync {docs['last_sync_toronto']}"
             f" · last change {docs['last_change_toronto']}"
             + (f" · visibility {docs['visibility']}" if docs["visibility"] else "")
             + (f" · last error: {docs['last_error']}" if docs["last_error"] else " · no errors"),
             "\nIf the snapshot is ever unavailable I answer that plainly instead of "
             "inventing state — try me during an outage and check."]
    return "\n".join(lines)


HELP = ("**Producer Agent — Creator Room.** I report the media pipeline's true state. Ask me:\n"
        "- `status` — the whole pipeline on one screen\n"
        "- `ideas` — the H3 prompt-pack queue + the lane-2 pilot slate\n"
        "- `script` — script template state (and the honest episode count)\n"
        "- `renders` — the clips that exist on disk + generation state\n"
        "- `clips` — the clipping lane's true state, labelled with its date\n"
        "- `credits` — the true credit numbers + the pending route decision\n"
        "- `review` — the human review gate (nothing posts unreviewed)\n"
        "- `sources` — where every fact I report comes from\n"
        "- `next` — the honest next action\n"
        "- `health` — my own self-check: uptime, snapshot freshness, room documents\n"
        "I answer from a labelled snapshot of real files, and I publish that same "
        "snapshot as a document in this room. Where the pipeline is waiting, I say so.")


# ---------------------------------------------------------------------------
# Intent routing. First match wins — order is deliberate: the specific
# v2 intents are checked before the broader v1 keywords so e.g. a
# question about the review gate never lands on `renders`.
# ---------------------------------------------------------------------------
INTENT_ROUTES: list[tuple[str, set[str], object]] = [
    ("health", {"health", "alive", "uptime", "selfcheck"}, fmt_health),
    ("status", {"status", "overview", "summary"}, fmt_status),
    ("credits", {"credits", "credit", "hailuo", "cost", "costs", "price",
                 "spend", "budget"}, fmt_credits),
    ("review", {"review", "gate", "gates", "approval", "approve", "approved",
                "publish", "publishing"}, fmt_review),
    ("sources", {"sources", "source", "provenance", "verify"}, fmt_sources),
    ("ideas", {"ideas", "idea", "queue", "prompts", "prompt"}, fmt_ideas),
    ("script", {"script", "scripts", "episode", "template"}, fmt_script),
    ("renders", {"renders", "render", "generated", "generation"}, fmt_renders),
    ("clips", {"clips", "clip", "clipping", "clipper"}, fmt_clips),
    ("next", {"next", "blocked", "waiting"}, fmt_next),
    ("help", {"help", "commands"}, None),
]


def intent(body: str) -> str | None:
    m = (body.lower().replace("@producer", " ").replace("@ops-agent", " ")
         .replace("@watch-agent", " "))
    for ch in "!?.,;:-":
        m = m.replace(ch, " ")
    words = set(m.split())
    for name, keywords, _fn in INTENT_ROUTES:
        if words & keywords:
            return name
    return None


FORMATTERS = {name: fn for name, _kw, fn in INTENT_ROUTES if fn is not None}

UNAVAILABLE = ("**Producer Agent — snapshot unavailable.** The snapshot file cannot be "
               "read and no last-good cache exists, so I have no state to report and I "
               "will not invent any. The pipeline's last recorded state is in this "
               "room's documents and in producer-snapshot.json once it is restored.")


def answer(kind: str) -> str:
    view = STORE.load()
    if view is None:
        return UNAVAILABLE
    s = view["data"]
    ctx = {"origin": view["origin"], "generated_at": view["generated_at"],
           "age_minutes": view["age_minutes"], "docs": PUBLISHER.state}
    fn = FORMATTERS.get(kind)
    text = (fn(s, ctx) if fn is not None else HELP)
    banner = ""
    if view["origin"] != "fresh":
        banner = (f"⚠ **Serving the last-known snapshot** (from the {view['origin']}) — "
                  "the live snapshot file is unavailable right now.\n\n")
    elif view["age_minutes"] is not None and view["age_minutes"] > STALE_AFTER_MINUTES:
        banner = (f"⚠ **Stale snapshot** — this data is {view['age_minutes']:.0f} minutes "
                  f"old (generated {view['generated_at']}); the pipeline's state may have "
                  "moved since.\n\n")
    label = (f"\n\n— Producer Agent · snapshot {view['generated_at']} "
             f"(via {view['origin']}; data age is labelled, never hidden)")
    return banner + text + label


def main() -> None:
    print(f"[{datetime.now(TZ):%H:%M:%S}] producer v2 starting; room {ROOM_ID}", flush=True)
    try:
        api("POST", f"/agents/{AGENT_ID}/status", {"status": "online"}, timeout=10)
        print("status set online", flush=True)
    except Exception as e:
        print(f"status note: {e}", flush=True)
    seen: deque[str] = deque(maxlen=500)
    last_sync_attempt = 0.0
    while True:
        # Document-sync beat: at most once a minute, PATCH only on change.
        if time.time() - last_sync_attempt > 60:
            last_sync_attempt = time.time()
            view = STORE.load()
            if view is not None:
                state = PUBLISHER.sync(view["data"],
                                       datetime.now(TZ).strftime("%Y-%m-%d %H:%M Toronto"))
                if state["last_error"]:
                    print(f"doc sync: {state['last_error']}", flush=True)
        try:
            resp = api("GET", f"/agents/{AGENT_ID}/events?timeout=20&rooms={ROOM_ID}", timeout=30)
            RUNTIME["last_poll_ok"] = datetime.now(TZ).strftime("%H:%M:%S")
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
                RUNTIME["answers"] += 1
                print(f"[{datetime.now(TZ):%H:%M:%S}] answered {kind}", flush=True)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            RUNTIME["poll_errors"] += 1
            print(f"poll error: {e}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
