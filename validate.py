"""Plan validation. Every rule here exists because of something in the account data.

Errors block the build. Warnings are printed and written to the report.
"""
import calendar
import re
from datetime import date

NAME_RE = re.compile(r"^(META|GOOG)_[A-Z]{2}_[A-Za-z0-9]+(_[A-Za-z0-9]+)*$")


def _within(value, target, tol=0.02):
    return abs(value - target) <= target * tol


def validate(plan):
    errors, warnings = [], []
    g = plan["guardrails"]
    meta, google = plan["meta"], plan["google"]

    meta_total = sum(c["monthly_budget"] for c in meta["campaigns"])
    google_total = sum(c["monthly_budget"] for c in google["campaigns"])
    total = meta_total + google_total

    # 1. Budget cap and channel split
    if total > g["monthly_budget_cap"]:
        errors.append(f"Total budget ${total:,.0f} is over the ${g['monthly_budget_cap']:,.0f} cap.")
    for ch, actual in (("meta", meta_total), ("google", google_total)):
        target = g["channel_split"][ch]
        if not _within(actual, target):
            errors.append(f"{ch} budget ${actual:,.0f} is more than 2% away from the ${target:,.0f} split.")

    # 2. Projected blended CPA must land inside the target range
    proj_spend, proj_trials = 0, 0
    for c in meta["campaigns"] + google["campaigns"]:
        if c["monthly_budget"] and c.get("expected_cpa"):
            proj_spend += c["monthly_budget"]
            proj_trials += c["monthly_budget"] / c["expected_cpa"]
    blended = proj_spend / proj_trials if proj_trials else 0
    lo, hi = g["cpa_target"]["min"], g["cpa_target"]["max"]
    if blended > hi:
        errors.append(f"Projected blended CPA ${blended:,.0f} is above the ${hi} ceiling.")
    elif blended < lo * 0.9:
        warnings.append(f"Projected blended CPA ${blended:,.0f} is well under target. Check expected_cpa inputs are realistic.")

    # 2b. A month-long launch must use the month's real length, or daily budgets overspend
    # (30 days of budget run for 31 days = $4K over on a $120K plan).
    start = date.fromisoformat(str(plan["launch"]["start_date"]))
    if start.day == 1:
        month_days = calendar.monthrange(start.year, start.month)[1]
        if plan["launch"]["days"] != month_days:
            errors.append(f"launch.days is {plan['launch']['days']} but {start:%B %Y} has {month_days} days. "
                          f"Meta daily budgets would spend ${meta_total / plan['launch']['days'] * month_days:,.0f}.")

    # 3. Naming convention, so reports can be grouped by channel/geo/role
    for c in meta["campaigns"] + google["campaigns"]:
        if not NAME_RE.match(c["name"]):
            errors.append(f"Campaign name '{c['name']}' breaks the convention CHANNEL_GEO_Type_Detail.")

    # 4. No shared budgets. In the data, adding UK to a shared budget took ~$560/day from US campaigns.
    if google.get("shared_budgets"):
        errors.append("Shared budgets are not allowed. Give each campaign its own budget.")

    # 5. No live spend in a geo until its trial tracking is verified (UK: $15K, 0 trials).
    verified = set(g["verified_geos"])
    for c in google["campaigns"]:
        live = c.get("status", "ENABLED") != "PAUSED" and c["monthly_budget"] > 0
        if live and not set(c["geo"]) <= verified:
            errors.append(f"{c['name']} spends in {c['geo']} but tracking is only verified for {sorted(verified)}.")
    for c in meta["campaigns"]:
        for s in c["ad_sets"]:
            if not set(s["geo"]) <= verified:
                errors.append(f"{c['name']}/{s['name']} targets unverified geo {s['geo']}.")

    # 6. Retargeting share cap (Retargeting_30d had the worst CPA in the account)
    rt = sum(c["monthly_budget"] for c in meta["campaigns"] if c["role"] == "retargeting")
    if meta_total and rt / meta_total > g["max_retargeting_share_meta"]:
        errors.append(f"Retargeting is {rt / meta_total:.0%} of Meta, over the {g['max_retargeting_share_meta']:.0%} cap.")

    # 7. Every Meta ad set must exclude trial starters and customers
    for c in meta["campaigns"]:
        for s in c["ad_sets"]:
            ex = set(s.get("exclude_audiences", []))
            if not {"Trial_Starters_180d", "Customers_All"} <= ex:
                errors.append(f"{c['name']}/{s['name']} must exclude Trial_Starters_180d and Customers_All.")

    # 8. Ads referenced must exist; new creative needs an asset before launch
    meta_ads = meta["ads"]
    for c in meta["campaigns"]:
        for s in c["ad_sets"]:
            if not s["ads"]:
                errors.append(f"{c['name']}/{s['name']} has no ads.")
            for a in s["ads"]:
                if a not in meta_ads:
                    errors.append(f"Meta ad '{a}' in {s['name']} is not defined under meta.ads.")
                elif meta_ads[a].get("status") == "new":
                    warnings.append(f"Meta ad '{a}' is new creative. Upload {meta_ads[a]['asset']} before launch.")
    for c in google["campaigns"]:
        groups = c.get("ad_groups", []) + c.get("asset_groups", [])
        for gr in groups:
            for a in gr["ads"]:
                if a not in google["ads"]:
                    errors.append(f"Google ad '{a}' in {gr['name']} is not defined under google.ads.")

    # 9. ABO test ad sets must be able to reach a kill decision inside 7 days
    days = plan["launch"]["days"]
    for c in meta["campaigns"]:
        if c["budget_level"] == "ad_set":
            shares = [s.get("budget_share", 0) for s in c["ad_sets"]]
            if abs(sum(shares) - 1) > 0.02:
                errors.append(f"{c['name']}: ad set budget_share values add up to {sum(shares):.2f}, not 1.")
            for s in c["ad_sets"]:
                weekly = c["monthly_budget"] * s.get("budget_share", 0) / days * 7
                if weekly < 2.5 * hi:
                    warnings.append(f"{s['name']} gets ${weekly:,.0f}/week, under 2.5x CPA (${2.5 * hi:,.0f}). It can't be judged in a week.")

    # 10. Brand protection: non-brand search and PMax must not buy brand traffic
    brand = [b.lower() for b in g["brand_terms"]]
    for c in google["campaigns"]:
        # Match the exact name token: a substring check would treat "NonBrand" as brand and skip it.
        if c["type"] == "search" and "Brand" not in c["name"].split("_"):
            if not c.get("negative_brand"):
                errors.append(f"{c['name']} must set negative_brand: true.")
            for gr in c["ad_groups"]:
                for kws in gr["keywords"].values():
                    for kw in kws:
                        if any(b in kw.lower() for b in brand):
                            errors.append(f"Brand term '{kw}' found in non-brand ad group {gr['name']}.")
        if c["type"] == "pmax" and not c.get("brand_exclusion"):
            errors.append(f"{c['name']} must set brand_exclusion: true.")

    # 11. RSA limits
    for name, ad in google["ads"].items():
        for h in ad.get("headlines", []):
            if len(h) > 30:
                errors.append(f"Headline over 30 chars in {name}: '{h}' ({len(h)})")
        for d in ad.get("descriptions", []):
            if len(d) > 90:
                errors.append(f"Description over 90 chars in {name}: '{d}' ({len(d)})")
        if "long_headline" in ad and len(ad["long_headline"]) > 90:
            errors.append(f"Long headline over 90 chars in {name}.")
        if "headlines" in ad and "images" not in ad and len(ad["headlines"]) < 3:
            errors.append(f"{name} needs at least 3 headlines.")

    # 12. A keyword must not be blocked by a negative list attached to its own campaign
    neg_lists = google.get("shared_negative_lists", {})
    for c in google["campaigns"]:
        negs = [n.lower() for nl in c.get("negative_lists", []) for n in neg_lists.get(nl, [])]
        for gr in c.get("ad_groups", []):
            for kws in gr["keywords"].values():
                for kw in kws:
                    hit = [n for n in negs if f" {n} " in f" {kw.lower()} "]
                    if hit:
                        errors.append(f"Keyword '{kw}' in {c['name']}/{gr['name']} is blocked by negative '{hit[0]}'.")

    summary = dict(total=total, meta_total=meta_total, google_total=google_total,
                   projected_trials=proj_trials, projected_cpa=blended)
    return errors, warnings, summary
