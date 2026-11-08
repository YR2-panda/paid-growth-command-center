"""Reconcile platform-reported results with PostHog. Pure functions: every number the app
or the agent shows comes from here, never from the language model."""
import pandas as pd

TABS = ("Meta_Daily", "Meta_Ads_Weekly", "Google_Daily", "Trials_PostHog", "Change_Log")


def _norm(df):
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def col(df, *keys):
    for c in df.columns:
        if all(k in c for k in keys):
            return c
    raise KeyError(f"No column containing {keys} in {list(df.columns)}")


def _week(s):
    return pd.to_datetime(s).dt.to_period("W-SUN").dt.start_time


def load(path_or_buffer):
    x = pd.read_excel(path_or_buffer, sheet_name=None)
    missing = [t for t in TABS[:4] if t not in x]
    if missing:
        raise ValueError(f"Workbook is missing tabs: {missing}")
    d = {k: _norm(x[k]) for k in TABS if k in x}
    d.setdefault("Change_Log", pd.DataFrame(columns=["date", "change"]))
    d["Change_Log"]["date"] = pd.to_datetime(d["Change_Log"]["date"])
    return d


def weekly(d):
    md, gd, ph = d["Meta_Daily"].copy(), d["Google_Daily"].copy(), d["Trials_PostHog"].copy()
    md["wk"], gd["wk"], ph["wk"] = _week(md["date"]), _week(gd["date"]), _week(ph["date"])
    p = ph.pivot_table(index="wk", columns=col(ph, "source"), values=col(ph, "trial"), aggfunc="sum").fillna(0)
    out = pd.DataFrame({
        "meta_spend": md.groupby("wk")[col(md, "spend")].sum(),
        "meta_reported": md.groupby("wk")[col(md, "trials")].sum(),
        "posthog_facebook": p.get("facebook"),
        "google_spend": gd.groupby("wk")[col(gd, "spend")].sum(),
        "google_reported": gd.groupby("wk")[col(gd, "conversions")].sum(),
        "posthog_google": p.get("google"),
    })
    out["meta_ratio"] = out.meta_reported / out.posthog_facebook
    out["google_ratio"] = out.google_reported / out.posthog_google
    out["meta_cpa_platform"] = out.meta_spend / out.meta_reported
    out["meta_cpa_posthog"] = out.meta_spend / out.posthog_facebook
    out["google_cpa_posthog"] = out.google_spend / out.posthog_google
    return out


def tracking_breaks(w, change_log, threshold=0.25):
    """Weeks where platform/PostHog ratio moves >25% vs the prior 3-week average, with nearby changes."""
    rows = []
    for ch in ("meta", "google"):
        r = w[f"{ch}_ratio"]
        base = r.rolling(3).mean().shift(1)
        for wk, v in r.items():
            b = base.get(wk)
            if pd.notna(b) and abs(v - b) / b > threshold:
                near = change_log[(change_log["date"] >= wk - pd.Timedelta(days=3)) &
                                  (change_log["date"] <= wk + pd.Timedelta(days=6))]
                rows.append({"channel": ch, "week": wk.date(), "ratio": round(v, 2), "baseline": round(b, 2),
                             "nearby_changes": "; ".join(f"{c['date'].date()}: {c[col(change_log, 'change')]}"
                                                         for _, c in near.iterrows())})
    return pd.DataFrame(rows)


def zero_conversion(d, min_spend=560):
    rows = []
    for tab, conv in (("Meta_Daily", "trials"), ("Google_Daily", "conversions")):
        df = d[tab]
        g = df.groupby(col(df, "campaign")).agg(spend=(col(df, "spend"), "sum"), conv=(col(df, conv), "sum"))
        for c, r in g[(g.conv == 0) & (g.spend > min_spend)].iterrows():
            rows.append({"channel": tab.split("_")[0], "campaign": c, "spend": round(r.spend), "conversions": 0})
    return pd.DataFrame(rows)


def spend_mismatch(d):
    ma, md = d["Meta_Ads_Weekly"], d["Meta_Daily"]
    out = pd.DataFrame({"ad_tab": ma.groupby(col(ma, "campaign"))[col(ma, "spend")].sum(),
                        "campaign_tab": md.groupby(col(md, "campaign"))[col(md, "spend")].sum()})
    out["gap"] = out.ad_tab - out.campaign_tab
    return out.round(0)


def campaign_table(d):
    rows = []
    for tab, conv, ch in (("Meta_Daily", "trials", "Meta"), ("Google_Daily", "conversions", "Google")):
        df = d[tab]
        g = df.groupby(col(df, "campaign")).agg(spend=(col(df, "spend"), "sum"), reported=(col(df, conv), "sum"))
        for c, r in g.iterrows():
            rows.append({"channel": ch, "campaign": c, "spend": round(r.spend), "reported_conversions": int(r.reported),
                         "platform_cpa": round(r.spend / r.reported) if r.reported else None})
    return pd.DataFrame(rows)


def vs_target(cpa, target):
    if not target:
        return ""
    lo, hi = target["min"], target["max"]
    where = "BELOW (better than)" if cpa < lo else "ABOVE (worse than)" if cpa > hi else "INSIDE"
    return f" -> {where} the ${lo}-${hi} target range"


def key_findings(d, target=None):
    """The conclusions, computed in Python so the model doesn't have to derive or judge them."""
    w = weekly(d)
    out = []
    br = tracking_breaks(w, d["Change_Log"])
    drops = br[(br.channel == "meta") & (br.ratio < br.baseline)] if len(br) else br
    if len(drops):
        split = pd.Timestamp(drops.week.min())
        pre, post = w[w.index < split], w[w.index >= split]
        for name, part in (("before", pre), ("from", post)):
            sp, rep, ph = part.meta_spend.sum(), part.meta_reported.sum(), part.posthog_facebook.sum()
            out.append(f"Meta {name} week {split.date()}: spend ${sp:,.0f}, Meta-reported {rep:.0f} trials (CPA ${sp / rep:,.0f}), "
                       f"PostHog {ph:.0f} trials (CPA ${sp / ph:,.0f}{vs_target(sp / ph, target)}).")
        out.append(f"So from week {split.date()} Meta reports {post.meta_reported.sum() / post.posthog_facebook.sum():.0%} of the trials PostHog records. "
                   "Meta's own CPA is inflated by broken tracking, so its algorithm optimizes on partial data. Nearby change: "
                   + drops.sort_values("week").iloc[0].nearby_changes)
    tot = w.sum(numeric_only=True)
    for ch, sp, ph in (("Meta", tot.meta_spend, tot.posthog_facebook), ("Google", tot.google_spend, tot.posthog_google)):
        out.append(f"{ch} full-period PostHog CPA ${sp / ph:,.0f}{vs_target(sp / ph, target)}.")
    blend = (tot.meta_spend + tot.google_spend) / (tot.posthog_facebook + tot.posthog_google)
    out.append(f"Blended full-period PostHog CPA ${blend:,.0f}{vs_target(blend, target)}.")
    for _, r in zero_conversion(d).iterrows():
        out.append(f"{r.channel} {r.campaign} spent ${r.spend:,.0f} with 0 conversions.")
    md = d["Meta_Daily"]
    daily = md.groupby(col(md, "date"))[col(md, "spend")].sum()
    out.append(f"Meta daily spend never varied much (${daily.min():,.0f}-${daily.max():,.0f}/day), so there is NO data on how CPA responds to higher spend.")
    return out


def facts(d, target=None):
    """Compact, computed fact sheet handed to the agent as its only source of numbers."""
    w = weekly(d)
    tot = w.sum(numeric_only=True)
    lines = ["KEY FINDINGS (computed; use these labels, don't re-judge them):"] + [f"  - {x}" for x in key_findings(d, target)] + [
        f"Period: {w.index.min().date()} to {(w.index.max() + pd.Timedelta(days=6)).date()} ({len(w)} weeks).",
        f"Meta: spend ${tot.meta_spend:,.0f}, Meta-reported trials {tot.meta_reported:.0f}, PostHog facebook trials {tot.posthog_facebook:.0f}, "
        f"PostHog CPA ${tot.meta_spend / tot.posthog_facebook:,.0f}.",
        f"Google: spend ${tot.google_spend:,.0f}, Google-reported conversions {tot.google_reported:.0f}, PostHog google trials {tot.posthog_google:.0f}, "
        f"PostHog CPA ${tot.google_spend / tot.posthog_google:,.0f}.",
        "Weekly (week start | meta spend | meta reported | posthog facebook | google spend | google reported | posthog google):",
    ]
    for wk, r in w.iterrows():
        lines.append(f"  {wk.date()} | ${r.meta_spend:,.0f} | {r.meta_reported:.0f} | {r.posthog_facebook:.0f} | "
                     f"${r.google_spend:,.0f} | {r.google_reported:.0f} | {r.posthog_google:.0f}")
    lines.append("Campaign totals (platform-reported):")
    for _, r in campaign_table(d).iterrows():
        cpa = f"${r.platform_cpa:,.0f}" if r.platform_cpa else "n/a"
        lines.append(f"  {r.channel} {r.campaign}: spend ${r.spend:,.0f}, conversions {r.reported_conversions}, CPA {cpa}")
    br = tracking_breaks(w, d["Change_Log"])
    if len(br):
        lines.append("Tracking-ratio breaks:")
        for _, r in br.iterrows():
            lines.append(f"  {r.channel} week {r.week}: ratio {r.ratio} vs baseline {r.baseline}. Nearby: {r.nearby_changes}")
    lines.append("Change log:")
    for _, c in d["Change_Log"].iterrows():
        lines.append(f"  {c['date'].date()}: {c[col(d['Change_Log'], 'change')]}")
    return "\n".join(lines)
