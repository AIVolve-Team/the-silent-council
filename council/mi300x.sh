#!/usr/bin/env bash
# The council's run on the MI300X, in G1's engine container, after its steps 3 and 4 (container and
# fp32 against bf16, g1/README.md): the guide is council/MI300X.md. The first time, launch
# SYSTEM_TORCH=1 NO_REALIGN=1 ./council/trial.sh --quick, which prepares Python, data and model and shows
# that everything runs on the GPU.
#
#   ./council/mi300x.sh calibration    telepathy with 0, 10, 20 and 40 steps and text, on CUAD and demo
#                                      dev; writes the tables to choose steps and thresholds
#   ./council/mi300x.sh dev            the dev eval on every benchmark, with STEPS=<chosen steps>
#   ./council/mi300x.sh test           the test run, only once, with the frozen pre-registration
#   ./council/mi300x.sh replication    the 72 unused CUAD test contracts, only once, telepathy, text and
#                                      solo agent; the report puts together test, replication and total
#
# Variables: STEPS (dev, test and replication); the W_a realignment is off, as decided with the diagnosis of 12/10
# (NO_REALIGN=0 turns it back on, only for a comparison: it is not the pre-registered configuration).
# To try the script without a GPU: MODEL=Qwen/Qwen3-0.6B LIMIT=1 ./council/mi300x.sh calibration (LIMIT=2 for
# dev, because the swaps need at least 2 contracts).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COUNCIL="$ROOT/council"
PY="${PY:-$COUNCIL/.venv/bin/python}"
PHASE="${1:-}"
MODEL="${MODEL:-Qwen/Qwen3-14B}"
case "$PHASE" in
  calibration | dev | test | replication) ;;
  *) sed -n '2,17p' "$0"; exit 2 ;;
esac
[ -x "$PY" ] || { echo "$PY is missing: first launch ./council/trial.sh --quick"; exit 1; }
OUTPUT="$COUNCIL/results-mi300x/$PHASE"
mkdir -p "$OUTPUT"
exec > >(tee -a "$OUTPUT/run.log") 2>&1
echo "== $PHASE with $MODEL ($(date '+%d/%m %H:%M'))"

options=(--model "$MODEL" --dtype bfloat16)
[ "${NO_REALIGN:-1}" = 1 ] && options+=(--no-realign)
trials=()
[ -n "${LIMIT:-}" ] && trials+=(--limit "$LIMIT")
filter() { grep --line-buffered -v -E "Warning|warn\(|Loading checkpoint"; }
cd "$COUNCIL/review"

case "$PHASE" in
  calibration)
    for benchmark in cuad demo; do
      echo "-- $benchmark: telepathy with 0, 10, 20, 40 steps ($(date +%H:%M))"
      "$PY" -u -m review.run --benchmark "$benchmark" --mode telepathy --steps 0 10 20 40 "${options[@]}" \
        ${trials[@]+"${trials[@]}"} --output "$OUTPUT" 2>&1 | filter
      echo "-- $benchmark: text ($(date +%H:%M))"
      "$PY" -u -m review.run --benchmark "$benchmark" --mode text --steps 10 "${options[@]}" ${trials[@]+"${trials[@]}"} \
        --output "$OUTPUT" 2>&1 | filter
    done
    for benchmark in cuad demo; do "$PY" -m review.calibration "$OUTPUT" --benchmark "$benchmark"; done \
      > "$OUTPUT/calibration.md"
    echo "Done. Tables for the calibration in $OUTPUT/calibration.md: choose steps and thresholds and write them in the pre-registration."
    ;;
  dev | test)
    [ -n "${STEPS:-}" ] || { echo "STEPS is needed, the latent steps chosen in STEPS=10 $0 $PHASE"; exit 2; }
    subset=dev
    if [ "$PHASE" = test ]; then
      subset=test
      [ -z "${LIMIT:-}" ] || { echo "On the test every contract runs: no LIMIT."; exit 2; }
    fi
    for benchmark in cuad contractnli claudette; do
      echo "-- $benchmark, $subset ($(date +%H:%M))"
      "$PY" -u -m review.eval run --benchmark "$benchmark" --subset "$subset" --steps "$STEPS" "${options[@]}" \
        ${trials[@]+"${trials[@]}"} --output "$OUTPUT" 2>&1 | filter
    done
    # The demo set has no test: it is the one of the blind check by hand.
    echo "-- demo ($(date +%H:%M))"
    "$PY" -u -m review.eval run --benchmark demo --steps "$STEPS" "${options[@]}" ${trials[@]+"${trials[@]}"} \
      --output "$OUTPUT" 2>&1 | filter
    "$PY" -m review.eval report "$OUTPUT" > /dev/null
    "$PY" -m review.blind prepare "$OUTPUT" --output "$OUTPUT/blind"
    echo "Done. Report in $OUTPUT/report.md (aggregate numbers only, to publish)."
    echo "For the blind check: $OUTPUT/blind/for-the-checker, with the contracts; the key stays with the organiser."
    ;;
  replication)
    [ -n "${STEPS:-}" ] || { echo "STEPS is needed, the same as the test: STEPS=0 $0 $PHASE"; exit 2; }
    [ -z "${LIMIT:-}" ] || { echo "On the replication every contract runs: no LIMIT."; exit 2; }
    echo "-- cuad, replication ($(date +%H:%M))"
    "$PY" -u -m review.eval run --benchmark cuad --subset replication --steps "$STEPS" "${options[@]}" \
      --output "$OUTPUT" 2>&1 | filter
    # The total puts together test and replication: the CUAD runs of the test are linked here, not copied.
    TEST="$COUNCIL/results-mi300x/test"
    if ls "$TEST"/cuad-test-*.jsonl > /dev/null 2>&1; then
      ln -sf "$TEST"/cuad-test-*.jsonl "$TEST/eval-cuad-test.json" "$OUTPUT/"
    else
      echo "The test runs are not in $TEST: the report has only the replication."
    fi
    "$PY" -m review.eval report "$OUTPUT" > /dev/null
    echo "Done. Report in $OUTPUT/report.md: test, replication and total, to report."
    ;;
esac
