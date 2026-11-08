#!/usr/bin/env python3
"""Portfolio digest poster — run by switch-ops-digest.timer (08:45 + 21:45
Toronto) as a oneshot. Posts the Ops Agent's `brief` answer into the
Portfolio Ops Room under the Ops Agent's own Switch identity, so the room
gets a living twice-daily digest without anyone asking. Reuses
switch_agent.py's formatter and sender so there is one source of truth
for what a brief looks like.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import switch_agent as ops

TZ = ZoneInfo("America/Toronto")


def main() -> None:
    snap = ops.load_snapshot()
    body = ops.fmt_brief(snap)
    text = ("📋 **Scheduled portfolio digest**\n\n" + body +
            f"\n\n— Ops Agent · snapshot {snap['generated_at_toronto']} "
            "(digest posts 08:45 + 21:45 Toronto; ask `brief` any time)")
    ops.send(text)
    print(f"[{datetime.now(TZ):%H:%M:%S}] digest posted")


if __name__ == "__main__":
    main()
