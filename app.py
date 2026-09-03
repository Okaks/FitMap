import json
from pathlib import Path

import pandas as pd
import streamlit as st

import scoring_engine as eng
import github_sync

DATA = Path(__file__).parent

st.set_page_config(
    page_title="Opportunity Scoring — Yellow Card",
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
def load_dataset_from_disk():
    return json.loads((DATA / "MASTER_dataset.json").read_text())["companies"]


def load_dataset():
    if "companies" not in st.session_state:
        st.session_state.companies = json.loads(json.dumps(load_dataset_from_disk()))
    return st.session_state.companies


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

tab_co, tab_prod, tab_mkt, tab_method, tab_edit = st.tabs(
    ["Companies", "By offering", "Markets", "How this works", "Edit data"]
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
            st.markdown("**What to pitch**")
            for i, p in enumerate(r["recommendations"]):
                tag = " · supporting" if p.get("subordinate") else (" · lead" if i == 0 else "")
                st.markdown(
                    f'<div class="rowline"><b>{p["product"].replace("_"," ")}</b>{tag}<br>'
                    f'<span class="why">{p["reason"]}</span></div>',
                    unsafe_allow_html=True,
                )

        if r["suppressed_products"]:
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

    approachable, not_approachable = [], []
    for r in rows:
        for p in r["recommendations"]:
            if p["product"] != chosen:
                continue
            row = {
                "Company": r["company"],
                "Score": round(r["score"], 0),
                "Fit": round(p["score"], 0),
                "Position": "supporting" if p.get("subordinate") else "lead",
                "Category": PILL[r["category"]][1],
                "Why": p["reason"],
            }
            if r["category"] in ("prospect", "prospect_narrow", "route_to_partnership"):
                approachable.append(row)
            else:
                row["Not approachable"] = (
                    r["hard_disqualifiers"][0]["rule"].replace("_", " ")
                    if r["hard_disqualifiers"] else "no established need"
                )
                not_approachable.append(row)

    approachable.sort(key=lambda h: (-h["Fit"], -h["Score"]))
    not_approachable.sort(key=lambda h: -h["Fit"])

    st.caption(f"{len(approachable)} companies to approach, ranked by fit")
    st.dataframe(pd.DataFrame(approachable), hide_index=True, use_container_width=True)

    if not_approachable:
        with st.expander(
            f"{len(not_approachable)} companies whose signature also fires — but which are excluded"
        ):
            st.caption(
                "Kept visible on purpose. A tool that only shows what it selected can't be checked. "
                "These fire on the signature and are still ruled out, each for a stated reason."
            )
            st.dataframe(pd.DataFrame(not_approachable), hide_index=True, use_container_width=True)

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
            "Markets where friction is high and Yellow Card has little or no regulatory footing. "
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


# ---------------------------------------------------------------- editor

TIER1_FIELDS = [
    ("tier1_cross_border_payments", "Recurring cross-border payments"),
    ("tier1_usd_liquidity", "Persistent USD liquidity requirement"),
    ("tier1_multi_market_collection", "Multi-market local collection"),
    ("tier1_multi_currency_obligations", "Recurring multi-currency obligations"),
]
TIER2_FIELDS = [
    ("tier2_disclosed_pain", "Disclosed FX or dollar-access harm"),
    ("tier2_multi_entity", "Multi-entity structure"),
    ("tier2_multiple_local_rails", "Multiple local payment requirements"),
]
TIER0_FIELDS = [
    ("single_market_single_currency", "Single market, single currency"),
    ("foreign_parent_treasury", "Foreign parent controls treasury"),
    ("competes_for_same_buyer", "Competes for the same buyer"),
    ("sustained_regional_retreat", "Sustained regional retreat"),
    ("licence_conflict", "Licence conflict"),
    ("direct_banking_all_markets", "Direct banking in all markets (soft cap)"),
]
USD_REQ = ["receives", "holds", "pays", "needs_on_demand"]
DIRECTIONS = ["none", "soft_in_hard_out", "hard_in_soft_out", "bidirectional"]
TRAJECTORIES = ["expanding", "pruning", "static", "retreating"]

STRENGTH_HELP = (
    "0.9-1.0 stated in a filing with figures · 0.6-0.8 evidenced across sources, not quantified · "
    "0.3-0.5 inferable from business model · 0.1-0.2 thin single source. "
    "Anything at 0.5 or below carries the thin-evidence flag."
)


def blank_company():
    return {
        "identity": {"legal_name": "", "trading_name": "", "sector": "",
                     "business_model_type": "corporate", "hq_country": "",
                     "ownership": "", "year_founded": None},
        "footprint": {"operating_countries": "", "entity_structure": "",
                      "entry_years": "", "markets_exited": ""},
        "money_movement": {"currencies_collected_raw": [], "currencies_paid_raw": [],
                           "customer_geography": "", "supplier_geography": "",
                           "recipient_type": "", "payment_frequency": "recurring"},
        "signals": {k: {"present": False, "strength": 0.0, "source": ""}
                    for k, _ in TIER1_FIELDS + TIER2_FIELDS},
        "fx": {"mismatch_direction": "none", "usd_requirement_type": []},
        "product_gates": {"provides_financial_functionality_to_customers": False,
                          "holds_or_manages_digital_assets": False},
        "tier0_flags": {k: False for k, _ in TIER0_FIELDS},
        "footprint_trajectory": "static",
        "meta": {"evidence_depth": "thin", "confidence": "low", "status": "EXTRACTED",
                 "output_category": "prospect", "notes": ""},
    }


def _editor_unlocked():
    try:
        pw = st.secrets.get("editor_password")
    except Exception:
        pw = None
    if not pw:
        return True, "open"
    if st.session_state.get("editor_ok"):
        return True, "unlocked"
    return False, "locked"


def persist(companies, message):
    """Commit to GitHub when configured. Returns (ok, detail, mode)."""
    try:
        secrets = st.secrets
    except Exception:
        return False, "No secrets available.", "local"
    if not github_sync.configured(secrets):
        return False, "", "download"
    ok, detail = github_sync.push(secrets, companies, message)
    return ok, detail, "github"


with tab_edit:
    unlocked, lock_state = _editor_unlocked()

    if not unlocked:
        st.markdown(
            '<p class="lede">The dataset is read-only here. Everything else in this tool is '
            'fully explorable — move the weights in the sidebar and the whole ranking recomputes.</p>',
            unsafe_allow_html=True,
        )
        entered = st.text_input("Editor password", type="password")
        if entered:
            if entered == st.secrets.get("editor_password"):
                st.session_state.editor_ok = True
                st.rerun()
            else:
                st.error("Not that one.")
        st.stop()

    try:
        _gh_on = github_sync.configured(st.secrets)
    except Exception:
        _gh_on = False

    if _gh_on:
        st.markdown(
            '<p class="lede">Add, change or remove companies. Scores recompute as you save, and '
            'each save commits to GitHub — the change is live, nothing to push by hand.</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<p class="lede">Add, change or remove companies. Scores recompute the moment you save. '
            'GitHub sync is not configured, so changes stay in this session — use Download to keep them.</p>',
            unsafe_allow_html=True,
        )
        st.caption("Set up sync: see the GitHub sync section of the README. Takes about five minutes.")

    mode = st.radio("", ["Add a company", "Edit an existing one", "Remove", "Download"],
                    horizontal=True, label_visibility="collapsed")

    companies = st.session_state.companies
    names = [c["identity"]["trading_name"] for c in companies]

    if mode == "Remove":
        gone = st.selectbox("Company", names, key="rm_pick")
        target = next(c for c in companies if c["identity"]["trading_name"] == gone)
        if target.get("meta", {}).get("confirmed_yc_customer"):
            st.warning(
                "This is a confirmed customer and one of the positive controls. "
                "Removing it means the framework loses the check that proves it ranks real customers highly."
            )
        if st.button("Remove from dataset", type="primary"):
            st.session_state.companies = [c for c in companies
                                          if c["identity"]["trading_name"] != gone]
            ok, detail, mode = persist(st.session_state.companies, f"Remove {gone} from dataset")
            if mode == "github" and ok:
                st.success(f"Removed {gone} and committed. Ranking has recomputed.")
            elif mode == "github":
                st.error(f"Removed here, but the commit failed: {detail}")
                st.caption("The change is live in this session. Use Download to keep it.")
            else:
                st.success(f"Removed {gone}. Ranking has recomputed.")
            st.rerun()

    elif mode == "Download":
        payload = {
            "project": "Yellow Card Customer Opportunity Scoring Engine",
            "framework_version": "1.4",
            "counts": {"total_rows": len(companies)},
            "companies": companies,
        }
        st.download_button(
            "Download MASTER_dataset.json",
            data=json.dumps(payload, indent=2, ensure_ascii=False),
            file_name="MASTER_dataset.json",
            mime="application/json",
            type="primary",
        )
        if _gh_on:
            st.caption(
                f"{len(companies)} rows. Saves already commit to GitHub automatically — this is "
                "just a backup copy or a way to work offline."
            )
        else:
            st.caption(
                f"{len(companies)} rows. Replace the file in your repo and push. Without GitHub sync, "
                "session edits are lost when the app restarts."
            )
        st.json(payload["counts"])

    else:
        editing = mode == "Edit an existing one"
        if editing:
            pick_edit = st.selectbox("Company", names, key="ed_pick")
            c = json.loads(json.dumps(
                next(x for x in companies if x["identity"]["trading_name"] == pick_edit)))
        else:
            c = blank_company()

        ident, foot = st.columns(2)
        with ident:
            st.markdown("**Identity**")
            c["identity"]["trading_name"] = st.text_input("Trading name", c["identity"].get("trading_name", ""))
            c["identity"]["legal_name"] = st.text_input("Legal name", c["identity"].get("legal_name", ""))
            c["identity"]["sector"] = st.text_input("Sector", c["identity"].get("sector", ""))
            bmt = ["corporate", "platform", "financial institution"]
            cur_bmt = c["identity"].get("business_model_type", "corporate")
            c["identity"]["business_model_type"] = st.selectbox(
                "Business model", bmt, index=bmt.index(cur_bmt) if cur_bmt in bmt else 0)
            c["identity"]["hq_country"] = st.text_input("HQ country", c["identity"].get("hq_country", ""))
            c["identity"]["ownership"] = st.text_input("Ownership", c["identity"].get("ownership", "") or "")

        with foot:
            st.markdown("**Footprint and flows**")
            c["footprint"]["operating_countries"] = st.text_area(
                "Operating countries", str(c["footprint"].get("operating_countries", "")), height=70)
            c["footprint"]["entity_structure"] = st.text_area(
                "Entity structure", str(c["footprint"].get("entity_structure", "")), height=70)
            coll = st.text_input("Currencies collected (comma separated)",
                                 ", ".join(c["money_movement"].get("currencies_collected_raw", [])))
            paid = st.text_input("Currencies paid out (comma separated)",
                                 ", ".join(c["money_movement"].get("currencies_paid_raw", [])))
            c["money_movement"]["currencies_collected_raw"] = [x.strip() for x in coll.split(",") if x.strip()]
            c["money_movement"]["currencies_paid_raw"] = [x.strip() for x in paid.split(",") if x.strip()]
            c["money_movement"]["recipient_type"] = st.text_input(
                "Recipient type", c["money_movement"].get("recipient_type", ""),
                help="Drives the local-rails direction flag. Words like consumers, merchants, farmers, drivers, employees mark outbound.")

        st.markdown("---")
        st.markdown("**Tier 1 — establishes that a problem exists**")
        st.caption(STRENGTH_HELP)
        for key, label in TIER1_FIELDS:
            sig = c["signals"].get(key) or {"present": False, "strength": 0.0, "source": ""}
            a, b, d_ = st.columns([1, 1.4, 3.4])
            sig["present"] = a.checkbox(label, bool(sig.get("present")), key=f"p_{key}")
            sig["strength"] = b.slider("strength", 0.0, 1.0, float(sig.get("strength") or 0.0), 0.1,
                                       key=f"s_{key}", label_visibility="collapsed")
            sig["source"] = d_.text_input("source", sig.get("source", ""), key=f"src_{key}",
                                          placeholder="Source — no signal scores without one",
                                          label_visibility="collapsed")
            c["signals"][key] = sig

        st.markdown("**Tier 2 — worsens an existing problem, never creates one**")
        st.caption("Disclosed FX or dollar-access harm only. Layoffs, unpaid vendors and funding trouble are not FX pain.")
        for key, label in TIER2_FIELDS:
            sig = c["signals"].get(key) or {"present": False, "strength": 0.0, "source": ""}
            a, b, d_ = st.columns([1, 1.4, 3.4])
            sig["present"] = a.checkbox(label, bool(sig.get("present")), key=f"p_{key}")
            sig["strength"] = b.slider("strength", 0.0, 1.0, float(sig.get("strength") or 0.0), 0.1,
                                       key=f"s_{key}", label_visibility="collapsed")
            sig["source"] = d_.text_input("source", sig.get("source", ""), key=f"src_{key}",
                                          placeholder="Source", label_visibility="collapsed")
            c["signals"][key] = sig

        st.markdown("---")
        f1, f2, f3 = st.columns(3)
        with f1:
            st.markdown("**Currency mismatch**")
            cur_dir = c["fx"].get("mismatch_direction", "none")
            base_dir = next((d for d in DIRECTIONS if str(cur_dir).startswith(d)), "none")
            c["fx"]["mismatch_direction"] = st.selectbox(
                "Direction", DIRECTIONS, index=DIRECTIONS.index(base_dir),
                help="The FX rule fires either way. Direction is recorded, it doesn't decide whether the need exists.")
            c["fx"]["usd_requirement_type"] = st.multiselect(
                "USD requirement", USD_REQ,
                default=[x for x in c["fx"].get("usd_requirement_type", []) if x in USD_REQ],
                help="This is what triggers Global USD Accounts — separate from mismatch direction.")
        with f2:
            st.markdown("**Product gates**")
            c["product_gates"]["provides_financial_functionality_to_customers"] = st.checkbox(
                "Offers financial functionality to its own customers",
                bool(c["product_gates"].get("provides_financial_functionality_to_customers")),
                help="Hard gate for API/Widget. A manufacturer never qualifies.")
            c["product_gates"]["holds_or_manages_digital_assets"] = st.checkbox(
                "Holds or manages digital assets",
                bool(c["product_gates"].get("holds_or_manages_digital_assets")),
                help="Hard gate for wallets/custody. Crypto adjacency alone is not enough.")
            traj = c.get("footprint_trajectory", "static")
            c["footprint_trajectory"] = st.selectbox(
                "Trajectory", TRAJECTORIES,
                index=TRAJECTORIES.index(traj) if traj in TRAJECTORIES else 2,
                help="Retreating is a disqualifier, not a discount.")
        with f3:
            st.markdown("**Tier 0**")
            for key, label in TIER0_FIELDS:
                c["tier0_flags"][key] = st.checkbox(
                    label, bool(c["tier0_flags"].get(key) is True), key=f"t0_{key}")

        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        depths = ["rich", "moderate", "thin"]
        confs = ["high", "medium", "low"]
        cd = c["meta"].get("evidence_depth", "thin")
        cc = c["meta"].get("confidence", "low")
        c["meta"]["evidence_depth"] = m1.selectbox("Evidence depth", depths,
                                                   index=depths.index(cd) if cd in depths else 2)
        c["meta"]["confidence"] = m2.selectbox("Confidence", confs,
                                               index=confs.index(cc) if cc in confs else 2)
        c["meta"]["status"] = m3.selectbox("Status", ["EXTRACTED", "NEEDS SEARCH PASS"],
                                           index=0 if c["meta"].get("status") == "EXTRACTED" else 1)
        c["meta"]["notes"] = st.text_area("Notes", c["meta"].get("notes", "") or "", height=80)

        established = any(
            c["signals"][k].get("present") and float(c["signals"][k].get("strength") or 0) >= 0.5
            for k, _ in TIER1_FIELDS
        )
        missing_src = [lbl for k, lbl in TIER1_FIELDS + TIER2_FIELDS
                       if c["signals"][k].get("present") and not c["signals"][k].get("source")]

        if not established:
            st.info(
                "No Tier 1 signal at 0.5 or above. This row will land in **no established need** — "
                "shown separately rather than deleted, so the floor rule can be judged."
            )
        if missing_src:
            st.warning("Signals marked present with no source: " + ", ".join(missing_src)
                       + ". Every signal needs one — that rule is what makes the tool checkable.")

        label = "Save changes" if editing else "Add to dataset"
        if st.button(label, type="primary", disabled=not c["identity"]["trading_name"]):
            others = [x for x in companies
                      if x["identity"]["trading_name"] != (pick_edit if editing else c["identity"]["trading_name"])]
            st.session_state.companies = others + [c]
            name = c["identity"]["trading_name"]
            verb = "Update" if editing else "Add"
            ok, detail, mode = persist(st.session_state.companies, f"{verb} {name}")
            if mode == "github" and ok:
                st.success(f"{name} saved and committed. Ranking has recomputed.")
                if detail.startswith("http"):
                    st.caption(f"[View the commit]({detail})")
            elif mode == "github":
                st.error(f"Saved here, but the commit failed: {detail}")
                st.caption("The change is live in this session. Use Download so it isn't lost.")
            else:
                st.success(f"{name} saved. Ranking has recomputed.")
            st.rerun()
