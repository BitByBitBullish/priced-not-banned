#!/usr/bin/env python3
"""
witness_study.py — Empirical per-input witness-size sampler + classifier.

Purpose: measure the distribution of witness bytes per input across Bitcoin
history, segmented by input CLASS and ERA, to support a protocol proposal
(per-input capped witness discount). Central claim under test:
  "the first N bytes of witness per input cover ~99.99% of all signature-
   bearing (monetary) inputs, while inscription/data inputs blow past N."

Source of truth: mempool.space public API. Witness bytes are computed EXACTLY
from raw hex (len(hex)//2 per witness stack item) — never estimated.

Reproducibility: block selection is seeded (SEED). Anyone re-running with the
same seed + same era anchors + same TIP samples the identical block set (Era C's
pool extends to the chain tip, so tip is part of the reproducibility key; it is
recorded in blocks_selected.json and can be pinned with --tip). random.sample
ordering is stable within a CPython major version.

Witness size is reported two ways per input:
  witness_bytes            = sum of witness stack-item DATA bytes (len(hex)//2).
  witness_bytes_serialized = data bytes + item-count compactSize + per-item
                             length-prefix compactSizes (the on-wire witness
                             size that consumes block weight). Multi-item
                             witnesses (multisig/LN/script-path) carry more
                             prefix overhead than single-item ones, so the two
                             differ by a class-dependent amount. Tables key on
                             witness_bytes unless stated; serialized is persisted
                             so a cap defined on either can be evaluated.

CLASS -> BUCKET mapping (documented; analyzer uses this):
  MONETARY (signature-bearing money movement):
    p2wpkh_singlesig      v0_p2wpkh, 2-item [sig,pubkey]
    p2tr_keypath          v1_p2tr, 1 effective item [schnorr sig]
    p2wsh_multisig        v0_p2wsh, witnessScript ends OP_CHECKMULTISIG
    lightning_like        v0_p2wsh, witnessScript uses OP_CSV (heuristic)
  MONETARY-ish (contract spends, kept SEPARATE for bucketing):
    p2wsh_other           v0_p2wsh, non-multisig non-CSV script
    p2tr_scriptpath_other v1_p2tr script-path, NO inscription envelope
  DATA:
    taproot_inscription   v1_p2tr script-path, tapscript has ord envelope
  other / __legacy__      non-segwit or unclassifiable (counted, not bucketed)

NOTE (heuristics, honest): lightning_like and multisig M/N detection use
byte-pattern matching on the witnessScript hex; a pushed pubkey could in
principle contain a matching opcode byte, so these two classes are
conservative heuristics, not consensus-exact parses. p2wpkh/p2tr_keypath/
inscription-envelope detection are structurally exact. All raw fields are
persisted so a reviewer can re-derive every class independently.
"""
import sys, os, json, time, random, argparse, urllib.request, urllib.error, http.client
from datetime import datetime, timezone
from pathlib import Path

# Data directory (self-contained for public release): override with WITNESS_DATA_DIR.
_DATA_ROOT = Path(os.environ.get("WITNESS_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))

API = "https://mempool.space/api"
SEED = 110  # reproducible block selection

# Well-known activation heights (era anchors).
SEGWIT   = 481824   # 2017-08-24 SegWit active
TAPROOT  = 709632   # 2021-11-14 Taproot active
INSCRIPT = 767000   # round anchor just BEFORE inscription 0 (block 767430,
                    # 2022-12-14). Blocks 767000-767429 carry no inscriptions,
                    # so Era C's leading ~430 blocks are inscription-free by
                    # construction; this dilutes nothing (they simply contain 0
                    # data-class inputs) and keeps the anchor a memorable round #.

DATA_DIR = str(_DATA_ROOT)

def get(path, tries=4):
    url = API + path
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "witness-study/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read()
                ct = r.headers.get("Content-Type", "")
                if "json" in ct or body[:1] in (b"{", b"["):
                    return json.loads(body)
                return body.decode().strip()
        except (OSError, ValueError, http.client.HTTPException) as e:
            last = e
            time.sleep(0.4 * (i + 1))
    raise RuntimeError(f"GET {path} failed after {tries}: {last}")

def tip():
    return int(get("/blocks/tip/height"))

def height_to_hash(h):
    return get(f"/block-height/{h}")

def block_txs(bhash):
    """Yield every tx (with per-input witness) in a block, paginating by the
    block's actual tx_count. Bounding on tx_count (not '<25 => done') avoids the
    mempool.space 4xx that occurs when idx lands exactly on tx_count — which
    happens whenever tx_count is a multiple of 25 and would otherwise crash the
    run 4 retries later."""
    blk = get(f"/block/{bhash}")
    tc = int(blk["tx_count"])
    if tc < 1:
        raise RuntimeError(f"block {bhash}: implausible tx_count={tc}")
    idx = 0
    while idx < tc:
        txs = get(f"/block/{bhash}/txs/{idx}")
        if not isinstance(txs, list) or not txs:
            raise RuntimeError(f"block {bhash}: bad txs page at idx={idx} of {tc}: {txs!r:.80}")
        for t in txs:
            yield t
        idx += len(txs)
        if idx < tc:
            time.sleep(0.15)  # ~6 req/s, measured-safe

# ---- classification -------------------------------------------------------

def _cs_len(n):
    """Serialized byte length of a Bitcoin compactSize encoding of n."""
    if n < 0xfd:        return 1
    if n <= 0xffff:     return 3
    if n <= 0xffffffff: return 5
    return 9

def _is_inscription(tapscript_hex):
    # envelope must be CONTIGUOUS and byte-aligned: OP_FALSE(00) OP_IF(63)
    # OP_PUSHBYTES_3(03) "ord"(6f7264) == 0063036f7264. Independent/unaligned
    # substring tests spuriously matched random pubkey bytes; require the exact
    # 6-byte sequence at an even (byte) offset.
    h = (tapscript_hex or "").lower()
    i = h.find("0063036f7264")
    while i >= 0:
        if i % 2 == 0:
            return True
        i = h.find("0063036f7264", i + 1)
    return False

def _opcodes(script_hex):
    """Tokenize a Bitcoin script into (opcode_byte, data_len) pairs, walking push
    structure so opcode-valued bytes INSIDE pushed data (pubkeys, hashes) are not
    mistaken for real opcodes. Returns None on malformed/truncated script."""
    try:
        b = bytes.fromhex(script_hex)
    except ValueError:
        return None
    ops = []; i = 0; n = len(b)
    while i < n:
        op = b[i]; i += 1
        dlen = 0
        if 1 <= op <= 0x4b:
            dlen = op
        elif op == 0x4c:
            if i >= n: return None
            dlen = b[i]; i += 1
        elif op == 0x4d:
            if i + 1 >= n: return None
            dlen = b[i] | (b[i + 1] << 8); i += 2
        elif op == 0x4e:
            if i + 3 >= n: return None
            dlen = b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24); i += 4
        if dlen:
            if i + dlen > n: return None   # truncated push
            i += dlen
            ops.append((op, dlen))
        else:
            ops.append((op, 0))
    return ops

def _classify_wsh(script_hex):
    """Return (class, m_of_n) for a v0_p2wsh witnessScript (hex). Uses an opcode
    walk (not substring matching), so 0xae/0xaf/0xb2 bytes inside pushed pubkeys
    cannot spoof a multisig or CSV match."""
    if not script_hex:
        return ("p2wsh_other", None)
    ops = _opcodes(script_hex)
    if ops is None:
        return ("p2wsh_other", None)
    # bare multisig: OP_M <pk>..<pk> OP_N OP_CHECKMULTISIG[VERIFY], last two are
    # real opcodes, M and N both OP_1..OP_16.
    if len(ops) >= 3 and ops[-1][1] == 0 and ops[-1][0] in (0xae, 0xaf) and ops[-2][1] == 0:
        first, nth = ops[0][0], ops[-2][0]
        if 0x51 <= first <= 0x60 and 0x51 <= nth <= 0x60:
            m, nn = first - 0x50, nth - 0x50
            if 1 <= m <= nn <= 16:
                return ("p2wsh_multisig", f"{m}of{nn}")
    # CSV-timelocked contract (Lightning-ish): OP_CHECKSEQUENCEVERIFY(0xb2) present
    # as a real opcode. Heuristic label; see docstring.
    if any(op == 0xb2 and dl == 0 for op, dl in ops):
        return ("lightning_like", None)
    return ("p2wsh_other", None)

def classify(vin):
    """Return (wit_class, witness_bytes, ser_bytes, n_items, m_of_n, annex, nested)
    or None to skip. '__legacy__' class = non-segwit input (no witness); counted,
    not bucketed. `nested`=True marks P2SH-wrapped SegWit (redeemScript in the
    scriptSig); such inputs are ordinary signature-bearing money and carry the
    SAME witness bytes as their native equivalents, so they are labelled with the
    native class (p2wpkh_singlesig / p2wsh_*) and flagged nested for transparency."""
    if vin.get("is_coinbase"):
        return None
    w = [x.lower() for x in (vin.get("witness") or [])]
    wbytes = sum(len(h) // 2 for h in w)
    ser = (wbytes + _cs_len(len(w)) + sum(_cs_len(len(h) // 2) for h in w)) if w else 0
    n = len(w)
    ptype = (vin.get("prevout") or {}).get("scriptpubkey_type")
    m_of_n = None
    annex = False
    nested = False
    if not w and ptype in ("v0_p2wpkh", "v0_p2wsh", "v1_p2tr"):
        raise RuntimeError(f"segwit prevout {ptype} with empty witness — API response corrupt")
    eff = w

    if ptype == "v1_p2tr" and n > 1 and w[-1][:2] == "50":
        annex = True
        eff = w[:-1]
    n_eff = len(eff)

    if ptype == "v0_p2wpkh":
        cls = "p2wpkh_singlesig"
    elif ptype == "v1_p2tr":
        if n_eff == 1:
            cls = "p2tr_keypath"
        elif n_eff >= 2:
            cb = eff[-1]
            if cb[:2] in ("c0", "c1"):
                tapscript = eff[-2]
                cls = "taproot_inscription" if _is_inscription(tapscript) else "p2tr_scriptpath_other"
            else:
                cls = "p2tr_scriptpath_other"
        else:
            cls = "other"
    elif ptype == "v0_p2wsh":
        cls, m_of_n = _classify_wsh(eff[-1] if eff else "")
    elif ptype == "p2sh" and w:
        # nested SegWit: the redeemScript (a witness-program push) sits in the
        # scriptSig. 160014<20B> => P2WPKH program; 220020<32B> => P2WSH program.
        ss = (vin.get("scriptsig") or "").lower()
        if ss[:6] == "160014":
            cls = "p2wpkh_singlesig"; nested = True
        elif ss[:6] == "220020":
            cls, m_of_n = _classify_wsh(w[-1] if w else ""); nested = True
        else:
            cls = "other"
    elif not w:
        return ("__legacy__", wbytes, ser, 0, None, False, False)
    else:
        cls = "other"
    return (cls, wbytes, ser, n, m_of_n, annex, nested)

# ---- sampling -------------------------------------------------------------

def select_blocks(rng, per_era, tp):
    sel = []
    for era, lo, hi in [("A", SEGWIT, TAPROOT), ("B", TAPROOT, INSCRIPT), ("C", INSCRIPT, tp + 1)]:
        pool = range(lo, hi)
        chosen = rng.sample(list(pool), min(per_era, hi - lo))
        sel += [(h, era) for h in chosen]
    return sel

def pick_heavy(rng, n_heavy, tp, exclude):
    """Pre-scan ~40 candidate Era-C blocks, rank by taproot_inscription bytes, take top n_heavy."""
    if n_heavy <= 0:
        return []
    cands = [h for h in rng.sample(range(INSCRIPT, tp + 1), min(40, tp + 1 - INSCRIPT)) if h not in exclude]
    scored = []
    for i, h in enumerate(cands):
        bhash = height_to_hash(h)
        insc = 0
        for tx in block_txs(bhash):
            for vin in tx.get("vin", []):
                c = classify(vin)
                if c and c[0] == "taproot_inscription":
                    insc += c[1]
        scored.append((insc, h))
        print(f"  heavy-scan {i+1}/{len(cands)} h={h} insc_bytes={insc}", file=sys.stderr)
    scored.sort(reverse=True)
    return [(h, "C_heavy") for _, h in scored[:n_heavy]]

def process_block(h, era, fh):
    bhash = height_to_hash(h)
    tally = {"inputs": 0, "legacy": 0}
    for tx in block_txs(bhash):
        txid = tx.get("txid")
        for vi, vin in enumerate(tx.get("vin", [])):
            c = classify(vin)
            if c is None:
                continue
            cls, wbytes, ser, nit, mn, annex, nested = c
            if cls == "__legacy__":
                tally["legacy"] += 1
                continue
            rec = {"height": h, "era": era, "txid": txid, "vin": vi,
                   "prevout_type": (vin.get("prevout") or {}).get("scriptpubkey_type"),
                   "wit_class": cls, "witness_bytes": wbytes,
                   "witness_bytes_serialized": ser, "n_items": nit,
                   "m_of_n": mn, "annex": annex, "nested": nested}
            fh.write(json.dumps(rec) + "\n")
            tally["inputs"] += 1
    return tally

def selftest():
    tp = tip()
    bhash = height_to_hash(tp - 3)
    # byte-math must be checked on a REAL witness-bearing input, not the coinbase
    # (which classify() skips) — the coinbase made the old assert vacuous.
    target = None
    for tx in block_txs(bhash):
        for vin in tx.get("vin", []):
            if not vin.get("is_coinbase") and vin.get("witness"):
                target = tx; break
        if target:
            break
    assert target is not None, "no witness-bearing tx found for selftest"
    ok = 0
    for vin in target.get("vin", []):
        w = vin.get("witness") or []
        manual = sum(len(h) // 2 for h in w)
        c = classify(vin)
        assert c is None or c[1] == manual, f"byte mismatch {c}"
        if c is not None:
            ok += 1
    assert ok >= 1, "selftest verified 0 witness inputs"
    # hand-computed byte vector (independent of classify's own formula): a 72B sig
    # + 33B pubkey p2wpkh spend => witness_bytes 105; serialized = 105 + cs(2 items)=1
    # + cs(72)=1 + cs(33)=1 = 108. Guards _cs_len + the serialization math directly.
    v = classify({"witness": ["aa" * 72, "bb" * 33],
                  "prevout": {"scriptpubkey_type": "v0_p2wpkh"}})
    assert v[:4] == ("p2wpkh_singlesig", 105, 108, 2), v
    assert _cs_len(0xfc) == 1 and _cs_len(0xfd) == 3 and _cs_len(0x10000) == 5
    # inscription envelope detector sanity (contiguous + byte-aligned)
    assert _is_inscription("0063036f726401") is True
    assert _is_inscription("2001aabbcc") is False
    assert _is_inscription("abc" + "0063036f7264") is False   # odd-offset rejected
    # multisig parse sanity: real 2-of-3 skeleton 52 <pk><pk><pk> 53 ae
    m = _classify_wsh("5221" + "aa"*33 + "21" + "bb"*33 + "21" + "cc"*33 + "53ae")
    assert m == ("p2wsh_multisig", "2of3"), m
    print(f"SELFTEST OK: byte-math verified on {ok} witness inputs of tx {target.get('txid')[:16]}..; "
          f"inscription+multisig detectors pass", file=sys.stderr)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks-per-era", type=int, default=30)
    ap.add_argument("--heavy", type=int, default=10)
    ap.add_argument("--tip", type=int, default=0, help="pin tip height for reproducible Era-C sampling (0=live)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    os.makedirs(DATA_DIR, exist_ok=True)
    rng = random.Random(SEED)
    tp = a.tip if a.tip else tip()
    print(f"tip={tp} seed={SEED} per_era={a.blocks_per_era} heavy={a.heavy}", file=sys.stderr)
    blocks = select_blocks(rng, a.blocks_per_era, tp)
    heavy = pick_heavy(rng, a.heavy, tp, {h for h, _ in blocks})
    blocks += heavy
    meta = {"generated_utc": datetime.now(timezone.utc).isoformat(), "seed": SEED,
            "tip": tp, "blocks_per_era": a.blocks_per_era, "heavy": a.heavy,
            "anchors": {"segwit": SEGWIT, "taproot": TAPROOT, "inscription": INSCRIPT},
            "blocks": [{"height": h, "era": e} for h, e in blocks]}
    with open(os.path.join(DATA_DIR, "blocks_selected.json"), "w") as f:
        json.dump(meta, f, indent=2)
    out = os.path.join(DATA_DIR, "inputs.jsonl")
    tmp = out + ".tmp"
    total = {"inputs": 0, "legacy": 0}
    with open(tmp, "w") as fh:
        for i, (h, era) in enumerate(blocks):
            t = process_block(h, era, fh)
            total["inputs"] += t["inputs"]; total["legacy"] += t["legacy"]
            print(f"[{i+1}/{len(blocks)}] h={h} era={era} inputs={t['inputs']} legacy={t['legacy']}", file=sys.stderr)
    os.replace(tmp, out)   # atomic: a partial run never masquerades as a complete inputs.jsonl
    print(f"DONE inputs={total['inputs']} legacy_skipped={total['legacy']} -> {out}", file=sys.stderr)

if __name__ == "__main__":
    main()
