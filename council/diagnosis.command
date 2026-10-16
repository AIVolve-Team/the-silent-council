#!/bin/bash
# The diagnosis trial in a Terminal window of its own: double-click in the Finder, or
# `open council/diagnosis.command`. `open` does not pass options to trial.command, that is why
# the diagnosis has a file of its own. Guide: council/TRIAL.md.
cd "$(dirname "$0")/.." || exit 1
./council/trial.sh --diagnosis
echo
read -r -p "Press Enter to close this window." _
