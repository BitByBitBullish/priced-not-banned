#!/usr/bin/env python3
"""
witness_analyze.py — Read inputs.jsonl and emit the study tables.

Outputs:
 1. Percentile table (p50/p90/p99/p99.9/p99.99/max) of witness bytes, per era,
    per class AND per bucket (monetary vs data).
 2. Largest-legit-monetary hunt: MAX monetary witness + top-20 monetary inputs.
 3. Subsidy table: per era, total witness bytes and % share by bucket/class.
 4. Annex-present count.

Percentile method: NEAREST-RANK on the ascending sorted list.
  index = ceil(p/100 * N) - 1  (clamped to [0, N-1]); pXX = sorted[index].
  Computed in integer arithmetic (p scaled x100) to avoid IEEE-754 ceil errors
  when p*N/100 is an exact integer (e.g. 99.9% of 1000).

Tail-support: a percentile is only meaningful if enough observations sit beyond
it. Any pXX with fewer than 10 observations in its tail ((100-p)/100 * n < 10)
is rendered with a trailing '~': too few tail obs to trust as an estimated
quantile — the value is the nearest-rank order statistic (equal to the sample
max only when nothing lies beyond it). Enrichment ("C_heavy") blocks are EXCLUDED from the combined
representative tables and used only in the max/outlier hunt.
"""
import sys, json, math, os
from collections import defaultdict
from pathlib import Path

# Data directory (self-contained for public release): override with WITNESS_DATA_DIR.
_DATA_ROOT = Path(os.environ.get("WITNESS_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))

DATA = str(_DATA_ROOT / "inputs.jsonl")

# bucket assignment. p2wsh_other / p2tr_scriptpath_other kept as their own
# "contract" line so the reviewer sees them separately; they are counted in
# MONETARY totals (non-data) but flagged.
DATA_CLASSES = {"taproot_inscription"}
CONTRACT_CLASSES = {"p2wsh_other", "p2tr_scriptpath_other"}
MONETARY_CORE = {"p2wpkh_singlesig", "p2tr_keypath", "p2wsh_multisig", "lightning_like"}

KNOWN_CLASSES = DATA_CLASSES | CONTRACT_CLASSES | MONETARY_CORE | {"other", "__legacy__"}

def bucket(cls):
    if cls not in KNOWN_CLASSES:
        raise ValueError(f"unmapped wit_class {cls!r} — refusing to bucket silently")
    if cls in DATA_CLASSES: return "data"
    if cls in ("other", "__legacy__"): return "other"
    return "monetary"  # core + contract

def pctl(sorted_vals, p):
    n = len(sorted_vals)
    if n == 0: return None
    pp = round(p * 100)                    # 99.99 -> 9999 exactly (no float drift)
    idx = (pp * n + 9999) // 10000 - 1     # integer ceil(pp*n/10000) - 1
    return sorted_vals[max(0, min(idx, n - 1))]

PCTS = [50, 90, 99, 99.9, 99.99]

def table(vals):
    s = sorted(vals)
    row = {f"p{p}": pctl(s, p) for p in PCTS}
    row["max"] = s[-1] if s else None
    row["n"] = len(s)
    return row

def _mark(p, val, n):
    # '~' flags an under-supported tail: fewer than 10 obs beyond the percentile,
    # so the value is the nearest-rank order statistic, not a trustworthy quantile.
    if val is None: return "NA"
    # integer form of (100-p)/100*n >= 10, avoids float drift at exact boundaries
    # (e.g. p99.9 at n=10000, where the float subtraction wrongly yields 9.9999).
    supported = (10000 - round(p * 100)) * n >= 100000
    return f"{val}{'' if supported else '~'}"

def fmt(row):
    n = row['n']
    return (f"n={n:>8}  p50={_mark(50,row['p50'],n):>6}  p90={_mark(90,row['p90'],n):>7}  "
            f"p99={_mark(99,row['p99'],n):>8}  p99.9={_mark(99.9,row['p99.9'],n):>9}  "
            f"p99.99={_mark(99.99,row['p99.99'],n):>10}  max={str(row['max']):>9}")

def main():
    if not os.path.exists(DATA):
        print(f"NO DATA at {DATA}", file=sys.stderr); sys.exit(1)
    recs = [json.loads(l) for l in open(DATA) if l.strip()]
    eras = sorted({r["era"] for r in recs})
    classes = sorted({r["wit_class"] for r in recs})

    heavy_n = sum(1 for r in recs if r["era"] == "C_heavy")
    print(f"# WITNESS STUDY  ({len(recs)} inputs, eras={eras})")
    print(f"# legend: '~' after a percentile = under-supported tail (<10 obs beyond it); value is the nearest-rank order statistic (= sample max only when nothing lies beyond it), not a trustworthy quantile.")
    print(f"# {heavy_n} inputs are from inscription-enrichment (C_heavy) blocks: EXCLUDED from combined/representative tables, used only in the outlier hunt.")
    print(f"# CAVEAT: inputs are CLUSTER-sampled by block (all inputs of each drawn block are taken), so extreme-tail cells may be supported by only a few independent blocks/entities, NOT by n independent inputs. See per-bucket 'tail support' block below.\n")

    # 1. percentiles per era per class + per bucket
    for era in eras:
        er = [r for r in recs if r["era"] == era]
        print(f"== ERA {era}  ({len(er)} inputs) ==")
        for cls in classes:
            v = [r["witness_bytes"] for r in er if r["wit_class"] == cls]
            if v:
                print(f"  {cls:<24} {fmt(table(v))}")
        for bk in ("monetary", "data"):
            v = [r["witness_bytes"] for r in er if bucket(r["wit_class"]) == bk]
            if v:
                print(f"  [BUCKET {bk:<8}]         {fmt(table(v))}")
        print()

    # all-era combined monetary vs data (enrichment blocks excluded)
    repr_recs = [r for r in recs if r["era"] != "C_heavy"]
    print("== ALL ERAS COMBINED (excl. C_heavy enrichment; 'monetary' bucket INCLUDES contract classes p2wsh_other + p2tr_scriptpath_other) ==")
    for bk in ("monetary", "data"):
        v = [r["witness_bytes"] for r in repr_recs if bucket(r["wit_class"]) == bk]
        if v:
            print(f"  [BUCKET {bk:<8}]         {fmt(table(v))}")
    # uncontaminated headline: signature-bearing core classes ONLY (no contract spends)
    core = [r["witness_bytes"] for r in repr_recs if r["wit_class"] in MONETARY_CORE]
    if core:
        print(f"  [BUCKET mon-core]         {fmt(table(core))}")
    print("  -- same buckets, SERIALIZED witness bytes (on-wire, incl. length prefixes) --")
    for bk in ("monetary", "data"):
        v = [r["witness_bytes_serialized"] for r in repr_recs if bucket(r["wit_class"]) == bk]
        if v:
            print(f"  [BUCKET {bk:<8} ser]     {fmt(table(v))}")
    # cluster-support diagnostic: how many DISTINCT blocks back the p99.99 tail.
    # If tail_obs are spread over few blocks the quantile is entity-driven, not
    # a trustworthy population p99.99 regardless of raw n (see header CAVEAT).
    print("  -- tail support: distinct blocks contributing obs at/above the p99.99 cell --")
    for label, subset in (
            ("monetary", [r for r in repr_recs if bucket(r["wit_class"]) == "monetary"]),
            ("mon-core", [r for r in repr_recs if r["wit_class"] in MONETARY_CORE]),
            ("data", [r for r in repr_recs if bucket(r["wit_class"]) == "data"])):
        if not subset:
            continue
        thr = pctl(sorted(r["witness_bytes"] for r in subset), 99.99)
        tail = [r for r in subset if r["witness_bytes"] >= thr]
        nblk = len({r["height"] for r in tail})
        flag = "" if nblk >= 10 else "  <-- entity/cluster-driven, do NOT publish as population p99.99"
        print(f"     {label:<9} p99.99>={thr}: {len(tail)} tail obs across {nblk} distinct block(s){flag}")
    print()

    # 2. largest legit monetary hunt
    mon = [r for r in recs if bucket(r["wit_class"]) == "monetary"]
    mon.sort(key=lambda r: r["witness_bytes"], reverse=True)
    if mon:
        top = mon[0]
        print(f"== MAX MONETARY WITNESS == {top['witness_bytes']} bytes  "
              f"class={top['wit_class']} m_of_n={top['m_of_n']} annex={top['annex']} "
              f"h={top['height']} tx={top['txid']}")
        print("  top-20 largest monetary inputs:")
        for r in mon[:20]:
            print(f"    {r['witness_bytes']:>8}B  {r['wit_class']:<22} "
                  f"m_of_n={str(r['m_of_n']):<6} annex={r['annex']!s:<5} "
                  f"h={r['height']} {r['txid'][:20]}..:{r['vin']}")
        print()

    # 3. subsidy table: share of total witness bytes per era
    print("== SUBSIDY TABLE (share of total witness BYTES) ==")
    for era in eras:
        er = [r for r in recs if r["era"] == era]
        tot_true = sum(r["witness_bytes"] for r in er)
        tot = tot_true or 1   # divisor guard only; never printed
        by_bucket = defaultdict(int)
        by_class = defaultdict(int)
        for r in er:
            by_bucket[bucket(r["wit_class"])] += r["witness_bytes"]
            by_class[r["wit_class"]] += r["witness_bytes"]
        print(f"  ERA {era}: total_witness_bytes={tot}")
        for bk in ("monetary", "data", "other"):
            if by_bucket[bk]:
                print(f"     bucket {bk:<9} {by_bucket[bk]:>12}  {100*by_bucket[bk]/tot:6.2f}%")
        for cls in sorted(by_class, key=lambda c: -by_class[c]):
            print(f"       - {cls:<24} {by_class[cls]:>12}  {100*by_class[cls]/tot:6.2f}%")
        print()

    # 4. annex + nested transparency
    # scope to match the legend's C_heavy-excluded promise; C_heavy shown separately
    annex_r = sum(1 for r in repr_recs if r.get("annex"))
    annex_h = sum(1 for r in recs if r.get("annex")) - annex_r
    nested_r = sum(1 for r in repr_recs if r.get("nested"))
    nested_h = sum(1 for r in recs if r.get("nested")) - nested_r
    print(f"== ANNEX == {annex_r} annex-present inputs (representative; +{annex_h} in C_heavy enrichment)")
    print(f"== NESTED SEGWIT == {nested_r} P2SH-wrapped SegWit inputs (representative; +{nested_h} in C_heavy) "
          f"(counted in monetary under their native class; witness bytes identical to native)")

if __name__ == "__main__":
    main()
