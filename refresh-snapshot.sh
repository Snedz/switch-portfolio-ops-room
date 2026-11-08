#!/bin/bash
# Regenerate the fleet snapshot on the Muse VM and copy it to 67-build-1,
# where the Ops Agent and Watch Agent read it. Run by cron every 5 minutes;
# also safe to run by hand. The agents re-read snapshot.json for every
# answer, so a refresh takes effect immediately and the new snapshot time
# shows in the next answer.
set -eu
cd "$(dirname "$0")"
python3 make_snapshot.py
scp -o BatchMode=yes -o IdentitiesOnly=yes -i /home/hatch/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/home/hatch/.ssh/known_hosts -o GlobalKnownHostsFile=/dev/null \
  -o ProxyCommand="python3 /home/hatch/workspace/scripts/ts-proxy.py %h %p" \
  snapshot.json root@100.69.46.81:/root/portfolio-ops/snapshot.json
