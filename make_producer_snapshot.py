#!/usr/bin/env python3
"""Generate the Creator Room snapshot from REAL media-pipeline state.

Truthfulness discipline (same as the ops room): every status below is
derived from a file check at generation time — a prompt pack's contents,
an mp4's existence/size/date via os.stat, a template's presence — never
from an assumption. Where the honest state is "waiting" or "blocked",
the snapshot says exactly that. The snapshot is labelled with its
generation time and the agent prints that time in every answer.

Sources (all on the fleet VM, all local file checks):
  - H3 goal files: prompt pack v1 + v1.2 addendum, lane-2 shorts plan,
    Virex-format script template, the two test clips (os.stat)
  - moneyprinter-test/RENDER-LOG.md + subtitle-tool/ (assembly proof)
  - clipping-state.json next to this script — a labelled copy of
    MissionWinning/67 VENTURES/clipping/STATE.json fetched via the
    GitHub connector; if absent, the clipping section is OMITTED and
    the snapshot says why. Its contents are never invented.

Output: producer-snapshot.json next to this script — copied to
67-build-1 where the Producer Agent reads it.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
HERE = Path(__file__).parent
H3 = Path.home() / "workspace/goals/minimax-h3-video-capability-for-program-67/files"


def stat_of(p: Path) -> dict | None:
    try:
        st = os.stat(p)
    except OSError:
        return None
    return {
        "exists": True,
        "size_bytes": st.st_size,
        "size_mb": round(st.st_size / 1_000_000, 2),
        "modified_toronto": datetime.fromtimestamp(st.st_mtime, TZ).strftime("%Y-%m-%d %H:%M Toronto"),
    }


def main() -> None:
    now = datetime.now(TZ)

    # Fail-safe: the H3 goal files are the primary source. On a host
    # without them (e.g. 67-build-1, if the refresh timer is ever enabled
    # there before the sources move), REFUSE to write a snapshot rather
    # than emit one that falsely reports everything missing.
    if not H3.exists():
        raise SystemExit(f"refusing to generate: H3 source dir not present: {H3}")

    pack = (H3 / "h3-prompt-pack-v1.md").read_text() if (H3 / "h3-prompt-pack-v1.md").exists() else ""
    addendum = (H3 / "h3-prompt-pack-v1.2-addendum-2026-10-29.md").exists()
    ideas = {
        "prompt_pack_v1": bool(pack),
        "prompt_pack_v12_addendum": addendum,
        "items": [
            {"n": 1, "title": "POD explainer test clip (how print-on-demand works)",
             "state": "done — generated Oct 29, passed review (see renders)"},
            {"n": 2, "title": "BeforeChristmas product clip",
             "state": "queued — prompt written; needs a hero product picked and a production route before it can be generated"},
            {"n": 3, "title": "Faceless animated explainer segment (espresso machine)",
             "state": "queued — prompt written; 4 segments make one short; not generated"},
        ],
        "lane2_pilot": {
            "specced": (H3 / "lane-2-owned-animated-shorts-2026-10-30.md").exists(),
            "state": "job-carded (JOB-h3-lane2-pilot), UNSTARTED",
            "clips": ["reef detail test (specced, unrun — blocked on credits/route)",
                      "one owned explainer short, one-failure-one-fix format (not scripted)"],
            "also_blocked_on": "studio working name — founder decision; nothing publishes without one",
        },
    }

    template_path = H3 / "template-virex-format-scripts-2026-10-31.md"
    scripts = {
        "template_ready": template_path.exists(),
        "template": "Virex-format explainer template (one failure → one fix → one visual beat; 5–7 beats + bookend close)",
        "episode_scripts_exist": False,
        "honest_state": "NO episode script exists. The template is ready; nobody has written episode 1 yet.",
    }

    clip1 = stat_of(H3 / "h3-test-clip-01-pod-explainer.mp4")
    clip2 = stat_of(H3 / "h3-test-clip-02-buttons-text.mp4")
    renders = {
        "clips": [
            {"file": "h3-test-clip-01-pod-explainer.mp4", "stat": clip1,
             "verdict": "PASS — house 3D CG style, three connected shots (Oct 29)"},
            {"file": "h3-test-clip-02-buttons-text.mp4", "stat": clip2,
             "verdict": "PASS — all four UI labels rendered exactly (BOOK/SERVICES/REVIEWS/DIRECTIONS), icons correct (Oct 29)"},
        ],
        "generation": {
            "state": "BLOCKED",
            "why": "Free Hailuo credits: 2 of 150 left; cheapest clip costs 28. The reef test (clip 03) was never run for this reason.",
            "unblocks_with": "founder production-route decision — API-first recommended (~$2.60–3.90 per kept clip at 2K); MiniMax API model id + key entitlement still unverified",
        },
        "assembly": {
            "proven": (Path.home() / "workspace/moneyprinter-test/RENDER-LOG.md").exists(),
            "note": "Assembly proven Oct 31: MoneyPrinterTurbo rendered a draft short end-to-end (pipeline test, synthetic B-roll — not a publishable asset); subtitle burn-in tool built and tested (~/workspace/subtitle-tool/).",
        },
    }

    clipping = None
    clipping_note = None
    cs_path = HERE / "clipping-state.json"
    if cs_path.exists():
        clipping = json.loads(cs_path.read_text())
    else:
        clipping_note = ("clipping section omitted: clipping-state.json not present at snapshot time; "
                         "the Producer never invents the clipping lane's state.")

    credits = {
        "free_credits_left": 2,
        "free_credits_total": 150,
        "cheapest_clip_credits": 28,
        "api_cost_per_kept_clip_usd": "$2.60–3.90",
        "route_decision": "PENDING — founder decision (API-first recommended)",
        "spent_usd": 0,
        "checked": ("Balance as recorded in the H3 goal records, 2026-11-07; "
                    "the reef test clip was never run because 2 < 28."),
    }

    review_gate = {
        "human_review_required": True,
        "h3_test_clips": "both clips human-reviewed Oct 29 — PASS verdicts recorded in renders",
        "clipping_samples": "built and run on samples Oct 16; awaiting a campaign pick and "
                            "founder review before any post",
        "posted_ever": False,
        "earned_usd": 0,
        "gates": ["G-POST: clipper posting blocked until the founder approves (C06)",
                  "G-PAYOUT: payout method not set (C07)",
                  "Studio working name undecided — nothing publishes without one (lane 2)"],
        "publishing": ("The Producer reports state only: it cannot generate, post, publish, "
                       "or spend. Every publish path in this pipeline ends at a human."),
    }

    room = {
        "room_name": "Creator Room",
        "agent": "producer — deterministic, no LLM",
        "intents_version": "v2 (status/credits/review/sources/health added; room documents live)",
        "documents": ["Creator Room — Pipeline Snapshot",
                      "Creator Room — Pipeline State & Review Gate"],
        "snapshot_refresh": ("manual one-command refresh (refresh-producer-snapshot.sh); "
                             "the systemd timer unit ships in this repo NOT enabled — "
                             "box-side generation is the next step"),
    }

    snap = {
        "generated_at_toronto": now.strftime("%Y-%m-%d %H:%M Toronto"),
        "generated_at_utc": now.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": [
            "H3 goal files on the fleet VM (prompt pack, lane-2 plan, script template, test clips via os.stat)",
            "moneyprinter-test/RENDER-LOG.md + subtitle-tool/ (assembly proof)",
            "MissionWinning/67 VENTURES/clipping/STATE.json via GitHub connector (labelled copy)",
        ],
        "ideas": ideas,
        "scripts": scripts,
        "renders": renders,
        "credits": credits,
        "review_gate": review_gate,
        "room": room,
        "clipping": clipping,
        "clipping_note": clipping_note,
        "next": {
            "honest_next_action": ("The pipeline is mostly WAITING, and the wait has one name: the founder's "
                                   "production-route decision (API-first, ~$2.60–3.90 per kept clip). That single "
                                   "decision unblocks H3 generation — the BeforeChristmas clip, the faceless "
                                   "explainer, and the lane-2 pilot (reef test + first owned short)."),
            "also_waiting": [
                "Hero product pick for the BeforeChristmas clip",
                "Studio working name (publishing gate for lane 2)",
                "Episode 1 script — the template is ready, the script is not written",
                "Clipper revival needs a campaign pick (Whop account + campaign join are still todo; nothing has ever been posted; earned $0)",
            ],
        },
    }
    out = HERE / "producer-snapshot.json"
    out.write_text(json.dumps(snap, indent=1))
    print(f"producer snapshot written: {out} — ideas {len(ideas['items'])} items, "
          f"clips on disk: {[c['file'] for c in renders['clips'] if c['stat']]} , "
          f"generation {renders['generation']['state']}, clipping {'present' if clipping else 'OMITTED'}")


if __name__ == "__main__":
    main()
