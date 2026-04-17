#!/bin/bash
set -euo pipefail

cleanup() {
  runuser -u kuser -- vncserver -kill :1 2>/dev/null || true
  if [[ -f /tmp/ws.pid ]]; then
    kill "$(cat /tmp/ws.pid)" 2>/dev/null || true
    rm -f /tmp/ws.pid
  fi
}
trap cleanup EXIT

# If a container password was supplied, set it on kuser and grant sudo access.
# The env var is cleared immediately after so it doesn't linger in the process env.
if [[ -n "${CONTAINER_PASSWORD:-}" ]]; then
  echo "kuser:${CONTAINER_PASSWORD}" | chpasswd
  usermod -aG sudo kuser
  # Ensure sudo is available and passworded access works
  printf '%%sudo ALL=(ALL:ALL) ALL\n' > /etc/sudoers.d/airlock-sudo
  chmod 0440 /etc/sudoers.d/airlock-sudo
  unset CONTAINER_PASSWORD
fi

# Clean up stale X11/VNC locks from a previous run
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# Create an XDG_RUNTIME_DIR for kuser so PulseAudio can place its socket there.
# xstartup exports the same path before starting pulseaudio + XFCE4.
KUID=$(id -u kuser)
mkdir -p /run/user/"$KUID"
chown kuser:kuser /run/user/"$KUID"
chmod 700 /run/user/"$KUID"

# Start VNC (xstartup will launch PulseAudio then XFCE4)
runuser -u kuser -- vncserver :1 \
  -localhost yes \
  -geometry 1280x800 \
  -depth 24 \
  -SecurityTypes None

for _ in $(seq 1 60); do
  if nc -z 127.0.0.1 5901 2>/dev/null; then
    break
  fi
  sleep 0.5
done

websockify 127.0.0.1:6081 127.0.0.1:5901 &
echo $! >/tmp/ws.pid

# Wait for PulseAudio socket — xstartup starts PA inside the VNC session
for _ in $(seq 1 30); do
  if [[ -S /run/user/"$KUID"/pulse/native ]]; then
    break
  fi
  sleep 0.5
done

# Stream PulseAudio monitor as WebM/Opus; one ffmpeg process per HTTP connection.
# Must run as kuser so it can access the per-user PulseAudio socket.
runuser -u kuser -- env \
  XDG_RUNTIME_DIR=/run/user/"$KUID" \
  PULSE_SERVER=unix:/run/user/"$KUID"/pulse/native \
  python3 /usr/local/lib/airlock/audio_server.py &

exec nginx -g "daemon off;"
