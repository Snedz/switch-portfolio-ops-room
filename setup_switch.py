#!/usr/bin/env python3
"""Provision the Portfolio Ops Room on a self-hosted Switch deployment.

Run on the Switch host (67-build-1), from this repo's directory. Reads the
deployment credentials from the Switch stack's .env (STACK_ENV, default
/root/switch-smoke/.env — never printed) and performs, get-or-create at
every step so it is safe to re-run:

  1. Registers the `ops-agent` with the Switch agent API
     (POST /agents, authorized by AGENT_REGISTRATION_TOKEN) and saves the
     agent's own API key to agent-registration.json (mode 600).
  2. Creates the #portfolio-ops channel on the deployment's Mattermost
     (admin API) — the Switch bridge auto-bridges existing channels.
  3. Logs into the Switch gateway admin API and registers the Mattermost
     collaboration bridge (set as default). NOTE: the bridge URL must be
     http://localhost:8065 — the deployment's OUTBOUND_ALLOWED_PRIVATE_HOSTS
     allowlists the hostname `localhost`; the literal 127.0.0.1 is refused
     by Switch's outbound SSRF guard.
  4. Creates the Switch room "Portfolio Ops" on that bridge with the agent
     inside (or adopts the auto-bridged room of the same name).
  5. Writes switch-agent.env (mode 600) for switch_agent.py.

After this script: install the systemd unit (see README) and start the
agent, then run run_demo.py to watch it answer in the channel.
"""
import http.cookiejar
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
CHANNEL = "portfolio-ops"
ROOM_NAME = "Portfolio Ops"
AGENT_NAME = "ops-agent"


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
    reg_path = HERE / "agent-registration.json"
    if reg_path.exists():
        reg = json.loads(reg_path.read_text())
        print(f"agent exists: {reg['id']}")
    else:
        reg = http("POST", f"{API}/agents", token=env["AGENT_REGISTRATION_TOKEN"], body={
            "name": AGENT_NAME,
            "display_name": "Ops Agent",
            "description": "Portfolio Ops Room agent for Mission Winning: answers deadline-board, "
                           "fleet-status and open-PR questions from a snapshot of real fleet data.",
            "connector_type": "custom",
            "integration_profile": {
                "connection_model": "always_on",
                "message_exchange": True,
                "pre_invocation_mediation": [],
                "post_invocation_mediation": [],
                "event_reporting": [],
            },
            "tools": [], "models": [],
            "metadata": {"project": "portfolio-ops-room"},
        })
        reg_path.write_text(json.dumps(reg))
        reg_path.chmod(0o600)
        print(f"agent registered: {reg['id']}")
    agent_id = reg["id"]

    # 2. Mattermost channel (admin API, get-or-create).
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
            "display_name": "Portfolio Ops", "type": "O",
            "purpose": "Run the Mission Winning portfolio from one room.",
        })
        print(f"channel created: {channel['id']}")

    # 3 + 4. Gateway: bridge and room.
    cj = http.cookiejar.CookieJar()
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
            "description": "Run the Mission Winning portfolio from one room: deadline board, "
                           "fleet status, open PRs — answered by the Ops Agent from real fleet data.",
            "agent_ids": [agent_id],
            "bridge_id": bridge_id,
        })
        print("room created")
    room_id = room["id"]
    print(f"room: {room_id}")

    # 5. Agent service env.
    out = HERE / "switch-agent.env"
    out.write_text(
        f"SWITCH_API={API}\nAGENT_ID={agent_id}\nAGENT_API_KEY={reg['api_key']}\nROOM_ID={room_id}\n")
    out.chmod(0o600)
    print(f"switch-agent.env written -> {out}")
    print("SETUP_DONE")


if __name__ == "__main__":
    sys.exit(main())
