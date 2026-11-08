#!/usr/bin/env python3
"""Provision the Creator Room on the fleet's self-hosted Switch deployment.

Clone of setup_switch.py (which provisioned the Portfolio Ops Room
tonight), retargeted: channel `creator-room`, room "Creator Room", agent
`producer`, outputs producer-registration.json + producer-agent.env so
nothing collides with the ops room. Run on the Switch host (67-build-1)
from the creator-room directory. Reads the deployment credentials from
the Switch stack's .env (STACK_ENV, default /root/switch-smoke/.env —
never printed). Get-or-create at every step, safe to re-run:

  1. Registers the `producer` agent with the Switch agent API.
  2. Creates the #creator-room channel on the deployment's Mattermost
     (admin API) — the Switch bridge auto-bridges existing channels.
     Order matters (tonight's lesson): channel first, then bridge, then
     room.
  3. Reuses the existing Mattermost collaboration bridge (registers one
     only if none exists). NOTE: the bridge URL must be
     http://localhost:8065 — the deployment's
     OUTBOUND_ALLOWED_PRIVATE_HOSTS allowlists the hostname `localhost`;
     the literal 127.0.0.1 is refused by Switch's outbound SSRF guard.
  4. Creates the Switch room "Creator Room" on that bridge with the
     agent inside (or adopts the auto-bridged room of the same name).
  5. Writes producer-agent.env (mode 600) for producer_agent.py.
"""
from http import cookiejar as _cookiejar
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).parent
STACK_ENV = Path(os.environ.get("STACK_ENV", "/root/switch-smoke/.env"))
API = "http://127.0.0.1:8000"
MM = "http://127.0.0.1:8065"
MM_BRIDGE_URL = "http://localhost:8065"  # allowlisted hostname — see step 3 note
CHANNEL = "creator-room"
ROOM_NAME = "Creator Room"
AGENT_NAME = "producer"


def read_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def http(method, url, token=None, body=None, opener=None, raw=False):
    req = urllib.request.Request(url, method=method)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    open_fn = opener.open if opener else urllib.request.urlopen
    try:
        with open_fn(req, data=data, timeout=30) as r:
            payload = r.read()
            if raw:
                return r.headers, payload
            return json.loads(payload or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from None


def main() -> None:
    env = read_env(STACK_ENV)

    # 1. Register the agent with Switch.
    reg_path = HERE / "producer-registration.json"
    if reg_path.exists():
        reg = json.loads(reg_path.read_text())
        print(f"agent exists: {reg['id']}")
    else:
        reg = http("POST", f"{API}/agents", token=env["AGENT_REGISTRATION_TOKEN"], body={
            "name": AGENT_NAME,
            "display_name": "Producer Agent",
            "description": "Creator Room agent for Mission Winning: reports the founder's real "
                           "media pipeline state — H3 animated shorts queue, scripts, renders, "
                           "and the clipping lane — honestly, including what is blocked.",
            "connector_type": "custom",
            "integration_profile": {
                "connection_model": "always_on",
                "message_exchange": True,
                "pre_invocation_mediation": [],
                "post_invocation_mediation": [],
                "event_reporting": [],
            },
            "tools": [], "models": [],
            "metadata": {"project": "creator-room"},
        })
        reg_path.write_text(json.dumps(reg))
        reg_path.chmod(0o600)
        print(f"agent registered: {reg['id']}")
    agent_id = reg["id"]

    # 2. Mattermost channel (admin API, get-or-create) — channel FIRST.
    headers, _ = http("POST", f"{MM}/api/v4/users/login",
                      body={"login_id": env["MATTERMOST_ADMIN_USER"],
                            "password": env["MATTERMOST_ADMIN_PASSWORD"]}, raw=True)
    mm_admin = headers["Token"]
    team = http("GET", f"{MM}/api/v4/teams/name/{env['MATTERMOST_TEAM_NAME']}", mm_admin)
    try:
        channel = http("GET", f"{MM}/api/v4/teams/{team['id']}/channels/name/{CHANNEL}", mm_admin)
        print(f"channel exists: {channel['id']}")
    except RuntimeError:
        channel = http("POST", f"{MM}/api/v4/channels", mm_admin, {
            "team_id": team["id"], "name": CHANNEL,
            "display_name": "Creator Room", "type": "O",
            "purpose": "The founder's media pipeline, reported honestly by the Producer Agent.",
        })
        print(f"channel created: {channel['id']}")

    # 3 + 4. Gateway: bridge (reuse existing) and room.
    cj = _cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    http("POST", f"{API}/gateway/auth/login", opener=opener,
         body={"email": env["GATEWAY_ADMIN_EMAIL"], "password": env["GATEWAY_ADMIN_PASSWORD"]})
    bridges = http("GET", f"{API}/gateway/collaborations", opener=opener)
    bridge = next((b for b in bridges if b.get("bridge_type") == "mattermost"), None)
    if bridge is None:
        bridge = http("POST", f"{API}/gateway/collaborations", opener=opener, body={
            "bridge_type": "mattermost",
            "display_name": "Mattermost — Switch stack",
            "connection_config": {
                "url": MM_BRIDGE_URL,
                "team_name": env["MATTERMOST_TEAM_NAME"],
                "admin_user": env["MATTERMOST_ADMIN_USER"],
                "admin_password": env["MATTERMOST_ADMIN_PASSWORD"],
                "default_member": env["MATTERMOST_ADMIN_USER"],
            },
            "channel_creation_enabled": True,
            "set_as_default": True,
        })
        print("bridge created")
    bridge_id = bridge["bridge_id"]
    print(f"bridge: {bridge_id} ({bridge.get('status')})")

    rooms = http("GET", f"{API}/gateway/rooms", opener=opener)
    room = next((r for r in rooms if r.get("name") == ROOM_NAME), None)
    if room is None:
        room = http("POST", f"{API}/gateway/rooms", opener=opener, body={
            "name": ROOM_NAME,
            "description": "The founder's media pipeline in one room: H3 animated shorts, "
                           "scripts, renders and the clipping lane — reported by the Producer "
                           "Agent from real files, including what is blocked and why.",
            "agent_ids": [agent_id],
            "bridge_id": bridge_id,
            "channel_type": "channel_public",
        })
        print("room created")
    room_id = room["id"]
    print(f"room: {room_id}")

    # 5. Agent service env.
    out = HERE / "producer-agent.env"
    out.write_text(
        f"SWITCH_API={API}\nAGENT_ID={agent_id}\nAGENT_API_KEY={reg['api_key']}\nROOM_ID={room_id}\n")
    out.chmod(0o600)
    print(f"producer-agent.env written -> {out}")
    print("SETUP_DONE")


if __name__ == "__main__":
    sys.exit(main())
