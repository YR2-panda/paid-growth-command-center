"""Turns a validated plan into upload files.

- Meta: one CSV in the Ads Manager bulk-import layout (one row per ad, campaign and
  ad set fields repeated). Everything is created PAUSED.
- Google: one CSV for Google Ads Editor (Account > Import > From file), mixed row
  types: campaign, ad group, keyword, negative, responsive search ad.
  PMax asset groups go into a separate CSV because Editor's PMax import differs by version.

Column names follow the platforms' import templates. Before the first real import,
export one existing campaign from each platform and compare headers; both tools let
you map columns on import if a header has changed.
"""
import csv
import os


GOOGLE_BILLING_DAYS = 30.4  # Google caps monthly charges at daily budget x 30.4


def daily(monthly, days):
    return round(monthly / days, 2)


def meta_utm(campaign_name):
    # Literal campaign name + Meta's dynamic ad name, so PostHog can attribute trials per ad.
    return ("utm_source=facebook&utm_medium=paid_social"
            f"&utm_campaign={campaign_name}&utm_content={{{{ad.name}}}}")


def google_suffix(campaign_name):
    return ("utm_source=google&utm_medium=cpc"
            f"&utm_campaign={campaign_name}&utm_content={{creative}}&utm_term={{keyword}}")


META_COLS = [
    "Campaign Name", "Campaign Status", "Campaign Objective", "Buying Type",
    "Campaign Daily Budget", "Campaign Bid Strategy",
    "Ad Set Name", "Ad Set Run Status", "Ad Set Time Start", "Ad Set Daily Budget",
    "Ad Set Bid Strategy", "Optimization Goal", "Billing Event", "Custom Event Type",
    "Countries", "Age Min", "Age Max", "Advantage Audience",
    "Custom Audiences", "Excluded Custom Audiences",
    "Ad Name", "Ad Status", "Title", "Body", "Link", "Call to Action", "URL Tags",
    "Video File Name", "Image File Name", "Creative Type",
]


def build_meta(plan, outdir):
    days = plan["launch"]["days"]
    start = plan["launch"]["start_date"] + " 00:00"
    link = plan["guardrails"]["landing_page"]
    ads = plan["meta"]["ads"]
    rows = []
    for c in plan["meta"]["campaigns"]:
        cbo = c["budget_level"] == "campaign"
        for s in c["ad_sets"]:
            adset_budget = "" if cbo else daily(c["monthly_budget"] * s["budget_share"], days)
            for a in s["ads"]:
                ad = ads[a]
                rows.append({
                    "Campaign Name": c["name"],
                    "Campaign Status": "PAUSED",
                    "Campaign Objective": c["objective"],
                    "Buying Type": "AUCTION",
                    "Campaign Daily Budget": daily(c["monthly_budget"], days) if cbo else "",
                    "Campaign Bid Strategy": c["bid_strategy"] if cbo else "",
                    "Ad Set Name": f"{c['name']}__{s['name']}",
                    "Ad Set Run Status": "PAUSED",
                    "Ad Set Time Start": start,
                    "Ad Set Daily Budget": adset_budget,
                    "Ad Set Bid Strategy": "" if cbo else c["bid_strategy"],
                    "Optimization Goal": "OFFSITE_CONVERSIONS",
                    "Billing Event": "IMPRESSIONS",
                    "Custom Event Type": plan["meta"]["conversion_event"],
                    "Countries": ",".join(s["geo"]),
                    "Age Min": s["age_min"],
                    "Age Max": s["age_max"],
                    "Advantage Audience": 1 if s["audience"] == "advantage_plus" else 0,
                    "Custom Audiences": ",".join(s.get("include_audiences", [])),
                    "Excluded Custom Audiences": ",".join(s.get("exclude_audiences", [])),
                    "Ad Name": a,
                    "Ad Status": "PAUSED",
                    "Title": ad["headline"],
                    "Body": ad["primary_text"],
                    "Link": link,
                    "Call to Action": "SIGN_UP",
                    "URL Tags": meta_utm(c["name"]),
                    "Video File Name": ad["asset"] if ad["format"] == "video" else "",
                    "Image File Name": ad["asset"] if ad["format"] == "image" else "",
                    "Creative Type": ad["format"],
                })
    path = os.path.join(outdir, "meta_bulk_import.csv")
    _write(path, META_COLS, rows)
    return path, len(rows)


G_COLS = [
    "Row Type", "Campaign", "Campaign Type", "Campaign Status", "Budget", "Budget type",
    "Bid Strategy Type", "Target CPA", "Target Impression Share", "Max CPC Bid Limit",
    "Networks", "Location", "Language", "Final URL suffix", "Shared Set",
    "Ad Group", "Ad Group Status", "Keyword", "Criterion Type",
    "Ad type", "Final URL", "Path 1", "Path 2",
] + [f"Headline {i}" for i in range(1, 16)] + [f"Description {i}" for i in range(1, 5)]

GEO = {"US": "United States", "UK": "United Kingdom"}
BID = {"TARGET_CPA": "Maximize conversions", "TARGET_IMPRESSION_SHARE": "Target impression share"}


def build_google(plan, outdir):
    days = plan["launch"]["days"]
    link = plan["guardrails"]["landing_page"]
    brand = plan["guardrails"]["brand_terms"]
    gads = plan["google"]["ads"]
    rows, pmax_rows = [], []
    for c in plan["google"]["campaigns"]:
        base = {"Campaign": c["name"]}
        rows.append({**base, "Row Type": "Campaign",
                     "Campaign Type": "Search" if c["type"] == "search" else "Performance Max",
                     "Campaign Status": "Paused",  # always import paused; launch after QA
                     "Budget": daily(c["monthly_budget"], GOOGLE_BILLING_DAYS), "Budget type": "Daily",
                     "Bid Strategy Type": BID[c["bid_strategy"]],
                     "Target CPA": c.get("target_cpa", ""),
                     "Target Impression Share": c.get("target_impression_share", ""),
                     "Max CPC Bid Limit": c.get("max_cpc", ""),
                     "Networks": "Google search" if c["type"] == "search" else "",
                     "Location": ";".join(GEO[x] for x in c["geo"]),
                     "Language": "English",
                     "Final URL suffix": google_suffix(c["name"])})
        for nl in c.get("negative_lists", []):
            rows.append({**base, "Row Type": "Campaign shared set", "Shared Set": nl})
        if c.get("negative_brand"):
            for b in brand:
                rows.append({**base, "Row Type": "Campaign negative", "Keyword": b,
                             "Criterion Type": "Campaign Negative Phrase"})
        for ag in c.get("ad_groups", []):
            gb = {**base, "Ad Group": ag["name"]}
            rows.append({**gb, "Row Type": "Ad group", "Ad Group Status": "Enabled"})
            for match, kws in ag["keywords"].items():
                for kw in kws:
                    rows.append({**gb, "Row Type": "Keyword", "Keyword": kw, "Criterion Type": match.title()})
            for a in ag["ads"]:
                ad = gads[a]
                r = {**gb, "Row Type": "Ad", "Ad type": "Responsive search ad", "Final URL": link,
                     "Path 1": ad["path"][0], "Path 2": ad["path"][1]}
                for i, h in enumerate(ad["headlines"], 1):
                    r[f"Headline {i}"] = h
                for i, d in enumerate(ad["descriptions"], 1):
                    r[f"Description {i}"] = d
                rows.append(r)
        for ag in c.get("asset_groups", []):
            ad = gads[ag["ads"][0]]
            pmax_rows.append({"Campaign": c["name"], "Asset Group": ag["name"], "Final URL": link,
                              "Brand exclusion": "Yes" if c.get("brand_exclusion") else "No",
                              "Final URL expansion": "Off" if not c.get("final_url_expansion") else "On",
                              "Audience signal": "; ".join(ag["audience_signal"]),
                              "Headlines": " | ".join(ad["headlines"]),
                              "Long headline": ad["long_headline"],
                              "Descriptions": " | ".join(ad["descriptions"]),
                              "Images": " | ".join(ad.get("images", [])),
                              "Videos": " | ".join(ad.get("videos", []))})
    for name, kws in plan["google"].get("shared_negative_lists", {}).items():
        for kw in kws:
            rows.append({"Row Type": "Shared negative", "Shared Set": name, "Keyword": kw,
                         "Criterion Type": "Negative Phrase"})
    path = os.path.join(outdir, "google_ads_editor_import.csv")
    _write(path, G_COLS, rows)
    ppath = os.path.join(outdir, "google_pmax_asset_groups.csv")
    if pmax_rows:
        _write(ppath, list(pmax_rows[0].keys()), pmax_rows)
    return path, len(rows), ppath


def _write(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
