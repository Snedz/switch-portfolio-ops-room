# Portfolio Ops Room — run a 64-venture portfolio from one chat room

**Track: Best Business Workflow — Flip the Switch Hackathon (WeMakeDevs × Switch)**
**Team: Mission Winning (T3RBB9)**

A solo founder runs a 64-venture portfolio with a fleet of AI agents. The
work lives in three places: a deadline register (123 tracked commitments,
97 of them active), a watch layer that monitors the machines, and GitHub.
Checking any of them meant leaving the conversation and opening a tool.

The Portfolio Ops Room collapses that into the room where the team already
talks: ask `@ops-agent deadlines`, `gates`, `money`, `health`, `brief`,
`status`, or `prs` in the channel and the agent answers in seconds, from
real data, with the data's age labelled on every answer. And the room does
not wait to be asked: a second agent watches the fleet's monitors and
posts the moment one flips, and a portfolio digest lands in the room
twice a day on a timer.

**By the numbers** (live board, snapshot 2026-11-07 19:24 Toronto): 7
questions · answers in ~1–2 s · data snapshot never more than 5 minutes
old · 123 commitments, 64 ventures, 1 operator · 10 founder-gated actions
waiting · 25 open PRs · 6 fleet monitors (5 up, 1 genuinely DOWN) ·
$1,512.65 of real overdue money on the board.

**One real answer** — `@ops-agent brief`, live in the room at 19:00 EST,
Nov 7 (verbatim from `evidence/transcript.md`):

> **Portfolio brief** — 2026-11-07 18:58 Toronto
>
> 🔴 **Overdue (3):**
> - TELUS / Debt Control Agency collection — decision (file DG231281, $1,495.48) — 3.4d overdue
> - BeforeChristmas Etsy bill $17.17 — suspension if unpaid — 0.8d overdue
> - Wise Business verification — trading address rejected, 2-day clock — 0.5d overdue
>
> 🟠 **Due within 48h (7):**
> - Rocket Pool GMC Round 42 grant — due Sat Nov 07, 18:59
> - Flip the Switch Hackathon (WeMakeDevs × Switch, $10K) — submission — due Sat Nov 07, 23:29
> - MLH Solana Hackathon (registration confirmed) — due Sun Nov 08, 10:00
> - Vultr Agent Rush Hackathon (lablab.ai) — submissions close Nov 8 UTC — due Sun Nov 08, 18:00
> - Cosmos Institute × Inherent essay (£20K, ≤1,000 words) — submission — due Sun Nov 08, 23:59
>
> 🔑 **Top gates waiting on the founder (10 total):**
> - Decide: recognise the TELUS debt or request written validation — TELUS / Debt Control Agency collection — decision (file DG231281, $1,495.48)
> - Pay the $17.17 Etsy bill (or confirm it is already paid) — BeforeChristmas Etsy bill $17.17 — suspension if unpaid
> - Upload a trading-address proof (…) + complete phone ID verification (ID photo + selfie) — Wise Business verification — trading address rejected, 2-day clock
>
> 🩺 **Watch:** 5/6 monitors up — DOWN: site-sitebefore
> 📬 **PRs:** 25 open on MissionWinning/67
> 📋 **Board:** 97 active items (3 overdue, 4 ≤24h, 7 ≤3d, 22 ≤7d)
>
> — Ops Agent · snapshot 2026-11-07 18:58 Toronto (data age is labelled, never hidden)

Note the board carried *this hackathon's own submission deadline* — an
entry that itself nearly died of a wrongly recorded deadline (13:29 vs
the live ~23:29 close), now tracked, correctly, by the system built from
earlier losses like it.

## How Switch is used — Switch is the load-bearing piece

This project does not put a bot *next to* Switch; the agent exists only
*inside* Switch:

- **The agent is a registered Switch agent.** `setup_switch.py` registers
  `ops-agent` through the Switch agent API (`POST /agents`, authorized by
  the deployment's `AGENT_REGISTRATION_TOKEN`) and receives the agent's own
  API key. The agent has no other identity and no other way to speak.
- **The room is a Switch room.** The Switch gateway's Mattermost
  collaboration bridge (registered via `POST /gateway/collaborations`,
  set as default) auto-bridged the team's `#portfolio-ops` Mattermost
  channel into a Switch room, and the agent was placed in it
  (`agent_ids` on room create). Switch's own greeting fired when the agent
  joined: *"Hi! I'm here to help — mention @ops-agent anytime."*
- **Messages flow through Switch in both directions.** A human posts in
  Mattermost → the Switch bridge ingests it into the room → the agent
  receives it on its Switch event stream (`GET /agents/{id}/events`,
  long-poll) → the agent answers through the Switch agent API
  (`POST /agents/{id}/message`) → the bridge publishes the answer into the
  channel under the agent's Mattermost bot account.
- **Switch's trust layer is visibly on duty.** Because the demo chat
  account isn't linked to a Switch user, Switch's identity guard posts its
  "I only take instructions from my owner…" notice before the agent's
  answer — Switch mediating the conversation, not decoration around it.
- **Two agents share the room.** The Ops Agent answers questions; the
  Watch Agent (registered the same way, carrying the same owner-only
  addressing policy, added to the room through the gateway API) posts
  monitor transitions as they happen. The Ops Agent is configured to
  never answer the Watch Agent's posts or its own digests, so the room
  cannot talk itself into a loop.

Remove Switch and every link in that chain disappears: no agent registry,
no room, no bridge, no event stream, no publishing path. The remaining code
is a formatter with nobody to talk to.

```
 human ──▶ Mattermost #portfolio-ops ──▶ Switch Mattermost bridge
                                                │  (room events)
                                                ▼
                                        Switch gateway (agent API)
                                                │  GET /agents/{id}/events
                                                ▼
                                     Ops Agent service (this repo)
                                                │  reads snapshot.json
                                                ▼
                        fleet data: deadline register · watch layer · GitHub
                                                │
              answer ◀── POST /agents/{id}/message ◀──┘
        (bridge publishes it into the channel as the agent)
```

### The agent

`switch_agent.py` — a small, deterministic staff agent (Python standard
library only, systemd service). Deliberately not an LLM: a deadline board
must be exact, and every number it says is traceable to the snapshot it
read. It answers:

| Ask | Answer |
| --- | --- |
| `deadlines` | The board: active count, overdue items, due ≤24h, next five — from the real deadline register |
| `gates` | The founder-gated actions waiting (the register's `gated_by` steps: payments, submissions, identity checks), most urgent first, with each action's estimated minutes |
| `money` | Overdue payments (a $1,495.48 collection, a $17.17 Etsy bill that suspends the shop, a lapsed bank verification) + payment deadlines due in the next two weeks |
| `health` | Per-monitor watch state — every kuma-lite monitor named, UP/DOWN, and since when |
| `brief` | One compact brief: overdues + due ≤48h + top gates + watch state + PR count |
| `status` | The mutual watcher summary line: the box↔VM monitoring state (one monitor was genuinely DOWN during the demo — site-sitebefore — and the agent said so) |
| `prs` | Open pull requests on the portfolio's brain repo (MissionWinning/67), with the latest five |

**Safety posture — verified, not assumed.** The agent detail (gateway API)
shows its Switch addressing policy is *owner-only*: the single rule allows
the owner (and the owner's agents) and nobody else — which is precisely why
the identity guard answers unlinked accounts in the transcript. The agent
holds **zero tools and zero models** and its service can do exactly one
thing: format snapshot data and post it. There is no Auto mode or
permission-bypass surface to leave on, no credentials to spend, and no
execution path — read-only by construction, not by configuration.

The proof, not the prose — the Ops Agent's detail as returned by the
gateway API (`GET /gateway/agents/{id}`, Nov 7; excerpted to the
safety-relevant fields — UI capability flags omitted, no credential
material exists in this object):

```json
{
  "id": "05dc8d3c-f0e9-4fed-8596-d5393a0cae70",
  "name": "ops-agent",
  "display_name": "Ops Agent",
  "connector_type": "custom",
  "connection_model": "always_on",
  "tool_count": 0,
  "model_count": 0,
  "owner_name": "Agent Bootstrap",
  "addressing_policy": {
    "rules": [
      {
        "rooms": "*",
        "room_groups": "*",
        "users": [],
        "agents": [],
        "owner": true,
        "owner_agents": true,
        "platform": false
      }
    ]
  },
  "agent_type": "always_on",
  "integration_profile": {
    "event_reporting": [],
    "connection_model": "always_on",
    "message_exchange": true,
    "command_capabilities": {
      "reset": "unsupported",
      "compact": "unsupported",
      "interrupt": "unsupported"
    },
    "pre_invocation_mediation": [],
    "post_invocation_mediation": []
  },
  "tools": [],
  "models": [],
  "rooms": [
    {
      "room_id": "f1db60bf-71e2-401e-badc-addf2bc30bbb",
      "room_name": "Mattermost — Switch stack (67-build-1): Portfolio Ops",
      "archived": false,
      "status": "live"
    }
  ],
  "sessions": [
    { "lifecycle": "heartbeat", "state": "live" }
  ]
}
```

Read the `addressing_policy` rule literally: `users: []`, `agents: []`,
`platform: false` — the *only* principals allowed to address this agent
are its owner and the owner's other agents. That one rule is the whole
access-control story, and it is Switch's, enforced before the agent ever
sees a message.

### The second agent — the Watch Agent

`watch_agent.py` — a second deterministic agent with the same posture
(zero tools, zero models, own Switch-issued key, owner-only addressing).
It never answers questions. Every minute it re-reads the snapshot and
diffs the per-monitor watch states against the last ones it saw; when a
monitor flips it posts the transition into the room itself, through the
same Switch message API — 🔴 down, 🟢 recovered, with the monitor's
since-time and the new up-count. On its first start it seeds silently and
posts one honest status line ("Watch Agent online — currently 5/6 up,
`site-sitebefore` DOWN since 15:55"). Its transition logic is verified by
a dry-run test in the evidence (seed → flip → silence → recover); the
live service is running and will post the next real flip as it happens.

### The digest

`digest.py` + `switch-ops-digest.timer` — twice a day (08:45 and 21:45
Toronto) a oneshot posts the `brief` answer into the room under the Ops
Agent's identity, so the portfolio's state arrives on schedule instead of
waiting for someone to ask. The timer's first fire was verified by
triggering the same oneshot unit manually (19:02 EST in the transcript);
the timer itself is armed for 21:45 tonight.

**Data model — an honestly labelled snapshot.** The agent host can reach
the register but the Switch host can't read the fleet VM's files, so
`make_snapshot.py` builds `snapshot.json` on the VM from the live sources
(deadline register, `watch-status.txt` + per-monitor state files, GitHub
via the connector) and `refresh-snapshot.sh` copies it to the Switch
host — automatically every five minutes by cron, so the label on the
next answer is never more than a few minutes old. The agents re-read it
for every answer and print its generation time on every reply. A snapshot
is never dressed up as a live query — and refreshing it mid-demo changed
the label on the next answer from 17:19 to 17:24, which is in the
transcript.

## Try it offline first (60 seconds)

No Switch stack, no Mattermost, no secrets, no network — the agent's
seven answers, computed from the shipped example snapshot:

```bash
python3 quickstart.py        # prints all seven answers
python3 test_formatters.py   # 6 tests — the exactness pitch, made flesh
```

`switch_agent.py` is a service and cannot be imported offline (it reads
its Switch credentials at import time), so `quickstart.py` carries the
seven formatters duplicated verbatim — the demo can never touch the
running agent. Real output, against `snapshot.example.json` (generated
2026-11-07 19:29 Toronto):

<details>
<summary>Full quickstart output — all seven answers</summary>

```
(reading snapshot.example.json)


======================================================================
@ops-agent deadlines
======================================================================
**Deadline board** — 97 active items (4 overdue, 3 due ≤24h, 7 due ≤3d, 23 due ≤7d)

🔴 **Overdue:**
- TELUS / Debt Control Agency collection — decision (file DG231281, $1,495.48) — was due Wed Nov 04, 10:00 (3.4d ago)
- BeforeChristmas Etsy bill $17.17 — suspension if unpaid — was due Fri Nov 06, 23:59 (0.8d ago)
- Wise Business verification — trading address rejected, 2-day clock — was due Sat Nov 07, 07:57 (0.5d ago)
- Rocket Pool GMC Round 42 grant — was due Sat Nov 07, 18:59 (0.0d ago)

🟠 **Due within 24h:**
- Flip the Switch Hackathon (WeMakeDevs × Switch, $10K) — submission — due Sat Nov 07, 23:29
- MLH Solana Hackathon (registration confirmed) — due Sun Nov 08, 10:00
- Vultr Agent Rush Hackathon (lablab.ai) — submissions close Nov 8 UTC — due Sun Nov 08, 18:00

**Next up:**
- Flip the Switch Hackathon (WeMakeDevs × Switch, $10K) — submission — due Sat Nov 07, 23:29 (0.2d)
- MLH Solana Hackathon (registration confirmed) — due Sun Nov 08, 10:00 (0.6d)
- Vultr Agent Rush Hackathon (lablab.ai) — submissions close Nov 8 UTC — due Sun Nov 08, 18:00 (0.9d)
- Cosmos Institute × Inherent essay (£20K, ≤1,000 words) — submission — due Sun Nov 08, 23:59 (1.2d)
- Celo Agents on Open Rails ($5K in CELO) — due Mon Nov 09, 04:00 (1.4d)

— Ops Agent · snapshot 2026-11-07 19:29 Toronto (data age is labelled, never hidden)

======================================================================
@ops-agent gates
======================================================================
**Founder gates — 10 actions waiting on you, most urgent first:**
1. **Decide: recognise the TELUS debt or request written validation** · ~10 min
   ↳ TELUS / Debt Control Agency collection — decision (file DG231281, $1,495.48) — overdue by 3.4d
2. **Pay the $17.17 Etsy bill (or confirm it is already paid)** · ~3 min
   ↳ BeforeChristmas Etsy bill $17.17 — suspension if unpaid — overdue by 0.8d
3. **Upload a trading-address proof (utility bill, not mobile, or bank statement, <3 months, addressed to Mission Winning LLC) + complete phone ID verification (ID photo + selfie)** · ~10 min
   ↳ Wise Business verification — trading address rejected, 2-day clock — overdue by 0.5d
4. **Decide: post a Rocket Pool GMC Round 42 grant application or skip (low fit — ETH staking)** · ~2 min
   ↳ Rocket Pool GMC Round 42 grant — due Sat Nov 07, 18:59 (-0.0d)
5. **Decide: build + submit a project, or let the registration lapse (prep pack in MissionWinning/67 PR #5523)** · ~2 min
   ↳ Flip the Switch Hackathon (WeMakeDevs × Switch, $10K) — submission — due Sat Nov 07, 23:29 (0.2d)
6. **Pick the entry: Solana payment verdict gate with devnet signing (recommended) or the read-only Settlement Receipt Verifier** · ~2 min
   ↳ MLH Solana Hackathon (registration confirmed) — due Sun Nov 08, 10:00 (0.6d)
7. **Decide: enter Vultr Agent Rush or pass (submissions close Nov 8 UTC)** · ~2 min
   ↳ Vultr Agent Rush Hackathon (lablab.ai) — submissions close Nov 8 UTC — due Sun Nov 08, 18:00 (0.9d)
8. **Review the [FOUNDER] block in the prep pack and submit the essay** · ~15 min
   ↳ Cosmos Institute × Inherent essay (£20K, ≤1,000 words) — submission — due Sun Nov 08, 23:59 (1.2d)
9. **Decide: enter Celo (needs real mainnet funds + real users) or skip** · ~2 min
   ↳ Celo Agents on Open Rails ($5K in CELO) — due Mon Nov 09, 04:00 (1.4d)
10. **Decide: enter Learn AR with Specs (Devpost) or pass** · ~2 min
   ↳ Learn AR with Specs, $2.5K — due Mon Nov 09, 17:00 (1.9d)

These are the register's `gated_by` actions: steps only the founder can take (payments, submissions, identity checks). Everything not gated keeps moving without him.

— Ops Agent · snapshot 2026-11-07 19:29 Toronto (data age is labelled, never hidden)

======================================================================
@ops-agent money
======================================================================
**Money — what's owed and what's coming**

🔴 **Overdue:**
- $1,495.48 — TELUS / Debt Control Agency collection — decision (file DG231281, $1,495.48) (was due Wed Nov 04, 10:00, 3.4d ago)
  ↳ Next step: Decide: recognise the TELUS debt or request written validation
- $17.17 — BeforeChristmas Etsy bill $17.17 — suspension if unpaid (was due Fri Nov 06, 23:59, 0.8d ago)
  ↳ Next step: Pay the $17.17 Etsy bill (or confirm it is already paid)
- Wise Business verification — trading address rejected, 2-day clock (was due Sat Nov 07, 07:57, 0.5d ago)
  ↳ Next step: Upload a trading-address proof (utility bill, not mobile, or bank statement, <3 months, addressed to Mission Winning LLC) + complete phone ID verification (ID photo + selfie)

**Payment deadlines ≤14d:**
- $500 — Agent37 $500 credit offer — $5 top-up final click (offer expires ~Nov 11) — due Wed Nov 11, 15:42 (3.8d)
- $69.99 — Surfshark 12-mo VPN via Apple — cancel by Nov 11 or $69.99/yr starts Nov 12 — due Wed Nov 11, 23:59 (4.2d)

Amounts are read from the register entries themselves; the Etsy payout bank (Airwallex) is locked by standing instruction and never appears here as an action.

— Ops Agent · snapshot 2026-11-07 19:29 Toronto (data age is labelled, never hidden)

======================================================================
@ops-agent health
======================================================================
**Watch health — 5/6 monitors UP** (kuma-lite, checked every 5 min from the fleet VM):
- 🟢 `box-healthchecks` — UP since Sat Nov 07, 15:55
- 🟢 `box-mattermost` — UP since Sat Nov 07, 15:55
- 🟢 `box-ntfy` — UP since Sat Nov 07, 15:55
- 🟢 `box-ssh` — UP since Sat Nov 07, 15:55
- 🟢 `site-missionwinning` — UP since Sat Nov 07, 15:55
- 🔴 `site-sitebefore` — DOWN since Sat Nov 07, 15:55

The watch layer: the VM monitors the box (SSH, Healthchecks, ntfy, Mattermost) and both public sites; the box runs the dead-man's switch, Healthchecks, ntfy and Beszel back. The Watch Agent in this room posts here the moment any of these flips.

— Ops Agent · snapshot 2026-11-07 19:29 Toronto (data age is labelled, never hidden)

======================================================================
@ops-agent brief
======================================================================
**Portfolio brief** — 2026-11-07 19:29 Toronto

🔴 **Overdue (4):**
- TELUS / Debt Control Agency collection — decision (file DG231281, $1,495.48) — 3.4d overdue
- BeforeChristmas Etsy bill $17.17 — suspension if unpaid — 0.8d overdue
- Wise Business verification — trading address rejected, 2-day clock — 0.5d overdue
- Rocket Pool GMC Round 42 grant — 0.0d overdue

🟠 **Due within 48h (7):**
- Rocket Pool GMC Round 42 grant — due Sat Nov 07, 18:59
- Flip the Switch Hackathon (WeMakeDevs × Switch, $10K) — submission — due Sat Nov 07, 23:29
- MLH Solana Hackathon (registration confirmed) — due Sun Nov 08, 10:00
- Vultr Agent Rush Hackathon (lablab.ai) — submissions close Nov 8 UTC — due Sun Nov 08, 18:00
- Cosmos Institute × Inherent essay (£20K, ≤1,000 words) — submission — due Sun Nov 08, 23:59

🔑 **Top gates waiting on the founder (10 total):**
- Decide: recognise the TELUS debt or request written validation — TELUS / Debt Control Agency collection — decision (file DG231281, $1,495.48)
- Pay the $17.17 Etsy bill (or confirm it is already paid) — BeforeChristmas Etsy bill $17.17 — suspension if unpaid
- Upload a trading-address proof (utility bill, not mobile, or bank statement, <3 months, addressed to Mission Winning LLC) + complete phone ID verification (ID photo + selfie) — Wise Business verification — trading address rejected, 2-day clock

🩺 **Watch:** 5/6 monitors up — DOWN: site-sitebefore
📬 **PRs:** 25 open on MissionWinning/67
📋 **Board:** 97 active items (4 overdue, 3 ≤24h, 7 ≤3d, 23 ≤7d)

— Ops Agent · snapshot 2026-11-07 19:29 Toronto (data age is labelled, never hidden)

======================================================================
@ops-agent status
======================================================================
**Fleet watch status** (kuma-lite mutual watcher, box ↔ VM):
`2026-11-08T00:24:48Z DOWN: site-sitebefore (5/6 monitors up)`
The box watches the VM (dead-man's switch + Healthchecks + Beszel) and the VM watches the box back. A DOWN line names the monitor and how many are up.

— Ops Agent · snapshot 2026-11-07 19:29 Toronto (data age is labelled, never hidden)

======================================================================
@ops-agent prs
======================================================================
**Open pull requests — MissionWinning/67: 25**
- #5588 docs(applications): Cosmos essay + Flip + Vultr Agent Rush founder prep
- #5587 brain: redact-clone public_safe flag (partial rebuild of #5336)
- #5586 brain: TASKS.jsonl vultr lane rows and stale review updates (rebuild)
- #5585 brain: muse-spark memory export 2026-11-07 16:52 ET
- #5584 roundtable: round 2 — full re-run (muse-spark convergence, single-seat)

— Ops Agent · snapshot 2026-11-07 19:29 Toronto (data age is labelled, never hidden)

That's the whole agent: seven deterministic answers over a
labelled snapshot. In the room, Switch delivers the question and
publishes the answer — see README.md and evidence/.
```

</details>

## Reproduce it

Prerequisites: a self-hosted Switch deployment with its bundled Mattermost
(this demo: Switch 0.31.0 on a Vultr box, "67-build-1"), and the stack's
`.env` (gateway admin, Mattermost admin, agent registration token).

```bash
git clone <this repo> && cd switch-portfolio-ops-room

# 1. Build a snapshot from your fleet data (or use snapshot.example.json)
python3 make_snapshot.py            # writes snapshot.json

# 2. Provision Switch: register the agent, create/bridge the channel,
#    create the room with the agent inside, write switch-agent.env
python3 setup_switch.py

# 2b. Register the second agent and add it to the room (watch-agent.env)
python3 setup_watch_agent.py

# 3. Run the agents + the digest timer
sudo cp switch-ops-agent.service switch-watch-agent.service \
        switch-ops-digest.service switch-ops-digest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now switch-ops-agent switch-watch-agent switch-ops-digest.timer
#    (or simply: python3 switch_agent.py / python3 watch_agent.py)

# 4. Ask it something, as a human, in #portfolio-ops
python3 run_demo.py                 # posts the question set, exports the transcript

# 5. Refresh the data any time (takes effect on the next answer);
#    in production a cron runs this every 5 minutes
./refresh-snapshot.sh
```

Two hard-won setup facts, so you don't lose an hour to them:

- **The bridge URL must be `http://localhost:8065`, not `127.0.0.1`.**
  Switch's outbound SSRF guard refuses the literal loopback IP; the
  deployment's `OUTBOUND_ALLOWED_PRIVATE_HOSTS` allowlists the *hostname*
  `localhost`. The 400 error names the setting.
- **Bang commands belong to Switch.** `!help`, `!reset`, `!compact` etc.
  are the room's own command system — don't build your agent's commands
  with `!` prefixes. Mention the agent and use plain words instead.

## Evidence

- `evidence/demo-excerpt.md` — the clean live round (17:25 EST, Nov 7):
  three questions, three answers, ~1–2 s each. (The demo video covers
  these original three; the full command set is below.)
- `evidence/transcript.md` / `transcript.json` — the full channel
  transcript, exported via the Mattermost API, including Switch's greeting
  and identity-guard notices — plus the extended same-evening session
  (18:59–19:02 EST): all seven questions answered live, the Watch Agent
  joining the room and posting its first status, the first scheduled
  digest, and the Watch Agent's dry-run transition verification.
- The room is live on the demo deployment: Mattermost team `switch`,
  channel `#portfolio-ops`; Switch room "Portfolio Ops".

## What we learned about Switch (the honest list)

- The registration → bridge → room → events path is genuinely composable
  from plain HTTP; no SDK was needed, and the API's error messages taught
  the setup (the SSRF 400 names its own fix).
- Auto-bridging existing channels is the right default: our channel became
  a room the moment the bridge registered, with the agent placed in it.
- The identity-link notice fires on *every* mention from an unlinked
  account, ahead of the agent's answer. The guard is right; the repetition
  is noise a room should be able to tune (once per account per room would
  do). This is our one product gripe — details in the submission.
- An agent's owner being the bootstrap account means the guard can't
  recognize the founder's chat account until it's linked in Console;
  plan the linking step into any real deployment.

## Files

| File | Role |
| --- | --- |
| `quickstart.py` | Offline demo: prints all seven answers from the example snapshot — no Switch stack, no secrets |
| `test_formatters.py` | Offline tests for the answer formatters (run against the example snapshot) |
| `switch_agent.py` | The Ops Agent service (Switch event stream → answers → Switch message API) |
| `watch_agent.py` | The Watch Agent service (snapshot monitor diff → transition posts) |
| `digest.py` | Posts the twice-daily portfolio digest (run by the timer) |
| `setup_switch.py` | One-shot provisioning: agent registration, channel, bridge, room |
| `setup_watch_agent.py` | One-shot provisioning: Watch Agent registration + room membership |
| `make_snapshot.py` | Builds `snapshot.json` from the real register, watcher, and GitHub |
| `refresh-snapshot.sh` | Regenerate + copy the snapshot to the Switch host |
| `run_demo.py` | Posts the demo questions as a human user; exports the transcript |
| `switch-ops-agent.service` | systemd unit for the Ops Agent |
| `switch-watch-agent.service` | systemd unit for the Watch Agent |
| `switch-ops-digest.service` / `.timer` | Oneshot + timer for the 08:45 / 21:45 digests |
| `snapshot.example.json` | A real snapshot (Nov 7) so you can run the formatter offline |
| `evidence/` | Live transcripts from the demo room |

## License

MIT — see `LICENSE`. Switch itself is Apache-2.0 + Commons Clause
(sandbox-quantum/switch); this project is an independent work built on its
public agent/gateway APIs.
