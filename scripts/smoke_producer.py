#!/usr/bin/env python3
"""Smoke test for the Creator Room's Producer Agent — runs on 67-build-1.

Asks EVERY intent in the live room (as the human Mattermost user, the
way a person would), waits for the bridge to publish the agent's
answers, and checks each answer arrived and carries the snapshot
label. Prints one PASS/FAIL line per intent and exits non-zero on any
failure, so it can gate a deploy.

    python3 scripts/smoke_producer.py                 # all 11 intents
    python3 scripts/smoke_producer.py status credits  # a subset
    python3 scripts/smoke_producer.py --out smoke.txt # also save a log

Credentials come from the deployment stack env (STACK_ENV, default
/root/switch-smoke/.env) — the same pattern as run_producer_demo.py.
Nothing is printed from that file. Standard library only.
"""
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

STACK_ENV = Path("/root/switch-smoke/.env")
MM = "http://127.0.0.1:8065"
TZ = ZoneInfo("America/Toronto")
CHANNEL_ID = "pwa6fja1siyydfzs75ejxydc6e"  # #creator-room
ALL_INTENTS = ["status", "ideas", "script", "renders", "clips", "credits",
               "review", "sources", "next", "health", "help"]
LABEL = "— Producer Agent · snapshot"
# Switch's identity guard precedes each answer with an owner notice
# (the asking chat account isn't linked to a Switch user). Those posts
# are not answers — filter them out before pairing answers to intents.
GUARD_MARKER = "I only take instructions from my owner"


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


def fetch_posts(token):
    page = call("GET", f"/api/v4/channels/{CHANNEL_ID}/posts?page=0&per_page=100", token)
    posts = page.get("posts", {})
    return [posts[pid] for pid in reversed(page.get("order", []))]


def main() -> int:
    intents, out_path = [], None
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out_path = argv[i + 1]
            i += 2
        else:
            intents.append(argv[i])
            i += 1
    intents = intents or ALL_INTENTS
    env = read_env(STACK_ENV)
    headers, _ = call("POST", "/api/v4/users/login",
                      body={"login_id": env["MATTERMOST_USER"],
                            "password": env["MATTERMOST_USER_PASSWORD"]}, raw=True)
    token = headers["Token"]
    me = call("GET", "/api/v4/users/me", token)
    my_id = me["id"]
    lines = [f"smoke {datetime.now(TZ):%Y-%m-%d %H:%M:%S %Z} — asking as "
             f"{me['username']}: {len(intents)} intents"]
    baseline = {p["id"] for p in fetch_posts(token)}

    t0 = time.time()
    for name in intents:
        call("POST", "/api/v4/posts", token,
             {"channel_id": CHANNEL_ID, "message": f"@producer {name}"})
        time.sleep(2)

    answers: list[str] = []
    deadline = time.time() + 240
    while time.time() < deadline:
        posts = [p for p in fetch_posts(token) if p["id"] not in baseline]
        answers = [p["message"] for p in posts
                   if p["user_id"] != my_id and GUARD_MARKER not in p["message"]]
        if len(answers) >= len(intents):
            break
        time.sleep(3)
    elapsed = time.time() - t0

    failures = 0
    for i, name in enumerate(intents):
        if i < len(answers):
            ok_label = LABEL in answers[i]
            first = answers[i].splitlines()[0][:90] if answers[i] else "(empty)"
            verdict = "PASS" if ok_label else "FAIL (no snapshot label)"
            if not ok_label:
                failures += 1
            lines.append(f"[{verdict}] {name}: {first}")
        else:
            failures += 1
            lines.append(f"[FAIL] {name}: no answer within timeout")
    lines.append(f"smoke result: {len(intents) - failures}/{len(intents)} intents "
                 f"answered with labels in {elapsed:.0f}s")
    report = "\n".join(lines)
    print(report)
    if out_path:
        Path(out_path).write_text(report + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
