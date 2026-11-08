# Creator Room — Architecture

The Creator Room is the second room on Program 67's self-hosted Switch
deployment (the first is the Portfolio Ops Room). A deterministic
Producer Agent reports the founder's real media pipeline — the H3
animated-shorts lane and the AI clipping lane — from a labelled
snapshot of real files. It never generates, posts, publishes, or
spends; it reports state, including (especially) what is blocked.

## Components

```
  fleet VM (sources)                     67-build-1 (Switch host)
 ┌───────────────────┐                  ┌──────────────────────────────────┐
 │ H3 goal files     │  make_producer_  │  Producer Agent (systemd)        │
 │ clipping STATE    │  snapshot.py     │   producer_agent.py              │
 │ (via connector)   │ ───────────────► │    ├─ SnapshotStore (fallback)   │
 └───────────────────┘  refresh-        │    ├─ INTENT_ROUTES (11 intents) │
        ▲               producer-       │    └─ DocumentPublisher ──────┐  │
        │               snapshot.sh     │         ▲ events (long-poll)  │  │
        │               (manual today)  │         │ answers (agent API) │  │
        │                               │  Switch gateway ──────────────┘  │
        │                               │    ├─ agent API  (:8000/agents)  │
        │                               │    ├─ documents API (gateway)    │
        │                               │    └─ Mattermost bridge ──► #creator-room
        │                               └──────────────────────────────────┘
        └── sources are file checks at generation time — never assumptions
```

| Piece | File | Role |
|---|---|---|
| Producer Agent | `producer_agent.py` | Long-polls its Switch event stream, routes intents, answers from the snapshot, drives the document-sync beat. |
| Room documents | `room_documents.py` | Renders the snapshot + state/review-gate documents; get-or-create, attach, PATCH-on-change via the gateway documents API. |
| Snapshot generator | `make_producer_snapshot.py` | Builds `producer-snapshot.json` from real file checks on the fleet VM (prompt pack, template, mp4 `os.stat`, assembly proof, clipping state). Refuses to write if its source dir is absent. |
| Refresh (manual) | `refresh-producer-snapshot.sh` | The producer's own one-command refresh (regenerate + copy to the box). Independent of the ops room's `refresh-snapshot.sh`. |
| Smoke test | `scripts/smoke_producer.py` | Asks every intent in the live room and verifies labelled answers. |
| Unit tests | `test_producer.py` | Routing, truthfulness invariants, fallback chain, document renderers. |
| Provisioning | `setup_producer.py` | Get-or-create: agent registration, channel, bridge, room, env file. |

## Why room documents go through the gateway

Switch's agent API (checked against the live OpenAPI spec on the
deployment: 41 paths) has **no document endpoints**. Documents live on
the gateway API (`POST /gateway/documents`, `POST
/gateway/rooms/{id}/documents/{doc_id}`, `PATCH /gateway/documents/{id}`).
The publisher therefore uses a gateway session with the deployment's
stack credentials — the same pattern `setup_producer.py` already uses —
and the documents are owned by the console admin account, attached to
the Creator Room, with content signed as the Producer's. Document
sync is best-effort: any failure is recorded and surfaced by the
`health` intent, and never interrupts answering.

## Data flow

1. **Snapshot.** The generator stats real files on the fleet VM and
   writes a JSON snapshot labelled with its generation time. The
   snapshot is the agent's *only* source of facts.
2. **Answering.** For every question the agent re-reads the snapshot
   (via the fallback chain, below), formats a deterministic answer,
   and appends the snapshot timestamp. Age > 30 min prepends a
   staleness banner.
3. **Documents.** Once a minute the agent re-renders the two room
   documents from the current snapshot and PATCHes any whose content
   hash changed — so a state change shows up in the document and in
   the next answer with the same timestamp (the change-and-re-ask
   beat).
4. **Change-and-re-ask.** Refresh the snapshot
   (`refresh-producer-snapshot.sh`) → documents update → ask `@producer
   status` → the answer and the document carry the new snapshot time.

## Failure modes & the fallback chain

| Failure | Behaviour |
|---|---|
| Snapshot file missing/corrupt | Serve the **last-good cache** (written on every successful read) with a loud banner naming its origin and time. |
| No snapshot and no cache | Answer the explicit **"snapshot unavailable"** text. Numbers are never reconstructed from memory. |
| Snapshot stale (> 30 min) | Answers continue, with a **staleness banner** stating the data's age in minutes. |
| Gateway/documents down | Answers continue; the failure is recorded and reported verbatim by `health`. |
| Generator run on a host without sources | **Refuses** (exit 2) rather than emitting a snapshot that falsely reports everything missing. |
| Switch event stream errors | Poll loop logs, backs off 3 s, keeps polling; the error count is visible in `health`. |
| Producer service dies | systemd `Restart=always`; the Ops and Watch agents are separate services and are unaffected. |

Isolation rule, kept throughout the build: the producer's code, env,
snapshot, refresh script, and service are its own. The ops room's
agent, watcher, digest timer, and refresh path are never modified by
anything in the Creator Room lane.

## Snapshot refresh — current truth and next step

Tonight the snapshot refreshes by one manual command
(`refresh-producer-snapshot.sh`, run from the fleet VM). It is **not**
on an automatic schedule yet, and the agent's answers stay honest
about that: every answer carries the snapshot's generation time and
the staleness banner fires automatically.

`switch-producer-snapshot.service` / `.timer` ship in this repo
**not installed and not enabled**. The generator's sources live on the
fleet VM, so enabling a box-side timer today would regenerate from
nothing; the generator's refusal guard makes that fail safe (clear
log line, no false snapshot), but the correct next step is to move
the generator's small text sources to the box first, then enable the
timer (15 min cadence, its own unit — never the ops refresh path).

## Review notes

- Deterministic by design: no LLM anywhere in this lane, so every
  answer is reproducible from the snapshot on disk.
- The truthfulness invariants are pinned by tests
  (`test_producer.py`): credits are 2 of 150 with a 28-credit cheapest
  clip, the clipper has never posted, earned is $0, and the route
  decision is the founder's.
- The v1 → v2 diff a reviewer wants: intents 6 → 11 (`status`,
  `credits`, `review`, `sources`, `health`), the snapshot fallback
  chain, room documents, and the refresh fail-safe.
