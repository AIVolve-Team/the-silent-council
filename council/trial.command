#!/bin/bash
# The full trial in a Terminal window of its own: double-click in the Finder, or `open council/trial.command`
# (also from Claude Code). This way it runs outside VS Code and Claude Code, and at the end the window stays open with
# the summary. Guide: council/PROVA.md.
cd "$(dirname "$0")/.." || exit 1
./council/trial.sh "$@"
echo
read -r -p "Press Enter to close this window." _
