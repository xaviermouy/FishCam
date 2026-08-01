#!/bin/bash
# clear_wittypi_logs.sh
#
# Deletes all .log files in the WittyPi installation directory.
# Safe to run — only removes log files, not scripts or schedule.wpi.
#
# Usage:
#   bash clear_wittypi_logs.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WITTYPI_DIR=$(python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); import config; print(config.get_wittypi_settings()['install_dir'])" 2>/dev/null)

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FishCam — Clear WittyPi Logs"
echo "════════════════════════════════════════════════════════════════════"
echo ""

if [ -z "$WITTYPI_DIR" ]; then
    echo "  ERROR: Could not read WittyPi install_dir from config."
    exit 1
fi

if [ ! -d "$WITTYPI_DIR" ]; then
    echo "  ERROR: WittyPi directory not found: $WITTYPI_DIR"
    exit 1
fi

echo "  WittyPi directory: $WITTYPI_DIR"
echo ""

# Count and list log files before deletion
LOG_FILES=("$WITTYPI_DIR"/*.log)
if [ ! -f "${LOG_FILES[0]}" ]; then
    echo "  No .log files found — nothing to clear."
    exit 0
fi

echo "  Log files found:"
for f in "${LOG_FILES[@]}"; do
    echo "    $(basename "$f")  ($(du -h "$f" | cut -f1))"
done
echo ""

read -r -p "  Delete these files? [y/N]  " answer
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "  Aborted — no files deleted."
    exit 0
fi
echo ""

# Delete log files
deleted=0
failed=0
for f in "${LOG_FILES[@]}"; do
    if sudo rm "$f" 2>/dev/null; then
        deleted=$((deleted + 1))
    else
        echo "  WARNING: Could not delete $(basename "$f")"
        failed=$((failed + 1))
    fi
done

echo "  Done. $deleted log file(s) deleted."
[ "$failed" -gt 0 ] && echo "  WARNING: $failed file(s) could not be deleted."
echo ""
