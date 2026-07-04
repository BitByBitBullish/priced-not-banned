# Priced, Not Banned — a middle-ground Bitcoin data proposal

A two-part proposal for Bitcoin's arbitrary-data fight: **cap the SegWit witness discount at the first 2,000 bytes per input** (money keeps its discount, bulk data past the cap pays full price), and **pair it with a discardable data lane** so data that only needs a commitment lives somewhere nodes never have to store. Nothing becomes invalid, no coin can be frozen, and no rule ever reads a byte's meaning — the line is drawn on *size and price only*. The threshold is measured, not asserted: across 439,000+ randomly sampled real transaction inputs, not one genuine monetary spend in the independent draw exceeds 2,000 bytes.

**Announcement:** https://x.com/bitbybitbullish/status/2073465112820682934

## Read this first
- **[witness-cap-proposal.md](witness-cap-proposal.md)** — the full, fact-checked proposal (the technical paper).
- **[EXPLAINER.md](EXPLAINER.md)** — the plain-language version ("the fight in one minute").

## Author
**BitByBitBullish.** Concept by the author; developed and drafted with AI assistance. The author also builds ₿itcoin Radar — which stays neutral in this debate; this proposal is personal (see the paper's "A Note from the Author").

## Reproduce the numbers
Every figure comes from two seeded, independent studies over public on-chain data (source: the mempool.space public API — no node or credentials required).

```
# Study 1 — stratified cluster sample (SEED=110): 90 blocks across 3 eras + 10 inscription-heavy
scripts/run_witness_study.sh 20260703-221946

# Study 2 — independent non-cluster draw (seed=2013): 751 distinct blocks, one tx-page each
python3 scripts/witness_revalidate.py --seed 2013
```

- **Seeds:** `SEED=110` (Study 1), `seed=2013` (Study 2) — same seed + same tip reproduces the identical block set.
- **[scripts/](scripts/)** — `witness_study.py` (sampler + byte-exact witness math + self-test), `witness_analyze.py` (percentile/subsidy tables), `witness_revalidate.py` (independent draw), `run_witness_study.sh`.
- **[reports/](reports/)** — the exact report outputs both studies produced.
- **[data/](data/)** — per-input datasets, gzipped: `inputs.jsonl.gz` (Study 1), `revalidate_inputs.jsonl.gz` (Study 2). Each row is one input's block height, txid, class, and witness byte count — all public blockchain data.

## License
- **Scripts** (`scripts/`): MIT — see [LICENSE](LICENSE).
- **Paper & explainer** (`witness-cap-proposal.md`, `EXPLAINER.md`): CC-BY 4.0 — reuse and adapt freely, **credit required** (credit for the concept is all that is asked).

Corrections are welcome and will be credited.
