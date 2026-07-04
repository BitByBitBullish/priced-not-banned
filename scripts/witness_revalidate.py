#!/usr/bin/env python3
"""
witness_revalidate.py — INDEPENDENT non-cluster re-validation draw for the
per-input witness-byte cap study (2026-07-04).

Motivation: the primary study (witness_study.py) CLUSTER-samples whole blocks, so
extreme-tail percentile cells rest on only a few independent blocks/entities. This
sampler instead draws MANY distinct random blocks across the whole SegWit era and
takes only ONE tx-page (<=25 txs) from a random offset in each — so ~N monetary
inputs come from ~N/40 INDEPENDENT blocks, giving real distinct-block tail support.

Question it answers: does ANY legit monetary witness exceed 1500 bytes, and how
often does the ~1.4KB lightning-close class recur across independent entities/blocks?

Classification is REUSED verbatim from witness_study.py (import) so buckets/byte-
math are identical to the primary study. Bulk per-input output is written alongside the datasets (data/).

Usage: witness_revalidate.py [--target 50000] [--seed 2013] [--tip H]
"""
import os, sys, json, random, time, argparse, math
from pathlib import Path
from collections import defaultdict

# Data directory (self-contained for public release): override with WITNESS_DATA_DIR.
_DATA_ROOT = Path(os.environ.get("WITNESS_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import witness_study as ws  # noqa: E402  reuse get/classify/tip/height_to_hash/SEGWIT

PAGE = 25
OUT = _DATA_ROOT / "revalidate_inputs.jsonl"
DATA_CLASSES = {"taproot_inscription"}
CONTRACT = {"p2wsh_other", "p2tr_scriptpath_other"}
CAP_CANDIDATES = (1500, 2000, 2500)

def is_monetary(cls):
    return cls not in DATA_CLASSES and cls != "__legacy__"

def pct(sorted_vals, q):
    """Nearest-rank percentile (matches witness_analyze semantics)."""
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, math.ceil(q / 100.0 * len(sorted_vals)) - 1))
    return sorted_vals[k]

def analyze(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    mon = [r for r in rows if r["monetary"]]
    print(f"\n===== RE-VALIDATION ANALYSIS ({len(rows)} inputs, {len(mon)} monetary) =====")
    # distinct blocks overall
    print(f"distinct blocks sampled: {len(set(r['h'] for r in rows))}")

    def block_table(vals_rows, label):
        v = sorted(r["witness_bytes"] for r in vals_rows)
        if not v:
            print(f"  {label:<26} n=0"); return
        nb = len(set(r["h"] for r in vals_rows))
        print(f"  {label:<26} n={len(v):<7} blocks={nb:<5} "
              f"p50={pct(v,50):<5} p90={pct(v,90):<6} p99={pct(v,99):<6} "
              f"p99.9={pct(v,99.9):<7} p99.99={pct(v,99.99):<7} max={v[-1]}")

    print("\n-- per monetary class (witness_bytes) --")
    by_cls = defaultdict(list)
    for r in mon:
        by_cls[r["wit_class"]].append(r)
    for cls in sorted(by_cls):
        block_table(by_cls[cls], cls)

    print("\n-- buckets --")
    block_table(mon, "monetary (all)")
    core = [r for r in mon if r["wit_class"] not in CONTRACT]
    block_table(core, "mon-core (excl contract)")

    print("\n-- OVER-CAP monetary inputs (the whole question) --")
    for cap in CAP_CANDIDATES:
        over = sorted([r for r in mon if r["witness_bytes"] > cap],
                      key=lambda r: -r["witness_bytes"])
        over_core = [r for r in over if r["wit_class"] not in CONTRACT]
        nb = len(set(r["h"] for r in over))
        nb_core = len(set(r["h"] for r in over_core))
        print(f"  > {cap}B : {len(over)} monetary inputs across {nb} blocks "
              f"({len(over_core)} mon-core across {nb_core} blocks)")
    # list the biggest monetary offenders
    top = sorted(mon, key=lambda r: -r["witness_bytes"])[:25]
    print("\n-- top-25 monetary by witness_bytes --")
    for r in top:
        print(f"     {r['witness_bytes']:>7}B  {r['wit_class']:<22} m_of_n={r['m_of_n']} "
              f"h={r['h']} {str(r['txid'])[:16]}..:{r['vin']}")

    # LN recurrence across independent blocks
    ln = [r for r in mon if r["wit_class"] == "lightning_like"]
    ln_big = [r for r in ln if r["witness_bytes"] >= 1400]
    print(f"\n-- lightning_like: {len(ln)} inputs across {len(set(r['h'] for r in ln))} blocks; "
          f">=1400B: {len(ln_big)} inputs across {len(set(r['h'] for r in ln_big))} DISTINCT blocks --")
    # multisig tail
    mm = [r for r in mon if r["wit_class"] == "p2wsh_multisig"]
    if mm:
        mm_s = sorted(mm, key=lambda r: -r["witness_bytes"])
        print(f"-- p2wsh_multisig: n={len(mm)}, max={mm_s[0]['witness_bytes']}B "
              f"(m_of_n={mm_s[0]['m_of_n']}, h={mm_s[0]['h']}); "
              f"count >800B: {sum(1 for r in mm if r['witness_bytes']>800)} --")
    print("===== END ANALYSIS =====")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=50000, help="min monetary inputs")
    ap.add_argument("--seed", type=int, default=2013)
    ap.add_argument("--tip", type=int, default=0)
    ap.add_argument("--analyze-only", action="store_true")
    a = ap.parse_args()
    if a.analyze_only:
        analyze(str(OUT)); return

    rng = random.Random(a.seed)
    tp = a.tip or ws.tip()
    lo, hi = ws.SEGWIT, tp
    print(f"=== witness re-validation START seed={a.seed} range=[{lo},{hi}] target_monetary={a.target} ===", file=sys.stderr)
    tmp = str(OUT) + ".tmp"
    fh = open(tmp, "w")
    mon = 0; blocks = 0; drawn = set(); t0 = time.time()
    while mon < a.target:
        h = rng.randint(lo, hi)
        if h in drawn:
            continue
        drawn.add(h)
        try:
            bhash = ws.height_to_hash(h)
            blk = ws.get(f"/block/{bhash}")
            tc = int(blk["tx_count"])
            if tc < 2:
                continue
            max_off = ((tc - 1) // PAGE) * PAGE
            off = rng.randrange(0, max_off + 1, PAGE) if max_off > 0 else 0
            txs = ws.get(f"/block/{bhash}/txs/{off}")
        except Exception as e:
            print(f"skip h={h}: {e}", file=sys.stderr)
            time.sleep(0.3)
            continue
        if not isinstance(txs, list):
            continue
        for t in txs:
            txid = t.get("txid")
            for vidx, vin in enumerate(t.get("vin", [])):
                try:
                    r = ws.classify(vin)
                except Exception:
                    continue
                if r is None:
                    continue
                cls, wbytes, ser, nit, mn, annex, nested = r
                if cls == "__legacy__":
                    continue
                m = is_monetary(cls)
                fh.write(json.dumps({"h": h, "txid": txid, "vin": vidx, "wit_class": cls,
                                     "witness_bytes": wbytes, "witness_bytes_serialized": ser,
                                     "m_of_n": mn, "annex": annex, "nested": nested,
                                     "monetary": m}) + "\n")
                if m:
                    mon += 1
        blocks += 1
        if blocks % 100 == 0:
            fh.flush()
            el = int(time.time() - t0)
            print(f"[{el}s] blocks={blocks} monetary={mon}/{a.target} last_h={h}", file=sys.stderr)
        time.sleep(0.15)
    fh.close()
    os.replace(tmp, str(OUT))
    print(f"=== SAMPLING DONE blocks={blocks} monetary={mon} elapsed={int(time.time()-t0)}s -> {OUT} ===", file=sys.stderr)
    analyze(str(OUT))

if __name__ == "__main__":
    main()
