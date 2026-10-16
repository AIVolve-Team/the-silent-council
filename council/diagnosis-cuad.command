#!/bin/bash
# The check of the diagnosis on CUAD dev in a Terminal window of its own: double-click in the
# Finder, or `open council/diagnosis-cuad.command` (also from Claude Code). `open` does not pass options to
# trial.command, that is why it has a file of its own. Guide: council/TRIAL.md.
cd "$(dirname "$0")/.." || exit 1
./council/trial.sh --diagnosis-cuad
echo
read -r -p "Press Enter to close this window." _
