#!/usr/bin/env bash
# Launch a pico viewer on the Pi's local display, detached, harvesting the
# Wayland desktop session env from a running GUI process.
# Usage: bash deploy_view.sh <script.py> [extra args...]
set -u
SCRIPT="${1:?need a script name}"; shift || true

# kill any existing viewer to free the serial port (only python procs, never self)
for p in $(pgrep -f "python3 pico_pc"); do
  [ "$p" = "$$" ] && continue
  kill "$p" 2>/dev/null
done
sleep 1

PORT=$(ls /dev/ttyACM* 2>/dev/null | head -1)
[ -z "$PORT" ] && { echo "NO PICO PORT FOUND"; exit 1; }

# harvest desktop session env from the first process that actually has WAYLAND_DISPLAY set
for pid in $(pgrep -u "$(id -un)"); do
  [ -r "/proc/$pid/environ" ] || continue
  if tr "\0" "\n" < "/proc/$pid/environ" | grep -q "^WAYLAND_DISPLAY="; then
    while IFS= read -r -d "" kv; do
      case "$kv" in
        DISPLAY=*|WAYLAND_DISPLAY=*|XAUTHORITY=*|XDG_RUNTIME_DIR=*) export "$kv" ;;
      esac
    done < "/proc/$pid/environ"
    break
  fi
done
: "${DISPLAY:=:0}"
: "${XDG_RUNTIME_DIR:=/run/user/$(id -u)}"

cd ~/induction || exit 1
setsid nohup python3 "$SCRIPT" --port "$PORT" "$@" > /tmp/picoplot.log 2>&1 < /dev/null &
NP=$!
sleep 4
echo "LAUNCHED $SCRIPT pid=$NP port=$PORT DISPLAY=${DISPLAY:-?} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-?}"
if kill -0 "$NP" 2>/dev/null; then echo "STILL RUNNING (ok)"; else echo "EXITED EARLY -- log:"; fi
echo "----- /tmp/picoplot.log -----"
tail -n 15 /tmp/picoplot.log
