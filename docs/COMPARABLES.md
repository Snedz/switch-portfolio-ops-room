# Comparables sweep — Creator Room / Producer Agent (Flip the Switch, Track 02)

Swept 2026-11-07 (~22:15 ET) via the GitHub connector (`search_repositories`,
`search_code`, `get_file_contents`) plus web search. **Every licence below was
verified from the repo's own `LICENSE` file** fetched through the connector —
not from badges, roundups, or memory.

Licence rule applied throughout:

- **MIT / Apache-2.0 / BSD / Unlicense = buildable-on** (borrow patterns and,
  where useful, code, with attribution).
- **AGPL / GPL = hosted-only / reference** (read for ideas; do not copy code
  into this MIT-licensed repo).
- **Non-commercial, Commons Clause, or no licence = out** for code borrowing
  (reference only, and never sell as a service).

Our build context: a deterministic, no-LLM Producer Agent on self-hosted
Switch — registered via `POST /agents`, long-polls `GET /agents/{id}/events`,
answers via `POST /agents/{id}/message` into a Mattermost-bridged room, and
reports a media pipeline's true state from a JSON snapshot. New work: room
documents holding the snapshot/state, a snapshot fallback chain, a health
self-check, and a snapshot-refresh timer.

---

## 1. Switch / room agents

### SandboxAQ Switch — `sandbox-quantum/switch`
- URL: https://github.com/sandbox-quantum/switch
- What it does: The platform we run on. Turns Slack / Teams / Discord /
  Telegram / Mattermost channels into shared "rooms" where humans and agents
  work from the same context, documents, and history. Self-hosted, any agent,
  any model.
- **LICENCE: Apache-2.0 + Commons Clause (modified)** — verified from the
  repo `LICENSE` file ("licensed to you under the Apache 2.0 License as
  limited by the 'Commons Clause' license condition", extended to
  derivatives) and its README badge ("Apache 2.0 + Commons Clause").
  This is **not** plain Apache-2.0: the Commons Clause removes the right to
  sell the software as a service.
- Borrow-notes — **host/reference, self-host use only; do not borrow to sell:**
  This is the single most relevant comparable, because **room documents are a
  real, implemented Switch feature**, found via `search_code`:
  - `core/switch_core/gateway/documents.py` — a gateway layer returning
    `RoomDocumentSummary` objects, with a per-principal `can_remove` flag
    derived from room participation (documents are permission-aware, not
    free-for-all files).
  - Migration `f2a5b6c7d8e9_room_scoped_documents.py` — documents are
    **room-scoped with a unique `(room_id, name)` index**: one canonical
    document per name per room. That is exactly the shape for an agent-owned
    `producer-snapshot` document: update-in-place, never duplicate.
  - `docs/official/resources/room-commands.md` — rooms expose their internal
    documents to members via room commands (e.g. `!list-documents`), so a
    status document is discoverable from inside the room, not a side channel.
  - Pattern to remix (as *usage* of the platform we already self-host, not
    copied code): agent owns one named room document per state surface;
    every update replaces that document; read permission follows room
    membership. Our Producer Agent should publish its snapshot as a room
    document first, and treat the local JSON file as the fallback (below).

## 2. Mattermost bot frameworks / intent routing

### mmpy_bot — `attzonko/mmpy_bot`
- URL: https://github.com/attzonko/mmpy_bot
- What it does: Python chatbot framework for Mattermost (WebSocket API v4):
  plugin mechanism, concurrent message handling, integrated webhook server,
  job scheduling, and auto-reconnect after connection loss (README, verified
  via connector).
- **LICENCE: MIT** — verified from the repo `LICENSE` file.
- Borrow-notes — **buildable-on:** the cleanest model for our intent layer.
  One plugin/handler per intent, registered declaratively, instead of one
  monolithic matcher; built-in **job scheduling** (maps to our
  snapshot-refresh timer); and **auto-reconnect with backoff** — translate
  that pattern from WebSocket to our Switch long-poll loop: a failed
  `GET /agents/{id}/events` never kills the agent, it backs off and resumes.
  We keep our stdlib-only, no-dependency stance, so borrow the *structure*
  (handler registry + scheduler + reconnect), not the package itself.

### MatterBot — `uforia/MatterBot`
- URL: https://github.com/uforia/MatterBot
- What it does: Two-part extensible Python Mattermost bot: a **scheduled
  feed** pushing information sources into channels on a schedule, plus a
  listener that routes channel commands to modules.
- **LICENCE: GPL-3.0** — verified from the repo `LICENSE` file (GNU GPL v3).
- Borrow-notes — **reference only, do not borrow code** (GPL code cannot be
  copied into this MIT repo). The *idea* is directly relevant and is ours to
  reimplement: split the agent into (a) a scheduled publisher that refreshes
  state into the room unprompted, and (b) a command listener that answers
  from that state. That is precisely our refresh-timer + on-demand-answer
  split.

## 3. AI clipping / shorts pipelines

### MoneyPrinterTurbo — `harry0703/MoneyPrinterTurbo`
- URL: https://github.com/harry0703/MoneyPrinterTurbo
- What it does: Topic/keyword → finished short video: LLM script, stock
  footage matching, TTS voiceover, burned-in subtitles, music, rendered with
  ffmpeg/MoviePy (vertical 1080×1920 supported); web UI + API + Docker.
- **LICENCE: MIT** — verified from the repo `LICENSE` file.
- Borrow-notes — **buildable-on:** borrow its **staged task-state model** —
  the pipeline is a sequence of discrete, inspectable stages
  (script → material → voice → subtitle → render), each with its own state.
  That is the right shape for our clipping-lane snapshot: report per-stage
  truth ("samples built, never posted, $0 earned") instead of one opaque
  status. Caution: do **not** vendor its bundled assets — an independent
  audit (Oct 2026) found most of the repo's bytes are proprietary
  fonts/music; the MIT licence covers the code, not those assets.

### ShortGPT — `RayVentura/ShortGPT`
- URL: https://github.com/RayVentura/ShortGPT
- What it does: Short-form video automation framework: a declarative
  "editing engine" that composes ffmpeg operations, Whisper-based
  captioning, and asset sourcing into repeatable short pipelines.
- **LICENCE: MIT** — verified from the repo `LICENSE` file.
- Borrow-notes — **buildable-on:** the editing-engine abstraction —
  editing steps as composable, named operations over a timeline — is a clean
  deterministic core for a clipper (no LLM needed for the edit itself).
  Its captioning flow (Whisper timestamps → styled caption segments) is the
  pattern to remix for 9:16 captioned clips.

### AI-Youtube-Shorts-Generator — `Anil-matcha/AI-Youtube-Shorts-Generator` (formerly SamurAIGPT)
- URL: https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator
- What it does: Long video → shorts: yt-dlp download, Whisper transcription,
  highlight-segment selection, ffmpeg vertical crop + captions.
- **LICENCE: MIT** — verified from the repo `LICENSE` file fetched today.
  (Note: some Nov 2026 third-party roundups listed this repo as having *no*
  licence; the direct `LICENSE` check supersedes them.)
- Borrow-notes — **buildable-on:** the end-to-end slicing flow is the
  reference shape for our clipping lane. Borrow the deterministic half —
  transcript segments → candidate windows → 9:16 crop → captioned render —
  and skip its LLM highlight picking, which conflicts with our no-LLM rule;
  our segment choice stays rule/time-based and labelled as such.

### short-video-maker — `gyoridavid/short-video-maker`
- URL: https://github.com/gyoridavid/short-video-maker
- What it does: Small service that makes short videos (TTS + Whisper
  captions + Remotion/ffmpeg rendering) exposed as a REST API and an MCP
  server.
- **LICENCE: MIT** — verified from the repo `LICENSE` file.
- Borrow-notes — **buildable-on:** the packaging pattern — a media pipeline
  wrapped as a small, deterministic service with explicit endpoints — is
  how our snapshot producer already works (`make_producer_snapshot.py` as a
  separate producer, the agent as a separate reporter). Confirms keeping
  generation and reporting as separate processes with a file/document
  contract between them.

### MoneyPrinterV2 — `FujiwaraChoki/MoneyPrinterV2`
- URL: https://github.com/FujiwaraChoki/MoneyPrinterV2
- What it does: Successor-line MoneyPrinter: generates and uploads shorts
  (YouTube/Twitter), with its own money-printer pipeline structure.
- **LICENCE: AGPL-3.0** — verified from the repo `LICENSE` file (GNU AGPL v3).
- Borrow-notes — **hosted-only / reference only, do not borrow code.**
  Useful only as a read on upload-automation structure; AGPL network-use
  terms are incompatible with quietly remixing it into this MIT repo.

### youtube-clipping — `Risingtides-dev/youtube-clipping`
- URL: https://github.com/Risingtides-dev/youtube-clipping
- What it does: Self-described "closed-loop YouTube Shorts clipping
  operation: source → AI-clip → Slack QC → score → double down", owning the
  whole yt-dlp/Whisper/ffmpeg stack with no app dependency.
- **LICENCE: none found** — no `LICENSE` file in the repo (connector fetch
  failed: file does not exist). Under the sweep rule: **out**.
- Borrow-notes — **do not borrow code.** The *loop idea* (clip → human QC in
  chat → score → make more of what scored) is a workflow concept, not code;
  if we ever want it, we design it ourselves and label the QC step as the
  human gate it is. Nothing is taken from this repo.

### yt-dlp — `yt-dlp/yt-dlp` · Whisper — `openai/whisper` (pipeline primitives)
- URLs: https://github.com/yt-dlp/yt-dlp · https://github.com/openai/whisper
- What they do: yt-dlp is the standard source-acquisition tool for the
  clipping lane; Whisper provides transcription with segment/word
  timestamps that drive caption placement.
- **LICENCES: yt-dlp — Unlicense (public domain dedication); Whisper — MIT**
  — both verified from their repo `LICENSE` files.
- Borrow-notes — **buildable-on:** use both as external tools/libraries
  (never vendored forks). Whisper's timestamped segments are the contract
  our snapshot should record for a clip (source, segment in/out, caption
  status), so the room can report a clip's provenance, not just its file
  name.

## 4. Status-document / snapshot-projection / health patterns

### Upptime — `upptime/upptime`
- URL: https://github.com/upptime/upptime
- What it does: Uptime monitor + status page powered entirely by GitHub
  Actions: scheduled checks write their results back as commits, a
  generated summary/status artefact, and a response-time history — the
  repo itself is the living status document.
- **LICENCE: MIT** — verified from the repo `LICENSE` file.
- Borrow-notes — **buildable-on:** the best snapshot-projection pattern in
  the sweep. Three transferable rules: (1) a **timer, not a request,**
  regenerates the status artefact, so it is fresh even when nobody asks;
  (2) the artefact is **generated from raw check data every run** — never
  hand-edited — so it cannot drift from reality; (3) **history is kept**
  alongside the current state, so "when did this change?" is answerable.
  Translated to our build: the refresh timer regenerates
  `producer-snapshot.json`, the agent projects it into the room document,
  and every answer carries the snapshot's generation time and staleness.

### Uptime Kuma — `louislam/uptime-kuma`
- URL: https://github.com/louislam/uptime-kuma
- What it does: Self-hosted monitoring: per-monitor heartbeat intervals,
  down/recovery notifications, and a public status page that is purely a
  projection of monitor state.
- **LICENCE: MIT** — verified from the repo `LICENSE` file.
- Borrow-notes — **buildable-on (pattern):** the health self-check shape —
  each component has an expected heartbeat cadence; missed beats flip its
  displayed state to DOWN after a threshold, and recovery flips it back,
  with both transitions announced. Our agent's `health` answer should work
  the same way: snapshot age vs. refresh cadence is the heartbeat; past
  threshold, the honest answer is "degraded — snapshot is N minutes old",
  never a fresh-sounding answer from stale data.

### Healthchecks — `healthchecks/healthchecks`
- URL: https://github.com/healthchecks/healthchecks
- What it does: Cron/job monitoring as a dead-man's switch: a job pings a
  unique URL on success; if the ping does not arrive inside its grace
  period, Healthchecks alerts — silence itself is the failure signal.
- **LICENCE: BSD-3-Clause** — verified from the repo `LICENSE` file
  (permissive; same buildable-on class as MIT/Apache under our rule).
- Borrow-notes — **buildable-on (pattern):** invert the health check. Our
  snapshot-refresh timer should *signal on success only*; the agent's
  health self-check then asks "when was the last successful refresh?"
  rather than "is the refresher running?" — a hung or dead refresher is
  detected by absence, which is exactly the failure mode a naive
  process-alive check misses.

---

## Borrowed into this build

The 4 patterns we judge most valuable for a deterministic room agent with
room documents + a fallback chain + a health check, in priority order:

1. **Switch room documents as the primary state surface** (Switch,
   Apache-2.0 + Commons Clause — self-host use, not code borrowing):
   one agent-owned document per room, unique by `(room_id, name)`,
   updated in place, permissions following room membership. The Producer
   Agent publishes its snapshot as the room's `producer-snapshot` document.
   **Fallback chain:** room document → local `producer-snapshot.json` →
   `clipping-state.json` for the clipping lane → an explicit "not in this
   snapshot — I won't guess" refusal. Every answer labels which rung it
   came from and the snapshot's generation time.

2. **Upptime-style timer-driven snapshot projection** (Upptime, MIT):
   the snapshot is regenerated by the refresh timer from raw on-disk
   state — never edited, never answered from memory — with prior state
   retained so changes are visible. Freshness is a property of the
   artefact (its timestamp), not of the agent's confidence.
   *(Tonight's exact state: the timer unit ships in this repo NOT
   enabled — refresh is one manual command until the generator's
   sources move to the box. See docs/ARCHITECTURE.md.)*

3. **Dead-man health check** (Healthchecks, BSD-3-Clause + Uptime Kuma,
   MIT): the refresh job signals on success only; the agent's health
   self-check compares last-success against the refresh cadence and
   reports **degraded/stale** past threshold instead of serving stale
   state as current. Silence = failure, by design.

4. **Plugin-per-intent dispatch + poll resilience** (mmpy_bot, MIT;
   scheduled-feed/command split concept from MatterBot, GPL — reimplemented,
   not copied): one small handler per intent keyword set, a system-sender
   denylist so room agents never answer each other, and an auto-reconnect /
   backoff loop around the Switch event long-poll so a dropped poll is a
   pause, not a death. Supporting pattern for the clipping lane itself:
   MoneyPrinterTurbo's (MIT) staged task-state, so the snapshot reports
   per-stage truth rather than a single opaque status.
