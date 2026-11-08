"""Plain-English launch summary a founder can read before anything goes live."""
import os

from generate import GOOGLE_BILLING_DAYS


def write_summary(plan, errors, warnings, summary, outdir):
    days = plan["launch"]["days"]
    lines = [f"# Launch summary: {plan['launch']['name']}",
             f"Start {plan['launch']['start_date']}, {days} days. Meta daily = monthly / {days}; Google daily = monthly / 30.4 (Google's monthly billing cap). Everything is imported PAUSED.", "",
             "| Channel | Campaign | Monthly | Daily | Expected CPA | Projected trials |",
             "|---|---|---:|---:|---:|---:|"]
    for ch in ("meta", "google"):
        for c in plan[ch]["campaigns"]:
            b, e = c["monthly_budget"], c.get("expected_cpa") or 0
            d = days if ch == "meta" else GOOGLE_BILLING_DAYS
            t = b / e if e and b else 0
            status = " (paused)" if c.get("status") == "PAUSED" else ""
            lines.append(f"| {ch.title()} | {c['name']}{status} | ${b:,.0f} | ${b / d:,.0f} | "
                         f"{'$%d' % e if e else '-'} | {t:,.0f} |")
    lines += ["", f"**Total:** ${summary['total']:,.0f} (Meta ${summary['meta_total']:,.0f}, "
              f"Google ${summary['google_total']:,.0f})",
              f"**Projected:** {summary['projected_trials']:,.0f} trials at a blended "
              f"${summary['projected_cpa']:,.0f} CPA "
              f"(target ${plan['guardrails']['cpa_target']['min']}-${plan['guardrails']['cpa_target']['max']}).", ""]
    lines.append("## Validation")
    lines += [f"- ERROR: {e}" for e in errors] or ["- No blocking errors."]
    lines += [f"- Warning: {w}" for w in warnings]
    lines += ["", "## Before you switch anything on",
              "- [ ] Test trial signup on the live signup flow: StartTrial fires in Meta Events Manager (browser + server, deduplicated) and Trial Start fires in Google Ads.",
              "- [ ] A test click with UTMs shows up in PostHog under the right utm_source / utm_content.",
              "- [ ] Audiences Trial_Starters_180d and Customers_All exist and are populated.",
              "- [ ] New creative files uploaded (see warnings).",
              "- [ ] Enable campaigns, then check spend after 2 hours and again next morning."]
    path = os.path.join(outdir, "launch_summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path
