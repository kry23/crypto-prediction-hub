#!/usr/bin/env bash
#
# Install / refresh the three crypto-predictor systemd units.
# Run as root (via sudo).
#
# Idempotent: copies units, reloads daemon, enables + starts.
# Skipped checks: assumes /opt/crypto-predictor and the deploy user
# already exist (cutover runbook handles those).
#
# Usage:
#   sudo bash /opt/crypto-predictor/deploy/install_systemd_units.sh

set -euo pipefail

SRC_DIR=$(dirname "$(readlink -f "$0")")/systemd
DEST_DIR=/etc/systemd/system

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root (use sudo)." >&2
    exit 1
fi

UNITS=(
    crypto-predictor-scheduler.service
    crypto-predictor-ui.service
    crypto-predictor-intel-bridge.service
)

echo "Copying units from ${SRC_DIR} to ${DEST_DIR}..."
for u in "${UNITS[@]}"; do
    cp -v "${SRC_DIR}/${u}" "${DEST_DIR}/${u}"
done

echo "systemctl daemon-reload..."
systemctl daemon-reload

echo "Enabling + starting units..."
for u in "${UNITS[@]}"; do
    systemctl enable "$u"
    systemctl restart "$u"
done

echo
echo "Done. Verify with:"
echo "  systemctl status crypto-predictor-scheduler"
echo "  systemctl status crypto-predictor-ui"
echo "  systemctl status crypto-predictor-intel-bridge"
echo
echo "Tail logs with:"
echo "  journalctl -u crypto-predictor-scheduler -f"
