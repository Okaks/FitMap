import json
from pathlib import Path

import pandas as pd
import streamlit as st

import scoring_engine as eng

DATA = Path(__file__).parent

st.set_page_config(
    page_title="FitMap",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; max-width: 1400px;}
  h1, h2, h3 {letter-spacing: -0.015em;}
  .lede {color: #8FA3BF; font-size: 0.95rem; line-height: 1.6; max-width: 68ch;}
  .pill {display:inline-block; padding:2px 9px; border-radius:3px; font-size:0.74rem;
         font-weight:600; letter-spacing:0.02em;}
  .p-prospect {background:#1C3A2E; color:#6ADFA0;}
  .p-narrow   {background:#3A3520; color:#E0A33E;}
  .p-partner  {background:#1F3348; color:#7FB3E8;}
  .p-excluded {background:#3A2323; color:#E88C8C;}
  .p-none     {background:#262E3A; color:#8FA3BF;}
  .rowline {border-bottom:1px solid #1E2836; padding:0.55rem 0;}
  .why {color:#8FA3BF; font-size:0.85rem;}
  .constraint {color:#E0A33E; font-weight:600;}
  [data-testid="stMetricValue"] {font-size: 1.65rem;}
</style>
""", unsafe_allow_html=True)

PILL = {
    "prospect": ("p-prospect", "Prospect"),
    "prospect_narrow": ("p-narrow", "Narrow pitch"),
    "route_to_partnership": ("p-partner", "Partnership"),
    "excluded": ("p-excluded", "Excluded"),
    "no_established_need": ("p-none", "No established need"),
}


def pill(cat):
    cls, label = PILL.get(cat, ("p-none", cat))
    return f'<span class="pill {cls}">{label}</span>'


@st.cache_data
def load_dataset():
    return json.loads((DATA / "MASTER_dataset.json").read_text())["companies"]


@st.cache_data
def load_markets():
    return json.loads((DATA / "market_table.json").read_text())


def run_scoring(w_cbp, w_usd, w_coll, w_curr, decay, t2_ceiling, urg_expand):
    eng.TIER1_WEIGHTS.update({
        "tier1_cross_border_payments": w_cbp,
        "tier1_usd_liquidity": w_usd,
        "tier1_multi_market_collection": w_coll,
        "tier1_multi_currency_obligations": w_curr,
    })
    eng.DECAY_LADDER[:] = decay
    eng.TIER2_RANGE = (1.0, t2_ceiling)
    eng.URGENCY["expanding"] = urg_expand

    rows = [eng.score_company(json.loads(json.dumps(c))) for c in load_dataset()]
    rows = eng.normalise(rows)
    rows.sort(key=lambda r: -r["raw_score"])
    return rows, eng.validate(rows)


# ---------------------------------------------------------------- sidebar

st.sidebar.markdown("### Scoring weights")
st.sidebar.caption("Change these and the ranking recomputes. Every score below is built from them.")

w_cbp = st.sidebar.slider("Recurring cross-border payments", 0, 50, 30)
w_usd = st.sidebar.slider("Persistent USD liquidity requirement", 0, 50, 30)
w_coll = st.sidebar.slider("Multi-market local collection", 0, 50, 20)
w_curr = st.sidebar.slider("Recurring multi-currency obligations", 0, 50, 20)

st.sidebar.markdown("---")
ladder = st.sidebar.select_slider(
    "Decay across stacked signals",
    options=["sharp", "moderate", "flat"],
    value="sharp",
    help="How much a company's second, third and fourth signals count. Sharp forces separation at the top of the ranking.",
)
DECAY = {"sharp": [1.0, 0.8, 0.6, 0.4], "moderate": [1.0, 0.85, 0.7, 0.55], "flat": [1.0, 0.9, 0.8, 0.7]}[ladder]

t2_ceiling = st.sidebar.slider("Tier 2 ceiling", 1.0, 2.0, 1.4, 0.05,
                               help="How far disclosed FX pain can amplify an established need.")
urg_expand = st.sidebar.slider("Urgency: expanding", 1.0, 2.0, 1.3, 0.05,
                               help="Applied to companies that entered a market recently. Never below 1.0 — retreat is a disqualifier, not a discount.")

st.sidebar.markdown("---")
st.sidebar.caption(
    "Structure only. No payment volumes, transaction counts or idle-balance "
    "estimates — structure is verifiable, volume is not. Every signal carries a source."
)

rows, validation = run_scoring(w_cbp, w_usd, w_coll, w_curr, DECAY, t2_ceiling, urg_expand)
by_name = {r["company"]: r for r in rows}
dataset = {c["identity"]["trading_name"]: c for c in load_dataset()}

# ---------------------------------------------------------------- header

st.title("Who needs this infrastructure, and which part of it")
st.markdown(
    '<p class="lede">A scoring framework for identifying businesses whose money movement '
    'points at stablecoin payment infrastructure — matched to the specific offering that answers it. '
    'Built from public structural evidence only.</p>',
    unsafe_allow_html=True,
)

pos_pass = sum(1 for p in validation["positive_controls"] if p["passes"])
neg_pass = sum(1 for p in validation["negative_controls"] if p["passes"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Companies scored", len(rows))
c2.metric("Known customers ranking high", f"{pos_pass}/{len(validation['positive_controls'])}")
c3.metric("Negative controls held", f"{neg_pass}/{len(validation['negative_controls'])}")
c4.metric("Markets assessed", len(load_markets()["markets"]))

tab_co, tab_prod, tab_mkt, tab_method = st.tabs(
    ["Companies", "By offering", "Markets", "How this works"]
)

# ---------------------------------------------------------------- companies

with tab_co:
    left, right = st.columns([1, 1.15], gap="large")

    with left:
        cats = st.multiselect(
            "Show",
            list(PILL.keys()),
            default=["prospect", "prospect_narrow"],
            format_func=lambda k: PILL[k][1],
        )
        shown = [r for r in rows if r["category"] in cats]
        st.caption(f"{len(shown)} companies")

        for r in shown:
            flag = " ⚑" if r["review_flag"]["needs_review"] else ""
            prods = ", ".join(p["product"].replace("_", " ") for p in r["recommendations"])
            st.markdown(
                f'<div class="rowline"><b>{r["score"]:.0f}</b> &nbsp; {r["company"]}{flag} '
                f'&nbsp; {pill(r["category"])}<br><span class="why">{prods}</span></div>',
                unsafe_allow_html=True,
            )

    with right:
        pick = st.selectbox("Open a company", [r["company"] for r in rows])
        r = by_name[pick]
        raw = dataset.get(pick, {})

        st.markdown(f"### {pick} &nbsp; {pill(r['category'])}", unsafe_allow_html=True)
        st.caption(r.get("sector") or "")

        if r["review_flag"]["needs_review"]:
            st.warning(f"**Check before pitching.** {r['review_flag']['reason']}")

        if r["hard_disqualifiers"]:
            for h in r["hard_disqualifiers"]:
                st.error(f"**Excluded — {h['rule'].replace('_',' ')}.** {h['reason']}")
            note = raw.get("tier0_flags", {}).get("tier0_note")
            if note:
                st.caption(note)

        m1, m2, m3 = st.columns(3)
        m1.metric("Score", f"{r['score']:.0f}")
        m2.metric("Evidence", r["evidence_depth"])
        m3.metric("Trajectory", r["components"]["urgency_state"])

        if r["recommendations"]:
            actionable = r["category"] in ("prospect", "prospect_narrow", "route_to_partnership")
            if actionable:
                st.markdown("**What to pitch**")
            else:
                st.markdown("**Products this company's profile matches**")
                st.caption(
                    "Shown for diagnosis, not for outreach. The exclusion above stands regardless of "
                    "how strongly these fire — that is the gate beating the score."
                    if r["category"] == "excluded" else
                    "Shown for diagnosis, not for outreach. No Tier 1 signal establishes need, so these "
                    "matches sit on supporting evidence alone."
                )
            for i, p in enumerate(r["recommendations"]):
                if actionable:
                    tag = " · supporting" if p.get("subordinate") else (" · lead" if i == 0 else "")
                else:
                    tag = f' · matches at {p["score"]:.0f}'
                st.markdown(
                    f'<div class="rowline"><b>{p["product"].replace("_"," ")}</b>{tag}<br>'
                    f'<span class="why">{p["reason"]}</span></div>',
                    unsafe_allow_html=True,
                )

        if r["suppressed_products"] and r["category"] in ("prospect", "prospect_narrow",
                                                          "route_to_partnership"):
            st.info(
                "**Already solved, don't pitch:** "
                + ", ".join(s.replace("_", " ") for s in r["suppressed_products"])
                + ". Soft caps suppress the products a company has solved for itself — "
                "they don't remove it from the list."
            )

        st.markdown("**Why it scores what it does**")
        if r["tier1_breakdown"]:
            df = pd.DataFrame(r["tier1_breakdown"])
            df["signal"] = df["signal"].str.replace("tier1_", "").str.replace("_", " ")
            st.dataframe(
                df[["signal", "weight", "strength", "decay", "contribution"]],
                hide_index=True, use_container_width=True,
            )
        comp = r["components"]
        st.caption(
            f"Base {comp['tier1_base']} × Tier 2 {comp['tier2_modifier']} "
            f"× Tier 3 {comp['tier3_modifier']} × urgency {comp['urgency_multiplier']}"
        )

        for key in ["tier2_disclosed_pain"]:
            sig = raw.get("signals", {}).get(key)
            if isinstance(sig, dict) and sig.get("present"):
                st.markdown("**Disclosed pain**")
                st.caption(sig.get("source", ""))

        if r["blocked_funds_flag"]["fires"]:
            st.markdown("**Blocked funds**")
            st.caption(
                "Operates in " + ", ".join(r["blocked_funds_flag"]["countries"])
                + " — on the IATA blocked-funds list. Third-party documented, not self-reported."
            )

# ---------------------------------------------------------------- products

with tab_prod:
    st.markdown("Pick an offering to see which companies its signature fires for, strongest first.")
    products = sorted({p["product"] for r in rows for p in r["recommendations"]})
    chosen = st.radio("Offering", products, horizontal=True,
                      format_func=lambda p: p.replace("_", " "))

    hits = []
    for r in rows:
        for p in r["recommendations"]:
            if p["product"] == chosen:
                hits.append({
                    "Company": r["company"],
                    "Score": round(r["score"], 0),
                    "Fit": round(p["score"], 0),
                    "Position": "supporting" if p.get("subordinate") else "lead",
                    "Category": PILL[r["category"]][1],
                    "Why": p["reason"],
                })
    hits.sort(key=lambda h: -h["Fit"])
    st.caption(f"{len(hits)} companies")
    st.dataframe(pd.DataFrame(hits), hide_index=True, use_container_width=True)

    suppressed_here = [r["company"] for r in rows if chosen in r["suppressed_products"]]
    if suppressed_here:
        st.info(
            f"**Suppressed for {len(suppressed_here)} companies** that have already solved this "
            f"themselves: {', '.join(suppressed_here)}. They remain prospects for other offerings."
        )

# ---------------------------------------------------------------- markets

with tab_mkt:
    mk = load_markets()
    md = pd.DataFrame([{
        "Country": m["country"],
        "Region": m["region"],
        "Presence": m["yc_status"],
        "Friction": m["friction"]["score"],
        "Trajectory": m.get("trajectory", ""),
        "Regulatory": m.get("regulatory", 0),
        "Rails": m.get("rails", 0),
        "Partners": m.get("partners", 0),
        "Blocked funds": "yes" if m.get("blocked_funds") else "",
        "Binding constraint": m.get("binding_constraint", ""),
    } for m in mk["markets"]])

    view = st.radio("View", ["Gap: demand against capability", "All markets"], horizontal=True)
    if view.startswith("Gap"):
        gap = md[(md["Friction"] >= 60) & (md["Regulatory"] <= 1)].sort_values("Friction", ascending=False)
        st.markdown(
            "Markets where friction is high and the provider has little or no regulatory footing. "
            "These are expansion signals, not sales targets — the constraint is capability, not demand."
        )
        st.dataframe(gap, hide_index=True, use_container_width=True)
    else:
        st.dataframe(md.sort_values("Friction", ascending=False), hide_index=True, use_container_width=True)

    st.markdown("---")
    pickm = st.selectbox("Open a market", [m["country"] for m in mk["markets"]])
    m = next(x for x in mk["markets"] if x["country"] == pickm)
    a, b, c = st.columns(3)
    a.metric("Friction", m["friction"]["score"])
    b.metric("Trajectory", m.get("trajectory", "—"))
    c.metric("Blocked funds", "yes" if m.get("blocked_funds") else "no")

    st.markdown(
        f'Binding constraint: <span class="constraint">{m.get("binding_constraint","—")}</span>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Regulatory, rails and partner coverage are scored separately because they fail "
        "independently. A licence with no rails is a build problem; rails with no licence is a legal one."
    )
    f = m["friction"]
    st.dataframe(pd.DataFrame([{
        "FX volatility": f["fx_volatility"], "Dollar access": f["dollar_access"],
        "Rail fragmentation": f["rail_fragmentation"], "Settlement friction": f["settlement_friction"],
    }]), hide_index=True, use_container_width=True)

    for k in ["trajectory_note", "evidence", "expansion_signal", "note"]:
        if m.get(k):
            st.markdown(f"**{k.replace('_',' ').capitalize()}**")
            st.caption(m[k])

    st.caption(
        "Bank and telco counts are not yet verified for any market. They belong here as a separate "
        "institutional opportunity — local stablecoin issuance and custody are a different sale from "
        "the corporate treasury pitch, and mixing them would flatten both."
    )

# ---------------------------------------------------------------- method

with tab_method:
    st.markdown("""
### The formula

    score = tier 1 base × tier 2 × tier 3 × urgency

**Tier 1 establishes that a problem exists.** Four signals, weighted, each rated 0–1 on how good
the evidence is, then sorted and decayed by rank. The decay is the point: a company that hits all
four signals weakly should not outrank one that hits two of them strongly. Without it, the model
rewards signal-counting instead of need.

**Tier 2 is multiplicative, not additive.** Supporting signals make an existing problem worse; they
cannot create one. If they were additive, a company with no real cross-border problem could
accumulate its way into the top ten.

Tier 2 counts *disclosed foreign-exchange or dollar-access harm* — an FX loss, a devaluation impact,
a stated hard-currency shortage, a repatriation problem. It does not count financial distress
generally. One company in this set has heavy documented distress — layoffs, unpaid vendors, a
supplier lawsuit — with no FX component at all. A model keying on "financial difficulty" would score
that as pain. It is the wrong kind entirely.

**Urgency only ever multiplies upward.** A company that entered three markets this year has an
unsolved problem now. A company that has been static for a decade is not penalised, because
"they've already solved it" is an inference, not evidence. Sustained regional retreat is different —
that is a company publicly deciding not to invest, and it is a disqualifier rather than a discount.

### Soft caps suppress products, not companies

The first version of this excluded any company with a mature treasury. That was wrong, and one row
proves it: an agricultural trading group operating across dozens of markets, procuring from
smallholders in soft currency against dollar export receipts. Every structural signal fires at
maximum — and it runs its own treasury companies in three offshore jurisdictions.

The treasury pitch is dead there. Collection and payout rails across those markets are not.
Suppressing the solved products and keeping the rest turns an exclusion into a correctly-scoped
pitch. A scraper puts that company in the top five. A blanket cap throws it away. Neither is right.

### Three outcomes, not two

Some companies are neither prospects nor exclusions. A payments company can compete on one layer
and still buy rails on another — that is precisely what Coinbase does. Forcing a binary choice
means either pitching treasury to a competitor or discarding a real partnership.

### Structure only

No payment volumes, transaction counts, or estimates of idle capital. Those aren't publicly
available and guessing at them would make every number in here unfalsifiable. Structure — which
markets, which currencies in, which currencies out, what entity shape — is verifiable, and it is
what the products actually key on.

Every signal carries a source. Where evidence is thin it is flagged rather than hidden.
Companies with no Tier 1 signal appear in their own category instead of being deleted, so the
floor rule can be judged rather than trusted.

### Validation
""")
    st.dataframe(pd.DataFrame(validation["positive_controls"]), hide_index=True, use_container_width=True)
    st.caption(
        "These are confirmed customers. If they don't rank high, the framework is wrong — "
        "not the companies. Move the weights in the sidebar and watch whether they hold."
    )
    st.dataframe(pd.DataFrame(validation["negative_controls"]), hide_index=True, use_container_width=True)
    st.caption(
        "Each negative control fails for one specific reason, so every rule is visibly doing work. "
        "The hardest of them has publicly stated FX pain and still isn't a customer — it supplies "
        "dollar liquidity rather than buying it."
    )