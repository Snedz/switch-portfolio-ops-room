# Portfolio Ops Room — run a 64-venture portfolio from one chat room

**Track: Best Business Workflow — Flip the Switch Hackathon (WeMakeDevs × Switch)**
**Team: Mission Winning (T3RBB9)**

A solo founder runs a 64-venture portfolio with a fleet of AI agents. The
work lives in three places: a deadline register (122 tracked commitments),
a watch layer that monitors the machines, and GitHub. Checking any of them
meant leaving the conversation and opening a tool.

The Portfolio Ops Room collapses that into the room where the team already
talks: ask `@ops-agent deadlines`, `status`, or `prs` in the channel and
the agent answers in seconds, from real data, with the data's age labelled
on every answer.

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
| `status` | The mutual watcher: the box↔VM monitoring state (one monitor was genuinely DOWN during the demo — site-sitebefore — and the agent said so) |
| `prs` | Open pull requests on the portfolio's brain repo (MissionWinning/67), with the latest five |

**Safety posture — verified, not assumed.** The agent detail (gateway API)
shows its Switch addressing policy is *owner-only*: the single rule allows
the owner (and the owner's agents) and nobody else — which is precisely why
the identity guard answers unlinked accounts in the transcript. The agent
holds **zero tools and zero models** and its service can do exactly one
thing: format snapshot data and post it. There is no Auto mode or
permission-bypass surface to leave on, no credentials to spend, and no
execution path — read-only by construction, not by configuration.

**Data model — an honestly labelled snapshot.** The agent host can reach
the register but the Switch host can't read the fleet VM's files, so
`make_snapshot.py` builds `snapshot.json` on the VM from the live sources
(deadline register, `watch-status.txt`, GitHub via the connector) and
`refresh-snapshot.sh` copies it to the Switch host. The agent re-reads it
for every answer and prints its generation time on every reply. A snapshot
is never dressed up as a live query — and refreshing it mid-demo changed
the label on the next answer from 17:19 to 17:24, which is in the
transcript.

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

# 3. Run the agent
sudo cp switch-ops-agent.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now switch-ops-agent
#    (or simply: python3 switch_agent.py)

# 4. Ask it something, as a human, in #portfolio-ops
python3 run_demo.py                 # posts the three questions, exports the transcript

# 5. Refresh the data any time (takes effect on the next answer)
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
  three questions, three answers, ~1–2 s each.
- `evidence/transcript.md` / `transcript.json` — the full 34-post channel
  transcript, exported via the Mattermost API, including Switch's greeting
  and identity-guard notices.
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
| `switch_agent.py` | The agent service (Switch event stream → answers → Switch message API) |
| `setup_switch.py` | One-shot provisioning: agent registration, channel, bridge, room |
| `make_snapshot.py` | Builds `snapshot.json` from the real register, watcher, and GitHub |
| `refresh-snapshot.sh` | Regenerate + copy the snapshot to the Switch host |
| `run_demo.py` | Posts the demo questions as a human user; exports the transcript |
| `switch-ops-agent.service` | systemd unit for the agent |
| `snapshot.example.json` | A real snapshot (Nov 7) so you can run the formatter offline |
| `evidence/` | Live transcripts from the demo room |

## License

MIT — see `LICENSE`. Switch itself is Apache-2.0 + Commons Clause
(sandbox-quantum/switch); this project is an independent work built on its
public agent/gateway APIs.
