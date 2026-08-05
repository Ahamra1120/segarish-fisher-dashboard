#!/usr/bin/env bash
# Waits for the backend to answer, then launches Chromium in kiosk mode
# pointed at the dashboard. Run this from a desktop autostart entry
# (kiosk-autostart.desktop) -- it needs an X/Wayland session to draw
# into, so it must NOT be run directly as a systemd system service.
set -euo pipefail

URL="${DASHBOARD_URL:-http://localhost:8000}"

echo "kiosk.sh: waiting for backend at $URL ..."
until curl -sf "$URL/api/health" >/dev/null 2>&1; do
  sleep 1
done

# Disable screen blanking so the touchscreen doesn't sleep mid-trip.
xset s off -dpms 2>/dev/null || true

CHROMIUM_BIN="$(command -v chromium-browser || command -v chromium || true)"
if [ -z "$CHROMIUM_BIN" ]; then
  echo "kiosk.sh: no chromium binary found (tried chromium-browser, chromium)" >&2
  exit 1
fi

exec "$CHROMIUM_BIN" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required \
  "$URL"
