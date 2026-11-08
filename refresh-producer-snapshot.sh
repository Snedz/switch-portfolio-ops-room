#!/bin/bash
# Regenerate the Creator Room (producer) snapshot on the Muse VM and
# copy it to 67-build-1, where the Producer Agent reads it.
#
# This is the producer's OWN refresh path — deliberately separate from
# refresh-snapshot.sh (the ops room's): separate script, separate file,
# no shared state. The Producer Agent re-reads producer-snapshot.json
# for every answer and re-renders its room documents when the snapshot
# changes, so a refresh takes effect on the next question with no
# service restart.
#
# Run by hand tonight. The systemd timer unit for this ships in the
# repo (switch-producer-snapshot.{service,timer}) NOT enabled: the
# generator's sources live on this VM, and enabling the timer on the
# box before the sources move there would have it regenerate from
# nothing — the generator refuses (exit 2) rather than emit a false
# snapshot. Box-side generation is the documented next step; see
# docs/ARCHITECTURE.md.
set -eu
cd "$(dirname "$0")"
python3 make_producer_snapshot.py
scp -o BatchMode=yes -o IdentitiesOnly=yes -i /home/hatch/.ssh/id_ed25519 \
  -o UserKnownHostsFile=/home/hatch/.ssh/known_hosts -o GlobalKnownHostsFile=/dev/null \
  -o ProxyCommand="python3 /home/hatch/workspace/scripts/ts-proxy.py %h %p" \
  producer-snapshot.json root@100.69.46.81:/root/creator-room/producer-snapshot.json
echo "producer snapshot refreshed on 67-build-1"
