"""
Yellow Card Customer Opportunity Scoring Engine
Framework v1.4

Usage:
    python scoring_engine.py MASTER_dataset.json > scored_output.json
"""

import json
import sys
from copy import deepcopy

# ---------------------------------------------------------------- config

TIER1_WEIGHTS = {
    "tier1_cross_border_payments": 30,
    "tier1_usd_liquidity": 30,
    "tier1_multi_market_collection": 20,
    "tier1_multi_currency_obligations": 20,
}

DECAY_LADDER = [1.0, 0.8, 0.6, 0.4]

PRODUCT_NAMES = {
    "global_usd_accounts": "Global USD Accounts",
    "treasury_management": "Treasury management",
    "local_rails": "Local collections and payouts",
    "fx": "Currency conversion",
    "stablecoin_settlement": "Stablecoin settlement",
    "api_widget": "Payments API and Widget",
    "wallets_custody": "Wallets and custody",
}

DIRECTION_PLAIN = {
    "soft_in_hard_out": "earns local currency, owes hard currency",
    "hard_in_soft_out": "earns hard currency, owes local currency",
    "bidirectional": "money moves both ways",
    "none": "no recurring mismatch",
    "none material": "no material mismatch",
}


def _plain_direction(d):
    d = str(d or "")
    for k, v in DIRECTION_PLAIN.items():
        if d.startswith(k):
            extra = d[len(k):].strip(" ()")
            return f"{v}{' — ' + extra if extra else ''}"
    return d


def _markets(c):
    """Short readable market description."""
    txt = str(c.get("footprint", {}).get("operating_countries", ""))
    txt = txt.split(";")[0].split(" - ")[0].strip()
    return txt[:70] if txt else "its operating markets"


def _currencies(c, key):
    lst = c.get("money_movement", {}).get(key, []) or []
    lst = [x for x in lst if len(str(x)) <= 30]
    if not lst:
        return ""
    if len(lst) <= 3:
        return ", ".join(lst)
    return f"{', '.join(lst[:3])} and {len(lst)-3} more"

TIER2_WEIGHTS = {
    "tier2_disclosed_pain": 0.20,
    "tier2_multi_entity": 0.10,
    "tier2_multiple_local_rails": 0.10,
    "tier2_compliance_friction": 0.15,
}
TIER2_RANGE = (1.0, 1.4)
TIER3_RANGE = (1.0, 1.1)

URGENCY = {
    "expanding": 1.3,
    "pruning": 1.0,
    "static": 1.0,
    "retreating": None,
}

HARD_DISQUALIFIERS = {
    "single_market_single_currency": "Single market, single currency in and out - no cross-border problem exists",
    "foreign_parent_treasury": "FX and banking policy set by an overseas parent",
    "competes_for_same_buyer": "Sells cross-border settlement to the same customers Yellow Card sells to",
    "sustained_regional_retreat": "Multiple market exits plus stated reduction in regional capital allocation",
    "licence_conflict": "Regulated deposit-taker where third-party settlement would conflict with its own licence",
}

SOFT_CAPS = {
    "direct_banking_all_markets": {
        "label": "treasury_already_solved",
        "suppresses": ["global_usd_accounts", "treasury_management"],
    },
    "infrastructure_layer_peer": {
        "label": "infrastructure_layer_peer",
        "suppresses": [],
        "cannot_lead": True,
    },
    "single_dominant_corridor_served": {
        "label": "single_dominant_corridor_served",
        "suppresses": ["stablecoin_settlement"],
    },
}

BLOCKED_FUNDS_COUNTRIES = [
    "Algeria", "XAF Zone", "Mozambique", "Eritrea", "Angola",
    "Zimbabwe", "Ethiopia", "Malawi", "Lebanon",
]

PARTNER_MOTION = {
    "VALR", "Interswitch", "Cellulant", "Peach Payments", "MNT-Halan", "Halan",
    "Flutterwave", "Paystack", "DPO Group", "Pesapal", "Fawry", "Nomba", "Yoco", "Clip",
}

# ---------------------------------------------------------------- signatures

def sig_global_usd_accounts(c):
    usd_req = c.get("fx", {}).get("usd_requirement_type", [])
    if not usd_req:
        return None
    s = sig_val(c, "tier1_usd_liquidity")
    if s < 0.4:
        return None
    breadth = min(1.0, 0.55 + 0.15 * len(usd_req))
    pain = sig_val(c, "tier2_disclosed_pain")
    curr = sig_val(c, "tier1_multi_currency_obligations")
    blended = 0.50 * s + 0.20 * breadth + 0.18 * curr + 0.12 * pain
    verbs = {"receives": "receives", "holds": "holds", "pays": "pays out",
             "needs_on_demand": "needs dollars on demand"}
    said = ", ".join(verbs.get(u, u) for u in usd_req)
    return {
        "score": round(100 * blended, 1),
        "reason": f"{said} in USD, against {_currencies(c, 'currencies_collected_raw') or 'local currency income'}",
    }


def sig_treasury(c):
    ents = sig_val(c, "tier2_multi_entity")
    curr = len(c.get("money_movement", {}).get("currencies_collected_raw", []))
    mkts = sig_val(c, "tier1_multi_market_collection")
    if ents < 0.5 or curr < 3:
        return None
    strength = (0.35 * ents + 0.25 * min(curr / 7, 1.0) + 0.20 * mkts
                + 0.20 * _market_breadth(c))
    return {
        "score": round(100 * strength, 1),
        "reason": f"separate entities across {_markets(c)}, collecting in "
                  f"{_currencies(c, 'currencies_collected_raw') or f'{curr} currencies'}",
    }


def sig_local_rails(c):
    s = sig_val(c, "tier1_multi_market_collection")
    if s < 0.4:
        return None
    breadth = _market_breadth(c)
    rails = sig_val(c, "tier2_multiple_local_rails")
    s = 0.55 * s + 0.25 * breadth + 0.20 * rails
    inbound = s >= 0.4
    outbound = "consumers" in str(c.get("money_movement", {}).get("recipient_type", "")) or \
               "merchants" in str(c.get("money_movement", {}).get("recipient_type", "")) or \
               "farmers" in str(c.get("money_movement", {}).get("recipient_type", "")) or \
               "drivers" in str(c.get("money_movement", {}).get("recipient_type", "")) or \
               "employees" in str(c.get("money_movement", {}).get("recipient_type", ""))
    direction = "both" if inbound and outbound else ("inbound" if inbound else "outbound")
    who = str(c.get("money_movement", {}).get("recipient_type", "")).strip()
    flow = {"both": "collects from and pays out to", "inbound": "collects from",
            "outbound": "pays out to"}[direction]
    return {
        "score": round(100 * s, 1),
        "reason": f"{flow} {who or 'counterparties'} across {_markets(c)}",
        "direction": direction,
    }


def _market_breadth(c):
    """Rough count of operating markets, normalised. Keeps a 40-country operator
    from scoring identically to a 3-country one on the same signal strength."""
    text = str(c.get("footprint", {}).get("operating_countries", ""))
    import re
    nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", text) if 2 <= int(n) <= 60]
    if nums:
        return min(1.0, max(nums) / 25)
    commas = text.count(",")
    return min(1.0, (commas + 1) / 12) if commas else 0.3


def sig_fx(c):
    d = c.get("fx", {}).get("mismatch_direction", "")
    if not d or d in ("none", "none material"):
        return None
    strength = (0.55 * sig_val(c, "tier1_multi_currency_obligations")
                + 0.45 * sig_val(c, "tier2_disclosed_pain"))
    return {
        "score": round(100 * strength, 1),
        "reason": _plain_direction(d),
        "subordinate": True,
    }


def sig_stablecoin_settlement(c):
    countries = str(c.get("footprint", {}).get("operating_countries", ""))
    friction_hits = sum(1 for k in BLOCKED_FUNDS_COUNTRIES if k.split()[0] in countries)
    s = sig_val(c, "tier1_cross_border_payments")
    if s < 0.5:
        return None
    strength = min(1.0, s * (1 + 0.15 * friction_hits))
    hits = [k for k in BLOCKED_FUNDS_COUNTRIES if k.split()[0] in countries]
    where = f"including {', '.join(hits[:3])}" if hits else "across its corridors"
    return {
        "score": round(100 * strength, 1),
        "reason": f"cross-border settlement {where}",
        "subordinate": True,
    }


def sig_api_widget(c):
    gates = c.get("product_gates", {})
    if not gates.get("provides_financial_functionality_to_customers"):
        return None
    coll = sig_val(c, "tier1_multi_market_collection")
    rails = sig_val(c, "tier2_multiple_local_rails")
    breadth = _market_breadth(c)
    resells = bool(gates.get("sells_fx_or_payments_to_third_parties"))
    s = max(0.35, 0.45 * coll + 0.30 * rails + 0.25 * breadth) + (0.25 if resells else 0.0)
    note = str(gates.get("gate_note", "")).split(".")[0].strip()
    sector = str(c.get("identity", {}).get("sector", "")).lower()
    if resells:
        why = "already moves money for its own customers on someone else's rails"
    else:
        why = note if note else f"offers financial services to its own customers ({sector})"
    return {"score": round(100 * min(1.0, s), 1), "reason": why[:170], "resells": resells}


def sig_wallets_custody(c):
    if not c.get("product_gates", {}).get("holds_or_manages_digital_assets"):
        return None
    platform = c.get("product_gates", {}).get("provides_financial_functionality_to_customers")
    s = 0.55 + (0.20 if platform else 0.0) + 0.25 * _market_breadth(c)
    note = str(c.get("product_gates", {}).get("gate_note", "")).split(".")[0].strip()
    return {"score": round(100 * min(1.0, s), 1),
            "reason": note[:150] if note else "holds or manages digital assets"}


SIGNATURES = {
    "global_usd_accounts": sig_global_usd_accounts,
    "treasury_management": sig_treasury,
    "local_rails": sig_local_rails,
    "fx": sig_fx,
    "stablecoin_settlement": sig_stablecoin_settlement,
    "api_widget": sig_api_widget,
    "wallets_custody": sig_wallets_custody,
}

# ---------------------------------------------------------------- helpers

def sig_val(c, key):
    s = c.get("signals", {})
    if s.get("NOT_YET_EXTRACTED"):
        return 0.0
    v = s.get(key)
    if not isinstance(v, dict):
        return 0.0
    if not v.get("present"):
        return float(v.get("strength", 0.0))
    return float(v.get("strength", 0.0))


def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().upper() in ("TRUE", "YES")
    return False


def normalise_flags(c):
    """Rows were written by hand across several batches and use variant keys and
    free-text values. Map them onto the canonical set before evaluating."""
    raw = dict(c.get("tier0_flags", {}))
    note = str(raw.get("tier0_note", "")).upper()
    out = {}

    for k in HARD_DISQUALIFIERS:
        out[k] = truthy(raw.get(k))

    negated = any(p in note for p in ("NO HARD CAP", "NO HARD DISQUALIFY", "NOT DISQUALIFIED",
                                      "NO CAP.", "NO CAP,"))
    if not negated and ("HARD DISQUALIFY" in note or "HARD CAP" in note):
        if "FOREIGN PARENT" in note or "PARENT TREASURY" in note:
            out["foreign_parent_treasury"] = True
        if "SAME BUYER" in note or "COMPETES FOR THE SAME BUYER" in note or "DIRECT COMPETITOR" in note:
            out["competes_for_same_buyer"] = True
        if "REGIONAL RETREAT" in note:
            out["sustained_regional_retreat"] = True
        if "SINGLE MARKET" in note:
            out["single_market_single_currency"] = True

    if str(raw.get("direct_banking_all_markets", "")).upper() == "PARENT LEVEL":
        out["foreign_parent_treasury"] = True

    if truthy(raw.get("infrastructure_competitor")) and not out["competes_for_same_buyer"]:
        if truthy(raw.get("competes_for_same_buyer")) or "COMPETITOR" in note:
            out["competes_for_same_buyer"] = True

    out["_soft_direct_banking"] = truthy(raw.get("direct_banking_all_markets")) or \
        str(raw.get("direct_banking_all_markets", "")).upper().startswith(("LIKELY", "PARTIAL"))
    out["_soft_infra_peer"] = truthy(raw.get("infrastructure_competitor")) and not out["competes_for_same_buyer"]
    out["_soft_single_corridor"] = truthy(raw.get("single_dominant_corridor_served"))

    effect = raw.get("soft_cap_effect")
    out["_explicit_suppression"] = effect.get("suppressed", []) if isinstance(effect, dict) else []
    if out["_explicit_suppression"]:
        out["_soft_direct_banking"] = True
    return out


def check_tier0(c):
    flags = normalise_flags(c)
    hard, soft = [], []
    for k, msg in HARD_DISQUALIFIERS.items():
        if flags.get(k):
            hard.append({"rule": k, "reason": msg})
    if flags["_soft_direct_banking"]:
        spec = deepcopy(SOFT_CAPS["direct_banking_all_markets"])
        if flags["_explicit_suppression"]:
            spec["suppresses"] = flags["_explicit_suppression"]
        soft.append(spec)
    if flags["_soft_single_corridor"]:
        soft.append(SOFT_CAPS["single_dominant_corridor_served"])
    if flags["_soft_infra_peer"]:
        soft.append(SOFT_CAPS["infrastructure_layer_peer"])
    return hard, soft


def tier1_base(c):
    contribs = []
    for key, weight in TIER1_WEIGHTS.items():
        s = sig_val(c, key)
        if s > 0:
            contribs.append({"signal": key, "weight": weight, "strength": s, "weighted": weight * s})
    contribs.sort(key=lambda x: x["weighted"], reverse=True)
    total = 0.0
    for i, ct in enumerate(contribs):
        factor = DECAY_LADDER[i] if i < len(DECAY_LADDER) else 0.0
        ct["decay"] = factor
        ct["contribution"] = round(ct["weighted"] * factor, 2)
        total += ct["contribution"]
    established = any(
        sig_val(c, k) >= 0.5 and isinstance(c.get("signals", {}).get(k), dict)
        and c["signals"][k].get("present")
        for k in TIER1_WEIGHTS
    )
    return round(total, 2), contribs, established


def tier2_modifier(c):
    lo, hi = TIER2_RANGE
    raw = sum(TIER2_WEIGHTS[k] * sig_val(c, k) for k in TIER2_WEIGHTS)
    return round(min(hi, lo + raw), 3)


def tier3_modifier(c):
    lo, hi = TIER3_RANGE
    holds = c.get("product_gates", {}).get("holds_or_manages_digital_assets")
    return hi if holds else lo


def urgency_multiplier(c):
    state = c.get("footprint_trajectory") or c.get("urgency", {}).get("state") or "static"
    return URGENCY.get(state, 1.0), state


def blocked_funds(c):
    bf = c.get("blocked_funds_flag")
    if isinstance(bf, dict) and bf.get("fires"):
        return True, bf.get("countries", [])
    countries = str(c.get("footprint", {}).get("operating_countries", ""))
    hits = [k for k in BLOCKED_FUNDS_COUNTRIES if k.split()[0] in countries]
    return bool(hits), hits


def recommend(c, soft_caps):
    suppressed = set()
    cannot_lead = False
    for s in soft_caps:
        suppressed.update(s["suppresses"])
        cannot_lead = cannot_lead or s.get("cannot_lead", False)

    results = []
    for name, fn in SIGNATURES.items():
        if name in suppressed:
            continue
        r = fn(c)
        if r:
            r["product"] = name
            r["label"] = PRODUCT_NAMES.get(name, name.replace("_", " "))
            results.append(r)

    gua = next((r for r in results if r["product"] == "global_usd_accounts"), None)
    tre = next((r for r in results if r["product"] == "treasury_management"), None)
    if gua and tre:
        if tre["score"] < gua["score"] * 0.8:
            results = [r for r in results if r["product"] != "treasury_management"]
        elif gua["score"] < tre["score"] * 0.8:
            results = [r for r in results if r["product"] != "global_usd_accounts"]

    if any(r.get("resells") for r in results):
        results = [r for r in results
                   if r["product"] not in ("treasury_management", "global_usd_accounts")]

    lead_pool = [r for r in results if not r.get("subordinate")]
    subs = [r for r in results if r.get("subordinate")]
    lead_pool.sort(key=lambda r: r["score"], reverse=True)
    subs.sort(key=lambda r: r["score"], reverse=True)
    ordered = lead_pool + subs
    return ordered[:3], sorted(suppressed), cannot_lead


def classify(c, hard, established, name):
    stated = str(c.get("meta", {}).get("output_category", ""))
    if name in PARTNER_MOTION or stated == "route_to_partnership":
        return "route_to_partnership"
    if hard:
        return "excluded"
    if not established:
        return "no_established_need"
    return "prospect"


def _score_story(c, contribs, t2, urg, urg_state):
    """One plain sentence explaining the score, for readers who won't read a table."""
    names = {
        "tier1_cross_border_payments": "it makes cross-border payments regularly",
        "tier1_usd_liquidity": "it needs dollars on an ongoing basis",
        "tier1_multi_market_collection": "it collects or pays out across several markets",
        "tier1_multi_currency_obligations": "it owes money in several currencies",
    }
    strong = [names[x["signal"]] for x in contribs if x["strength"] >= 0.7 and x["signal"] in names]
    weak = [names[x["signal"]] for x in contribs if 0 < x["strength"] < 0.7 and x["signal"] in names]

    if not strong and not weak:
        return "No evidence of a cross-border money problem was found."

    def joln(xs):
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]

    parts = []
    if strong:
        parts.append(f"There is clear evidence that {joln(strong)}.")
    if weak:
        parts.append(f"There is weaker evidence that {joln(weak)}.")
    if len(contribs) > 1:
        parts.append("The strongest of these counts in full and each additional one counts for less, "
                     "so a company with several faint indicators does not outrank one with a real problem.")
    pain = c.get("signals", {}).get("tier2_disclosed_pain") or {}
    if pain.get("present") and pain.get("strength", 0) >= 0.7:
        parts.append("The score is then lifted because the company has publicly reported that "
                     "currency movements or difficulty accessing dollars affected its results.")
    elif t2 > 1.05:
        parts.append("The score is lifted slightly by supporting evidence such as its entity structure "
                     "and the number of payment channels it runs.")
    if urg > 1.0:
        parts.append("It is lifted again because the company has entered new markets recently, so the "
                     "problem is live rather than settled.")
    elif urg_state == "static":
        parts.append("No lift for recent expansion: the footprint has been stable, so any arrangement "
                     "it has is probably entrenched.")
    return " ".join(parts)


def score_company(c):
    name = c.get("identity", {}).get("trading_name", "?")
    hard, soft = check_tier0(c)
    base, contribs, established = tier1_base(c)
    t2 = tier2_modifier(c)
    t3 = tier3_modifier(c)
    urg, urg_state = urgency_multiplier(c)

    if urg is None:
        hard.append({"rule": "sustained_regional_retreat", "reason": HARD_DISQUALIFIERS["sustained_regional_retreat"]})
        urg = 1.0

    raw = base * t2 * t3 * urg
    products, suppressed, cannot_lead = recommend(c, soft)
    bf_fires, bf_countries = blocked_funds(c)
    category = classify(c, hard, established, name)
    if category == "prospect" and suppressed:
        category = "prospect_narrow"

    return {
        "company": name,
        "sector": c.get("identity", {}).get("sector"),
        "category": category,
        "raw_score": round(raw, 2),
        "components": {
            "tier1_base": base,
            "tier2_modifier": t2,
            "tier3_modifier": t3,
            "urgency_multiplier": urg,
            "urgency_state": urg_state,
        },
        "tier1_breakdown": contribs,
        "score_story": _score_story(c, contribs, t2, urg, urg_state),
        "tier1_established": established,
        "hard_disqualifiers": hard,
        "soft_caps": [s["label"] for s in soft],
        "suppressed_products": suppressed,
        "cannot_lead": cannot_lead,
        "recommendations": products,
        "blocked_funds_flag": {"fires": bf_fires, "countries": bf_countries},
        "confidence": c.get("meta", {}).get("confidence", "unknown"),
        "evidence_depth": c.get("meta", {}).get("evidence_depth", "unknown"),
        "control_type": c.get("meta", {}).get("control_type"),
        "confirmed_yc_customer": c.get("meta", {}).get("confirmed_yc_customer", False),
        "status": c.get("meta", {}).get("status", "unknown"),
        "review_flag": _review_flag(c),
    }


def _review_flag(c):
    cat = str(c.get("meta", {}).get("output_category", ""))
    note = str(c.get("tier0_flags", {}).get("tier0_note", ""))
    if cat.upper().startswith("REVIEW"):
        return {"needs_review": True, "reason": note[:400]}
    if "MAJOR FINDING" in note or "CRITICAL" in note:
        return {"needs_review": True, "reason": note[:400]}
    return {"needs_review": False}


def normalise(rows):
    top = max((r["raw_score"] for r in rows if r["raw_score"] > 0), default=0)
    for r in rows:
        r["score"] = round(100 * r["raw_score"] / top, 1) if top else 0.0
    return rows


def validate(rows):
    positives = [r for r in rows if r.get("confirmed_yc_customer")]
    negatives = [r for r in rows if r.get("control_type") == "negative"]
    ranked = sorted(
        [r for r in rows if r["category"] in ("prospect", "prospect_narrow")],
        key=lambda r: r["raw_score"], reverse=True,
    )
    order = {r["company"]: i + 1 for i, r in enumerate(ranked)}
    return {
        "positive_controls": [
            {"company": r["company"], "category": r["category"], "score": r.get("score"),
             "rank": order.get(r["company"]), "passes": r["category"] in ("prospect", "prospect_narrow", "route_to_partnership")}
            for r in positives
        ],
        "negative_controls": [
            {"company": r["company"], "category": r["category"], "score": r.get("score"),
             "held by": ("ruled out — " + r["hard_disqualifiers"][0]["rule"].replace("_", " ")
                         if r["hard_disqualifiers"] else
                         ("offerings suppressed — " + ", ".join(
                             s.replace("_", " ") for s in r.get("suppressed_products", []))
                          if r.get("suppressed_products") else "no established need")),
             "passes": bool(r["category"] in ("excluded", "no_established_need")
                            or r.get("suppressed_products"))}
            for r in negatives
        ],
        "note": "Positive controls are confirmed Yellow Card customers. If they do not rank high, the framework is wrong, not the companies.",
    }


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "MASTER_dataset.json"
    data = json.load(open(path))
    companies = data["companies"] if isinstance(data, dict) else data

    rows = [score_company(deepcopy(c)) for c in companies]
    rows = normalise(rows)
    rows.sort(key=lambda r: (r["category"] != "prospect", -r["raw_score"]))

    out = {
        "framework_version": "1.4",
        "scored": len(rows),
        "validation": validate(rows),
        "by_category": {},
        "results": rows,
    }
    for r in rows:
        out["by_category"].setdefault(r["category"], []).append(r["company"])
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
