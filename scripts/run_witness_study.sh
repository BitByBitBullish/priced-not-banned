#!/usr/bin/env bash
# One-shot full witness-study run (self-contained; data source = mempool.space public API).
# Usage: run_witness_study.sh <timestamp>
set -uo pipefail
TS="${1:?need timestamp arg}"
cd "$(dirname "$0")" || exit 2   # scripts/ dir
mkdir -p ../reports
echo "=== witness study FULL run start $(date '+%Y-%m-%d %H:%M:%S %Z') (ts=$TS pid=$$) ==="
echo "--- selftest (byte-math + detectors) ---"
python3 witness_study.py --selftest || { echo "SELFTEST FAILED"; exit 1; }
echo "--- sampler: 30 blocks/era (A/B/C) + 10 inscription-heavy enrichment blocks ---"
python3 witness_study.py --blocks-per-era 30 --heavy 10 || { echo "SAMPLER FAILED"; exit 1; }
echo "--- analyzer -> reports/report-${TS}.txt ---"
python3 witness_analyze.py | tee "../reports/report-${TS}.txt"
echo "=== witness study FULL run DONE $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
