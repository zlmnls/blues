#!/usr/bin/env bash
# Dashboard update on the Tencent Cloud server: build -> publish static files -> push data to GitHub.
# Run by cron Mon-Sat 16:30 and 19:00 Beijing time; can also be run by hand.
# A failed GitHub push never affects the local dashboard.
set -u
REPO=/opt/blues
PY=/opt/blues-venv/bin/python
export TZ=Asia/Shanghai
export GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4'

log() { echo "[$(date '+%F %T')] $*"; }

exec 9>/run/lock/blues-update.lock
if ! flock -n 9; then log 'another update is running, skip'; exit 0; fi

cd "$REPO" || exit 1
log '=== update start'

build() { timeout 1200 "$PY" build_dashboard.py --out dashboard; }
if ! build; then
  log 'build failed, retrying in 60 s'
  sleep 60
  if ! build; then log 'build failed twice; dashboard keeps the previous data'; exit 1; fi
fi
log 'build ok; nginx serves /opt/blues/dashboard directly, so the page is already updated'

# ---- backup to GitHub (best effort)
git add dashboard/data
if git diff --cached --quiet; then
  log 'no data change, nothing to push'
else
  git commit -q -m "dashboard data $(date +%F) (tencent server)" && log 'committed data'
fi
if [ "$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 1)" = 0 ]; then
  log '=== update done (GitHub already up to date)'; exit 0
fi
ok=0
for i in 1 2 3; do
  if timeout 180 git pull -q --rebase -X theirs origin main && timeout 180 git push -q origin HEAD:main; then ok=1; break; fi
  git rebase --abort >/dev/null 2>&1
  log "push attempt $i failed"
  sleep $((i * 20))
done
if [ $ok = 1 ]; then log 'pushed to GitHub'; else log 'GitHub push failed 3 times; will retry with the next update'; fi
log '=== update done'
exit 0
