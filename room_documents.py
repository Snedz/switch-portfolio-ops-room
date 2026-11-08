#!/usr/bin/env python3
"""Room Documents publisher for the Creator Room.

Switch's agent API (verified against the live OpenAPI spec on
67-build-1: 41 paths) exposes NO document endpoints — documents live on
the Switch gateway API:

    POST  /gateway/documents                              create
    POST  /gateway/rooms/{room_id}/documents/{doc_id}     attach to room
    PATCH /gateway/documents/{doc_id}                     update content
    GET   /gateway/rooms/{room_id}/documents              list room docs

So the Producer publishes its room documents through a gateway session
(same credential pattern as setup_producer.py: the deployment stack
env, read at runtime, never printed, never stored in this repo). The
documents are owned by the deployment's console admin account and
attached to the Creator Room; their content is rendered from the same
snapshot the agent answers from, and signed as the Producer's.

Two documents:
  1. "Creator Room — Pipeline Snapshot" — the snapshot, rendered:
     generation state, credits, queue, next action.
  2. "Creator Room — Pipeline State & Review Gate" — the clipping
     lane's dated state + the human review gate (nothing posts without
     the founder; the Producer reports state only).

Sync discipline: content is re-rendered from the current snapshot on
every poll cycle; a PATCH is issued only when the content hash actually
changed. That is the change-and-re-ask beat: state changes -> document
updates -> the agent's next answer (and the document) show the new
state, with the same snapshot timestamp on both.

Failure discipline: publishing is best-effort and NEVER blocks or
breaks answering. Every failure is recorded in the sync state, which
the agent's `health` intent reports verbatim.
"""
import hashlib
import json
import urllib.error
import urllib.request
from http import cookiejar
from pathlib import Path

DOC_SNAPSHOT = "Creator Room — Pipeline Snapshot"
DOC_STATE = "Creator Room — Pipeline State & Review Gate"


def render_snapshot_document(s: dict) -> str:
    """Render document 1 from a snapshot dict (pure function)."""
    g = s["renders"]["generation"]
    c = s.get("credits") or {}
    lines = [
        f"# Creator Room — Pipeline Snapshot",
        "",
        f"**Snapshot generated:** {s['generated_at_toronto']} "
        f"({s['generated_at_utc']} UTC)",
        "**Maintained by:** Producer Agent (deterministic, no LLM) — "
        "re-rendered from the live snapshot whenever the snapshot changes.",
        "",
        "## Generation",
        f"- State: **{g['state']}** — {g['why']}",
        f"- Unblocks with: {g['unblocks_with']}",
    ]
    if c:
        lines.append(f"- Free Hailuo credits: **{c['free_credits_left']} of "
                     f"{c['free_credits_total']}** left; cheapest clip costs "
                     f"{c['cheapest_clip_credits']} — generation cannot run on "
                     f"free credits. Route decision: {c['route_decision']}.")
    lines += ["", "## Ideas queue"]
    for it in s["ideas"]["items"]:
        lines.append(f"- §{it['n']} **{it['title']}** — {it['state']}")
    p = s["ideas"]["lane2_pilot"]
    lines.append(f"- Lane 2 pilot: {p['state']} (also blocked on: {p['also_blocked_on']})")
    lines += ["", "## Renders on disk"]
    for clip in s["renders"]["clips"]:
        st = clip["stat"]
        if st:
            lines.append(f"- `{clip['file']}` — {st['size_mb']} MB, on disk since "
                         f"{st['modified_toronto']} — {clip['verdict']}")
        else:
            lines.append(f"- `{clip['file']}` — NOT FOUND on disk in this snapshot")
    lines += ["", "## Next", s["next"]["honest_next_action"]]
    return "\n".join(lines)


def render_state_document(s: dict) -> str:
    """Render document 2 (clipping state + review gate) from a snapshot."""
    lines = ["# Creator Room — Pipeline State & Review Gate", "",
             f"**Snapshot generated:** {s['generated_at_toronto']}",
             "**Maintained by:** Producer Agent — same snapshot the agent answers from.",
             "", "## Human review gate"]
    rg = s.get("review_gate") or {}
    if rg:
        lines.append(f"- Human review required before anything posts: "
                     f"**{'YES' if rg['human_review_required'] else 'no'}**")
        lines.append(f"- H3 test clips: {rg['h3_test_clips']}")
        lines.append(f"- Clipping samples: {rg['clipping_samples']}")
        lines.append(f"- Posted, ever: **{'yes' if rg['posted_ever'] else 'NO'}** · "
                     f"Earned: **${rg['earned_usd']}**")
        for gate in rg["gates"]:
            lines.append(f"- Gate: {gate}")
        lines.append(f"- {rg['publishing']}")
    c = s.get("clipping")
    lines += ["", "## Clipping lane (dated state)"]
    if c:
        lines.append(f"- As of: {c['updated']} (source: {c['source']})")
        lines.append(f"- Pipeline: {c['pipeline_status']} — {c['pipeline_note']}")
        lines.append(f"- Samples: {c['samples_status']}; posted: "
                     f"**{'yes' if c['samples_posted'] else 'NO — never posted'}**; "
                     f"earned: **${c['earned_usd']}**")
        lines.append(f"- Payout method: {c['payout_method']}; accounts: {c['accounts_status']}")
        lines.append("- Open tasks: " + "; ".join(c["open_tasks"]))
    else:
        lines.append(f"- Not in this snapshot: {s.get('clipping_note') or 'state file unavailable.'}")
    return "\n".join(lines)


DOCUMENTS = [
    (DOC_SNAPSHOT,
     "The Creator Room's live pipeline snapshot, published by the Producer "
     "Agent from the same snapshot it answers questions from.",
     "Read-only state document. It is re-rendered by the Producer Agent "
     "whenever the underlying snapshot changes; the snapshot timestamp "
     "inside is the freshness label.",
     render_snapshot_document),
    (DOC_STATE,
     "The clipping lane's dated state and the human review gate for the "
     "Creator Room, published by the Producer Agent.",
     "Read-only state document. Nothing in the media pipeline posts, "
     "publishes, or spends without the founder's review; this document "
     "records that gate and the dated clipping state behind it.",
     render_state_document),
]


class DocumentPublisher:
    """Get-or-create + attach + patch-on-change for the room documents.

    Construct with the stack env path and the Switch room id. `sync()`
    is safe to call on every poll cycle: it logs in lazily, and only
    PATCHes when a rendered content hash changed since the last sync.
    All errors are caught and recorded in `self.state` — sync never
    raises into the agent loop.
    """

    def __init__(self, stack_env: Path, api: str, room_id: str):
        self.stack_env = stack_env
        self.api = api.rstrip("/")
        self.room_id = room_id
        self.opener = None
        self.doc_ids: dict[str, str] = {}
        self.hashes: dict[str, str] = {}
        self.state = {"enabled": stack_env.exists(), "logged_in": False,
                      "documents": 0, "last_sync_toronto": None,
                      "last_change_toronto": None, "last_error": None,
                      "visibility": None}
        if not self.state["enabled"]:
            self.state["last_error"] = f"stack env not found at {stack_env}"

    # -- gateway plumbing -------------------------------------------------
    def _http(self, method: str, url: str, body: dict | None = None):
        req = urllib.request.Request(url, method=method)
        data = None
        if body is not None:
            req.add_header("Content-Type", "application/json")
            data = json.dumps(body).encode()
        with self.opener.open(req, data=data, timeout=20) as r:
            return json.loads(r.read() or b"{}")

    def _login(self) -> None:
        env = {}
        for line in self.stack_env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        cj = cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj))
        self._http("POST", f"{self.api}/gateway/auth/login",
                   {"email": env["GATEWAY_ADMIN_EMAIL"],
                    "password": env["GATEWAY_ADMIN_PASSWORD"]})
        self.state["logged_in"] = True

    def _create(self, name: str, description: str, instructions: str,
                content: str) -> str:
        body = {"name": name, "description": description,
                "instructions": instructions, "content": content}
        # Prefer room-scoped visibility; fall back to the API defaults
        # (private = console-owner visible) if the enum rejects it.
        try:
            doc = self._http("POST", f"{self.api}/gateway/documents",
                             {**body, "read_visibility": "room",
                              "write_visibility": "room"})
            self.state["visibility"] = "room"
        except urllib.error.HTTPError:
            doc = self._http("POST", f"{self.api}/gateway/documents", body)
            self.state["visibility"] = "private (API default)"
        self._http("POST",
                   f"{self.api}/gateway/rooms/{self.room_id}/documents/{doc['id']}")
        return doc["id"]

    # -- the sync beat ------------------------------------------------------
    def sync(self, snapshot: dict, now_toronto: str) -> dict:
        if not self.state["enabled"]:
            return self.state
        try:
            if self.opener is None:
                self._login()
            attached = self._http(
                "GET", f"{self.api}/gateway/rooms/{self.room_id}/documents")
            by_name = {d["name"]: d["id"] for d in attached}
            changed = False
            for name, desc, instr, render in DOCUMENTS:
                content = render(snapshot)
                digest = hashlib.sha256(content.encode()).hexdigest()
                if self.hashes.get(name) == digest and name in by_name:
                    continue
                if name not in by_name:
                    self.doc_ids[name] = self._create(name, desc, instr, content)
                    changed = True
                elif self.hashes.get(name) != digest:
                    self._http("PATCH",
                               f"{self.api}/gateway/documents/{by_name[name]}",
                               {"content": content})
                    changed = True
                self.doc_ids[name] = by_name.get(name, self.doc_ids.get(name))
                self.hashes[name] = digest
            self.state["documents"] = len(self.doc_ids)
            self.state["last_sync_toronto"] = now_toronto
            if changed:
                self.state["last_change_toronto"] = now_toronto
            self.state["last_error"] = None
        except Exception as e:  # publishing must never break answering
            self.state["last_error"] = f"{type(e).__name__}: {e}"
        return self.state
