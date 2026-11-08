# Creator Room — live evidence (Flip the Switch, Track 02)

**Deployment:** self-hosted Switch stack on 67-build-1 — same deployment as the Portfolio Ops Room.
**Room:** "Creator Room" (Switch room 4a6a7391-acd0-46fd-bb29-deaeac62faf0), bridged to Mattermost channel `creator-room-7e61d709`.
**Agent:** `producer` (Producer Agent, id 1bb4dc8c-359b-4ae5-91c5-0309bf5a21fe), registered through the Switch agent API, running as systemd service `switch-producer-agent.service` (active since 21:37 ET, Sat Nov 7, 2026).
**Live test:** Sat Nov 7, 2026, 21:40:58–21:41:09 EST — six questions asked as a human user in the channel; six answers published by the Switch bridge, each in ~2 seconds (service journal: `answered ideas/next/script/renders/clips/help`). Snapshot: generated 2026-11-07 21:36 Toronto from real files on the fleet VM; every answer carries that label.

Notes on the transcript below: Switch's identity guard precedes each answer with its owner notice (the asking chat account isn't linked to a Switch user) — the same behaviour the ops room showed; the agent's answer follows it. The Producer reports state only: it does not generate, post, or clip anything, and its answers never claim otherwise.

---

## (i) Backlog answer — real titles (`@producer ideas`, 21:40:58 EST)

**Ideas — the H3 animated-shorts queue** (prompt pack v1 on file, v1.2 grammar addendum on file):
- §1 **POD explainer test clip (how print-on-demand works)** — done — generated Oct 29, passed review (see renders)
- §2 **BeforeChristmas product clip** — queued — prompt written; needs a hero product picked and a production route before it can be generated
- §3 **Faceless animated explainer segment (espresso machine)** — queued — prompt written; 4 segments make one short; not generated

**Lane 2 — owned animated shorts (the studio lane):** pilot is job-carded (JOB-h3-lane2-pilot), UNSTARTED.
- reef detail test (specced, unrun — blocked on credits/route)
- one owned explainer short, one-failure-one-fix format (not scripted)
Also blocked on: studio working name — founder decision; nothing publishes without one.

Honest summary: the ideas are written and specced. None of the queued ones has been generated — see `renders` for why.

— Producer Agent · snapshot 2026-11-07 21:36 Toronto (data age is labelled, never hidden)

## (ii) What's stuck and why — the producer moment (`@producer next`, 21:41:00 EST)

**Next — the honest next action:**
The pipeline is mostly WAITING, and the wait has one name: the founder's production-route decision (API-first, ~$2.60–3.90 per kept clip). That single decision unblocks H3 generation — the BeforeChristmas clip, the faceless explainer, and the lane-2 pilot (reef test + first owned short).

**Also waiting, in the open:**
- Hero product pick for the BeforeChristmas clip
- Studio working name (publishing gate for lane 2)
- Episode 1 script — the template is ready, the script is not written
- Clipper revival needs a campaign pick (Whop account + campaign join are still todo; nothing has ever been posted; earned $0)

Nothing on this list is hidden work the fleet forgot — it is a short queue behind one founder decision, and this room exists so that stays visible.

— Producer Agent · snapshot 2026-11-07 21:36 Toronto (data age is labelled, never hidden)

## (iii) Script status for the named pilot (`@producer script`, 21:41:02 EST)

**Scripts — where the writing actually stands:**
- Template: READY — Virex-format explainer template (one failure → one fix → one visual beat; 5–7 beats + bookend close)
- Episode scripts: **NO episode script exists. The template is ready; nobody has written episode 1 yet.**

So `script` today means: the shape of episode 1 is fully specified (cold open mid-failure, 5–7 one-failure-one-fix beats, bookend close, ≤2 short narration sentences per beat) and the writing itself has not started.

— Producer Agent · snapshot 2026-11-07 21:36 Toronto (data age is labelled, never hidden)

## Also verified live (same test run)

- `@producer renders` (21:41:04): both real clips reported from os.stat — `h3-test-clip-01-pod-explainer.mp4` 8.17 MB and `h3-test-clip-02-buttons-text.mp4` 0.76 MB, both PASS (Oct 29); **Generation: BLOCKED** — free Hailuo credits 2 of 150 left, cheapest clip 28; assembly proven Oct 31 (MoneyPrinterTurbo draft render + subtitle tool), stated as a pipeline test, not a publishable asset.
- `@producer clips` (21:41:06): clipping lane state labelled as of 2026-10-16 — pipeline done on samples, **posted: NO — never posted**, **earned $0**, payout not set, revival needs a campaign pick.
- `@producer help` (21:41:08): the five intents, with the standing line "Where the pipeline is waiting, I say so."

Full transcript: demo-out-producer/transcript.md on 67-build-1 (/root/creator-room/).
