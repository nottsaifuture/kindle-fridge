#!/usr/bin/env sh
# Download the dashboard image to "$1" (called by kindle-dash's dash.sh).
# Copy this file over /mnt/us/dashboard/local/fetch-dashboard.sh on the Kindle.
DIR="$(dirname "$0")"
TMP="$1.part"

# xh ships with kindle-dash and, unlike the Kindle's own curl/wget,
# understands modern HTTPS such as GitHub Pages.
"$DIR/../xh" -d -q -o "$TMP" get "$DASH_URL"

# Keep the old image if the download failed or returned an error page.
if ! head -c 8 "$TMP" 2>/dev/null | grep -q PNG; then
  rm -f "$TMP"
  exit 1
fi
mv "$TMP" "$1"

# dash.sh puts the new image on screen right after this script returns,
# so wait a moment and then print the battery level on top of it.
level=$(gasgauge-info -c)
level=${level%?}
if [ "$level" -le "${BATTERY_WARN_PERCENT:-20}" ]; then
  message="LOW BATTERY ${level}% - PLEASE CHARGE"
else
  message="Battery ${level}%"
fi
(sleep 5 && /usr/sbin/eips "${BATTERY_COL:-1}" "${BATTERY_ROW:-39}" "$message") >/dev/null 2>&1 &

exit 0
