#!/usr/bin/env python3
"""Provision the Watch Agent on the Portfolio Ops Room's Switch deployment.

Run on the Switch host (67-build-1), from this repo's directory, after
setup_switch.py. Get-or-create at every step so it is safe to re-run:

  1. Registers the `watch-agent` with the Switch agent API
     (POST /agents, authorized by AGENT_REGISTRATION_TOKEN from the stack
     .env — never printed) and saves its API key to
     watch-agent-registration.json (mode 600).
  2. Tries to add the agent to the "Portfolio Ops" room through the
     gateway admin API (endpoint variants attempted in order; the result
     is printed). The Watch Agent posts via POST /agents/{id}/message,
     which the bridge publishes into the room.
  3. Prints the agent's addressing policy from the gateway so it can be
     checked against the Ops Agent's owner-only policy.
  4. Writes watch-agent.env (mode 600) for watch_agent.py.

Deployment credentials come from the Switch stack's .env (STACK_ENV,
default /root/switch-smoke/.env — never printed).
"""
import http.cookiejar
from http.cookiejar import CookieJar
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).parent
STACK_ENV = Path(os.environ.get("STACK_ENV", "/root/switch-smoke/.env"))
API = "http://127.0.0.1:8000"
ROOM_NAME = "Portfolio Ops"
AGENT_NAME = "watch-agent"
OPS_ENV = HERE / "switch-agent.env"


def read_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def http(method, url, token=None, body=None, opener=None):
    req = urllib.request.Request(url, method=method)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    open_fn = opener.open if opener else urllib.request.urlopen
    with open_fn(req, data=data, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def main() -> None:
    env = read_env(STACK_ENV)
    ops_cfg = read_env(OPS_ENV)
    room_id = ops_cfg["ROOM_ID"]

    # 1. Register the agent with Switch.
    reg_path = HERE / "watch-agent-registration.json"
    if reg_path.exists():
        reg = json.loads(reg_path.read_text())
        print(f"agent exists: {reg['id']}")
    else:
        reg = http("POST", f"{API}/agents", token=env["AGENT_REGISTRATION_TOKEN"], body={
            "name": AGENT_NAME,
            "display_name": "Watch Agent",
            "description": "Portfolio Ops Room watch agent for Mission Winning: posts fleet "
                           "monitor transitions (down / recovered) into the room as they "
                           "happen, from the same fleet snapshot the Ops Agent answers from.",
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

    # 2 + 3. Gateway: room membership attempt + addressing policy check.
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    http("POST", f"{API}/gateway/auth/login", opener=opener,
         body={"email": env["GATEWAY_ADMIN_EMAIL"], "password": env["GATEWAY_ADMIN_PASSWORD"]})
    attempts = [
        ("POST", f"{API}/gateway/rooms/{room_id}/agents", {"agent_id": agent_id}),
        ("POST", f"{API}/gateway/rooms/{room_id}/members", {"agent_id": agent_id}),
        ("POST", f"{API}/gateway/rooms/{room_id}/agents", {"agent_ids": [agent_id]}),
    ]
    joined = False
    for method, url, body in attempts:
        try:
            http(method, url, opener=opener, body=body)
            print(f"room membership: added via {method} {url.split('/gateway')[-1]}")
            joined = True
            break
        except Exception as e:
            print(f"room membership attempt failed ({url.split('/gateway')[-1]}): {str(e)[:120]}")
    if not joined:
        print("room membership: no gateway endpoint accepted the add — "
              "agent will post via the agent API (verify in the channel)")

    agents = http("GET", f"{API}/gateway/agents", opener=opener)
    for a in agents:
        if a.get("id") == agent_id:
            print(f"addressing_policy: {json.dumps(a.get('addressing_policy'))}")

    # 4. Agent service env.
    out = HERE / "watch-agent.env"
    out.write_text(
        f"SWITCH_API={API}\nAGENT_ID={agent_id}\nAGENT_API_KEY={reg['api_key']}\nROOM_ID={room_id}\n")
    out.chmod(0o600)
    print(f"watch-agent.env written -> {out}")
    print("SETUP_DONE")


if __name__ == "__main__":
    sys.exit(main())
