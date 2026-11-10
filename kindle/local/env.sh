#!/usr/bin/env sh
# Settings for kindle-dash on the fridge Kindle 4.
# Copy this file over /mnt/us/dashboard/local/env.sh on the Kindle.

# Paste the address of your dashboard image here (see README, step 3).
export DASH_URL="https://YOUR-GITHUB-NAME.github.io/kindle-fridge/YOUR-SECRET.png"

export WIFI_TEST_IP=1.1.1.1
export TIMEZONE="Europe/London"

# When to wake up and fetch a new image (cron format, Kindle's local time).
# 06:10, 07:10, 08:10, then every two hours until 22:10. Nothing overnight.
export REFRESH_SCHEDULE="10 6,7,8,10,12,14,16,18,20,22 * * *"

# Do a full (flashing) refresh every other update to clear e-ink ghosting.
export FULL_DISPLAY_REFRESH_RATE=1

# Keep the dashboard on screen overnight instead of the "sleeping" picture:
# the longest gap (22:10 -> 06:10) is 8 hours, so 12 hours is never reached.
export SLEEP_SCREEN_INTERVAL=43200

# Battery text. The dashboard is landscape but eips writes in the Kindle's
# portrait grid (50 columns x 40 rows), so the text comes out sideways in the
# blank strip at the right edge. Row 39 suits "kindle_buttons": "right"
# (text at the bottom right, reading upwards); for "left" use row 0.
export BATTERY_COL=1
export BATTERY_ROW=39
export BATTERY_WARN_PERCENT=20

export LOW_BATTERY_REPORTING=false
