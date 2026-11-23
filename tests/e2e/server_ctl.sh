#!/bin/bash
# Optional helper for machines where the test process may not open sockets (some sandboxes only let
# a shell-started process do it). Start this from a shell, then run the e2e tests with E2E_CTL=<dir>:
#     tests/e2e/server_ctl.sh /tmp/e2e_ctl 8541 &
# A test writes "start <profile-file-or-none> <hosted 0|1>" or "stop" to <dir>/cmd and waits for <dir>/ack.
DIR="${1:?control dir}"; PORT="${2:-8541}"
ROOT="${E2E_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
mkdir -p "$DIR"; rm -f "$DIR/cmd" "$DIR/ack"
PID=""
stop() { if [ -n "$PID" ]; then kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; PID=""; fi; }
trap 'stop; exit 0' TERM INT
while true; do
  if [ -f "$DIR/cmd" ]; then
    read -r action profile hosted < "$DIR/cmd"; rm -f "$DIR/cmd"
    stop
    if [ "$action" = "start" ]; then
      [ "$profile" = "none" ] && profile="$DIR/no_profile.json"
      if [ "$hosted" = "1" ]; then export RETIREMENT_SIM_HOSTED=1; else unset RETIREMENT_SIM_HOSTED; fi
      RETIREMENT_SIM_PROFILE="$profile" python3 -m streamlit run "$ROOT/ui/app.py" --server.headless true \
        --server.port "$PORT" --browser.gatherUsageStats false > "$DIR/server.log" 2>&1 &
      PID=$!
      for _ in $(seq 1 120); do (echo > "/dev/tcp/127.0.0.1/$PORT") 2>/dev/null && break; sleep 0.5; done
    fi
    echo done > "$DIR/ack"
  fi
  sleep 0.3
done
