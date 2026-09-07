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

LABELS_G = {
    "global_usd_accounts": "Global USD Accounts", "treasury_management": "Treasury management",
    "local_rails": "Local collections and payouts", "fx": "Currency conversion",
    "stablecoin_settlement": "Stablecoin settlement", "api_widget": "Payments API and Widget",
    "wallets_custody": "Wallets and custody",
    "fx_provider_enablement": "Payments API (for onward use)",
}

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
    "Scored on company structure only — markets, currencies, entities. Every signal carries a source."
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
        with st.expander("What the categories mean"):
            st.markdown(
                "- **Prospect** — a real need, nothing already solved. Approach normally.\n"
                "- **Narrow pitch** — needs some offerings but has already solved others itself. "
                "Pitch only what is listed; the rest would be selling something it already has.\n"
                "- **Partnership** — competes on one layer but could use the infrastructure on another. "
                "Approach as a partner, not with a treasury pitch.\n"
                "- **Excluded** — ruled out, with the reason shown on the company.\n"
                "- **No established need** — some supporting signals, but nothing that proves a "
                "cross-border problem exists."
            )

        for r in shown:
            flag = " ⚑" if r["review_flag"]["needs_review"] else ""
            prods = ", ".join(p.get("label", p["product"]) for p in r["recommendations"])
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
                + ", ".join(LABELS_G.get(s, s.replace("_", " ")) for s in r["suppressed_products"])
                + ". Soft caps suppress the products a company has solved for itself — "
                "they don't remove it from the list."
            )

        st.markdown("**Why it scores what it does**")
        if r.get("score_story"):
            st.markdown(f'<div class="why" style="line-height:1.6;">{r["score_story"]}</div>',
                        unsafe_allow_html=True)
            st.markdown("")
        if r["tier1_breakdown"]:
            df = pd.DataFrame(r["tier1_breakdown"])
            df["signal"] = df["signal"].str.replace("tier1_", "").str.replace("_", " ")
            st.dataframe(
                df[["signal", "weight", "strength", "decay", "contribution"]],
                hide_index=True, use_container_width=True,
            )
        comp = r["components"]
        with st.expander("The arithmetic"):
            st.caption(
                f"Base {comp['tier1_base']} × Tier 2 {comp['tier2_modifier']} "
                f"× Tier 3 {comp['tier3_modifier']} × urgency {comp['urgency_multiplier']}. "
                "Weight is how much a signal is worth; strength is how good the evidence is; "
                "decay is the discount applied to each signal after the strongest."
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
    products = sorted({p["product"] for r in rows for p in r["recommendations"]
                       if r["category"] in ("prospect", "prospect_narrow", "route_to_partnership")})
    chosen = st.radio("Offering", products, horizontal=True,
                      format_func=lambda p: LABELS_G.get(p, p.replace("_", " ")))

    ORDER = {"prospect": 0, "prospect_narrow": 1, "route_to_partnership": 2}
    hits = []
    for r in rows:
        if r["category"] not in ORDER:
            continue
        for p in r["recommendations"]:
            if p["product"] == chosen:
                hits.append({
                    "_o": ORDER[r["category"]],
                    "Company": r["company"],
                    "Category": PILL[r["category"]][1],
                    "Score": round(r["score"], 0),
                    "Fit": round(p["score"], 0),
                    "Lead or supporting": "supporting" if p.get("subordinate") else "lead",
                    "Why this company": p["reason"],
                    "_pill": pill(r["category"]),
                })
    hits.sort(key=lambda h: (h["_o"], -h["Fit"], -h["Score"]))
    for h in hits:
        h.pop("_o")

    st.caption(f"{len(hits)} companies to approach — prospects first, then narrow pitch, then "
               f"partnership. Excluded companies are not shown.")
    if not hits:
        st.info("No approachable company matches this offering.")
    for h in hits:
        pos = "" if h["Lead or supporting"] == "lead" else " · supporting"
        st.markdown(
            f'<div class="rowline"><b>{h["Company"]}</b> &nbsp;{h["_pill"]}&nbsp; '
            f'<span class="why">fit {h["Fit"]:.0f} · overall {h["Score"]:.0f}{pos}</span><br>'
            f'<span class="why">{h["Why this company"]}</span></div>',
            unsafe_allow_html=True,
        )

    suppressed_here = [r["company"] for r in rows if chosen in r["suppressed_products"]
                       and r["category"] in ("prospect", "prospect_narrow", "route_to_partnership")]
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

    st.markdown(
        "Each market is scored two ways: how hard it is to move money there, and whether the "
        "infrastructure to serve it exists yet. Those are separate questions — a market can be "
        "difficult *and* well served, or easy and unreachable."
    )
    view = st.radio("View", ["Where demand outruns capability", "All markets"], horizontal=True)
    if view.startswith("Where"):
        gap = md[(md["Friction"] >= 60) & (md["Regulatory"] <= 1)].sort_values("Friction", ascending=False)
        st.markdown(
            "Markets scoring high on friction where there is little or no licence or rail coverage yet. "
            "The demand is real; the ability to serve it is not there. These are expansion signals "
            "rather than places to sell into today."
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
### The question this answers

Which companies have a cross-border money problem that this infrastructure solves — and which part
of it they need.

### How a company gets its score

**First, is it even a candidate?** A company operating in one country with one currency has no
cross-border problem. A subsidiary whose parent sets banking policy overseas cannot buy anything
independently. A company selling the same service to the same customers is a competitor. Any of
these and it is ruled out, with the reason shown.

**Then, is there a real problem?** Four things establish one: recurring cross-border payments,
a standing need for dollars, collecting money across several markets, and owing money in several
currencies. Each is rated on how good the evidence is — a figure in a filing counts for more than
something inferred from a company's website.

Stacking weak signals does not beat one strong one. A company with four faint indicators should not
outrank a company with two clear ones, so later signals count for progressively less.

**Then, how bad is it?** If a company has publicly said currency movements hurt it, that multiplies
the score. It cannot create a problem where none exists — supporting evidence makes an existing
problem worse, nothing more.

Only FX or dollar-access harm counts here. One company in this set has heavy documented trouble —
layoffs, unpaid suppliers, a lawsuit — with no currency component at all. That is the wrong kind of
difficulty and it scores nothing.

**Finally, how urgent?** A company that entered new markets recently has an unsolved problem now.
A company that has been stable for years is not penalised, because assuming it has already solved
things would be a guess. A company retreating from a region is different — it has publicly decided
not to invest there, and it is ruled out.

### Why some companies get a shorter list

A company can have solved part of this itself. One agricultural group in this set runs its own
treasury operations in three countries, so there is no treasury pitch to make — but it still
collects from farmers across dozens of markets in local currency, and that part is unsolved.

Ruling it out entirely would throw away a real opportunity. Pitching it treasury tooling would
waste everyone's time. So the offerings it has already solved are removed and the rest stay.

### Why there are three outcomes rather than two

Some companies compete on one layer and could still use the infrastructure on another. Forcing a
yes-or-no answer would mean either pitching a competitor or discarding a genuine partnership.

### What it does not use

No transaction volumes, no payment counts, no estimates of how much money sits idle. None of that
is public, and guessing would make every number here unarguable. It uses what can be checked:
which markets a company operates in, which currencies come in and go out, how it is structured.

Every signal carries its source. Where the evidence is thin, it says so.

### Does it work?

Four companies in this set are confirmed customers. If the framework is sound, they should rank
high — and they do. Nine more were included specifically because they *should* fail, each for a
different reason, so every rule is visibly doing something.

Move the weights in the sidebar and watch whether that still holds.
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
