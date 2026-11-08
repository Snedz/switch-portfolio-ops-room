#!/usr/bin/env python3
"""Demo driver for the Portfolio Ops Room (runs on 67-build-1).

Logs into Mattermost as the human user (MATTERMOST_USER from the Switch
stack .env), asks the Ops Agent its question set in #portfolio-ops the
way a person would, waits for the agent's answers to arrive in the channel
(the Switch bridge publishes them), and exports the full transcript as
JSON + Markdown with Toronto timestamps into ./demo-out/.
"""
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
STACK_ENV = Path("/root/switch-smoke/.env")
MM = "http://127.0.0.1:8065"
TZ = ZoneInfo("America/Toronto")
CHANNEL_ID = "t54df4eyri8o7kgbbjmppxd64c"  # #portfolio-ops on the Switch stack's Mattermost
AGENT_MM_USER = "rbw3pi3cr7yrdxwb3n4y1rfojy"  # ops-agent's Mattermost bot account (bridge posts as this user)
QUESTIONS = [
    "@ops-agent deadlines",
    "@ops-agent gates",
    "@ops-agent money",
    "@ops-agent health",
    "@ops-agent brief",
    "@ops-agent status",
    "@ops-agent prs",
    "@ops-agent help",
]


def read_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def call(method, path, token=None, body=None, raw=False):
    req = urllib.request.Request(MM + path, method=method)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, data=data, timeout=15) as r:
        payload = r.read()
        if raw:
            return r.headers, payload
        return json.loads(payload or b"{}")


def login(login_id, password):
    headers, _ = call("POST", "/api/v4/users/login",
                      body={"login_id": login_id, "password": password}, raw=True)
    return headers["Token"]


def fetch_posts(token):
    page = call("GET", f"/api/v4/channels/{CHANNEL_ID}/posts?page=0&per_page=100", token)
    posts = page.get("posts", {})
    return [posts[pid] for pid in reversed(page.get("order", []))]


def main() -> None:
    env = read_env(STACK_ENV)
    token = login(env["MATTERMOST_USER"], env["MATTERMOST_USER_PASSWORD"])
    me = call("GET", "/api/v4/users/me", token)
    print(f"driver asking as {me['username']}")
    baseline = {p["id"] for p in fetch_posts(token)}

    call("POST", "/api/v4/posts", token, {
        "channel_id": CHANNEL_ID,
        "message": "Running the portfolio from this room today. Ops Agent — the full set:",
    })
    for q in QUESTIONS:
        call("POST", "/api/v4/posts", token, {"channel_id": CHANNEL_ID, "message": q})
        print(f"asked: {q}")
        time.sleep(2)

    deadline = time.time() + 150
    answered = 0
    while time.time() < deadline:
        posts = [p for p in fetch_posts(token) if p["id"] not in baseline]
        answered = sum(1 for p in posts if p["user_id"] == AGENT_MM_USER)
        if answered >= len(QUESTIONS):
            break
        time.sleep(3)
    print(f"agent answers in channel: {answered}/{len(QUESTIONS)}")

    posts = fetch_posts(token)
    users = {}
    for p in posts:
        uid = p["user_id"]
        if uid not in users:
            try:
                users[uid] = call("GET", f"/api/v4/users/{uid}", token)["username"]
            except Exception:
                users[uid] = uid
    transcript = []
    for p in posts:
        ts = datetime.fromtimestamp(p["create_at"] / 1000, TZ)
        transcript.append({
            "time_toronto": ts.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "user": users.get(p["user_id"], p["user_id"]),
            "message": p["message"],
            "id": p["id"],
        })
    outdir = HERE / "demo-out"
    outdir.mkdir(exist_ok=True)
    (outdir / "transcript.json").write_text(json.dumps(transcript, indent=1))
    md = ["# Portfolio Ops Room — live transcript",
          "Mattermost #portfolio-ops on the self-hosted Switch stack (67-build-1). "
          "The Ops Agent is connected through the Switch gateway; its answers are published "
          "into the channel by the Switch Mattermost bridge.\n"]
    for t in transcript:
        md.append(f"**{t['time_toronto']} — {t['user']}**\n\n{t['message']}\n")
    (outdir / "transcript.md").write_text("\n".join(md))
    print(f"transcript: {len(transcript)} posts -> {outdir}")
    print("DEMO_DONE" if answered >= len(QUESTIONS) else "DEMO_INCOMPLETE")


if __name__ == "__main__":
    main()
