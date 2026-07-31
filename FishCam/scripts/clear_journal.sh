#!/bin/bash
# clear_journal.sh
#
# Wipes the systemd journal log.
# Run manually before each deployment to start with a clean log.
#
# Usage:
#   bash clear_journal.sh

echo "Journal disk usage before:"
journalctl --disk-usage

echo ""
echo "Clearing journal..."
sudo journalctl --rotate
sudo journalctl --vacuum-time=1s

echo ""
echo "Journal disk usage after:"
journalctl --disk-usage

echo ""
echo "Done. Journal cleared."
