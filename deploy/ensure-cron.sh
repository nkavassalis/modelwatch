#!/bin/sh
# Ensure the cron daemon is running (this box has no systemd/init that would
# start it). Requires passwordless sudo for the logged-in user; silently
# no-ops otherwise. modelwatch publish depends on cron (hourly, TTL-gated).
if command -v service >/dev/null 2>&1; then
    if ! pgrep -x cron >/dev/null 2>&1; then
        sudo -n service cron start >/dev/null 2>&1 || true
    fi
fi
