# Opportunity Scoring Engine — Yellow Card

Which businesses need stablecoin payment infrastructure, and which specific
offering answers their problem. Structure-only scoring, public evidence, every
signal sourced.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `localhost:8501`. Python 3.9+.

## Deploy to Streamlit Community Cloud (free)

1. Push this folder to a GitHub repo.
2. Go to share.streamlit.io, sign in with GitHub, click **New app**.
3. Point it at the repo, branch `main`, main file `app.py`.
4. Deploy. You get a public URL in about two minutes.

Nothing to configure — `requirements.txt` and `.streamlit/config.toml` are
already here. The dataset ships in the repo, so there is no database to set up.

**Why Streamlit rather than Vercel:** the scoring engine is Python and Streamlit
runs it natively, so the sidebar weights recompute the whole ranking live.
Vercel would need the engine rewritten in JavaScript for no gain.

## Files

| File | What it is |
|---|---|
| `app.py` | The dashboard. Three views plus method. |
| `scoring_engine.py` | Scoring implementation. Runs standalone too. |
| `scoring_framework_v1.4.json` | The framework itself — tiers, weights, gates, signatures, output categories. |
| `MASTER_dataset.json` | 27 company rows, merged from four batches. |
| `market_table.json` | 35 markets — friction, trajectory, three serviceability fields, blocked-funds flag. |
| `companies_batch0*.json` | Source batches. The master file is generated from these. |
| `scored_output.json` | Last CLI run. |
| `.streamlit/config.toml` | Theme. |

Standalone run:

```bash
python3 scoring_engine.py MASTER_dataset.json > scored_output.json
```

## The formula

```
score = tier1_base × tier2 × tier3 × urgency
```

- **Tier 1** establishes need. Four weighted signals (30/30/20/20), each rated
  0–1 on evidence quality, sorted, then decayed by rank (1.0 / 0.8 / 0.6 / 0.4).
  Decay stops signal-counting from beating genuine need.
- **Tier 2** multiplicative, 1.0–1.4. Supporting signals worsen an existing
  problem, never create one. Counts disclosed FX or dollar-access harm only —
  not financial distress generally.
- **Tier 3** multiplicative, 1.0–1.1. Colour only.
- **Urgency** upward-only. Expanding 1.3; static and pruning 1.0. Sustained
  regional retreat is a disqualifier, not a discount.
- Displayed scores normalise to 100 against the top prospect.

## Output categories

- `prospect` — established need, nothing self-solved
- `prospect_narrow` — soft-capped on some offerings, live on others
- `route_to_partnership` — competes on one layer, could buy rails on another
- `excluded` — hard disqualifier fired, reason always stated
- `no_established_need` — Tier 2/3 signals with no Tier 1 underneath

## Theme

Deep ink base (`#0E1520`) with a muted gold accent (`#E0A33E`). Analytical
tooling rather than marketing site, and the gold nods at the subject without
copying Yellow Card's brand — pitching someone a mock-up in their own colours
reads as presumptuous. Accent is reserved for one job: marking the binding
constraint and narrow-pitch state. Everything else stays quiet.

## Validation

Positive controls are confirmed Yellow Card customers. If they don't rank high,
the framework is wrong, not the companies. Current run: 4/4 positive and 8/8
negative controls hold.

## Open items

1. Ten Tier 1 prospect rows unresearched — see `tier1_queue_remaining` in
   `companies_batch04_prospects.json`.
2. ~40 further prospects from the prospecting universe unresearched.
3. Block/Square positive-control status unverified.
4. **Tala carries a review flag.** It ranks first on structure but already moves
   lending capital over stablecoin rails via "Tala in a Box". Do not pitch it
   Global USD Accounts without checking what that covers.
5. Bank and telco counts are `VERIFY` in every market row. They are the
   institutional opportunity (local stablecoin issuance, custody) and are
   deliberately separate from the corporate prospect list.
6. **Nigeria is off the IATA blocked-funds list.** The flag must not fire for
   Nigeria. It remains high friction for other reasons — the May 2026 FX policy
   lengthens repatriation — but trapped airline revenue is no longer one.
7. The widely-cited "$28m blocked" Kenya Airways figure is from August 2022.
   Current sourced figures: KSh 1.4bn across Nigeria, Malawi, Ethiopia and
   Burundi as at September 2024, plus ~$11.6m in Ethiopia.

## Adding companies

Rows are hand-written JSON. Keep `tier0_flags` keys canonical — the engine
normalises variants, but new spellings need a normaliser update. Every signal
needs `present`, `strength` (0–1) and `source`. No signal scores without a source.

## GitHub sync

Edits made in the app commit straight to the repo when configured. See
`SETUP_GITHUB_SYNC.md` — about five minutes, once. Without it the editor works
but changes stay in the browser session.

The editor sits behind `editor_password` in Streamlit secrets, so anyone you send
the link to can explore every view and move the weights without being able to
change the data.
