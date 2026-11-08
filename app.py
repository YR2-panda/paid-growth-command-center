"""Paid Growth Command Center: diagnose the account, edit the plan, ask the agent, export the build.

Run locally:  streamlit run app.py
"""
import calendar
import copy
import datetime as dt
import os

import altair as alt
import pandas as pd
import streamlit as st
import yaml

from builder import agent, analysis
from builder.bundle import build_zip
from builder.generate import GOOGLE_BILLING_DAYS
from builder.validate import validate

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PLAN = os.path.join(ROOT, "plans", "next_month.yaml")
SAMPLE_DATA = os.path.join(ROOT, "sample_data", "account_export_sample.xlsx")
PRESETS = {
    "Add a UK test": "Add a $5,000 UK non-brand search test next month. Fund it from US non-brand.",
    "CEO: double Meta": "The CEO wants to double Meta spend starting tomorrow. What should we do? Commit to an answer.",
    "Rebalance Google": "PMax is our most expensive Google campaign. Move $3,000 from PMax to US non-brand search and explain the trade-off.",
}

st.set_page_config(page_title="Paid Growth Command Center", layout="wide")


# ---------- state ----------
def load_plan_text(path=DEFAULT_PLAN):
    with open(path, encoding="utf-8") as f:
        return f.read()


if "plan" not in st.session_state:
    st.session_state.plan = yaml.safe_load(load_plan_text())
    st.session_state.approvals = []
    st.session_state.agent_result = None


def plan_text():
    return yaml.safe_dump(st.session_state.plan, sort_keys=False, width=120)


# ---------- sidebar ----------
with st.sidebar:
    st.header("Setup")
    api_key = st.text_input("Anthropic API key", type="password",
                            help="Only needed for the Agent tab. Used for this session only and never stored.")
    model = st.text_input("Claude model", value=agent.DEFAULT_MODEL)
    st.divider()
    upload = st.file_uploader("Account export (.xlsx)", type=["xlsx"],
                              help="Tabs: Meta_Daily, Meta_Ads_Weekly, Google_Daily, Trials_PostHog, Change_Log. Leave empty to use the sample.")
    plan_upload = st.file_uploader("Plan (.yaml)", type=["yaml", "yml"], help="Leave empty to use plans/next_month.yaml.")
    if plan_upload is not None and st.button("Load uploaded plan"):
        st.session_state.plan = yaml.safe_load(plan_upload.getvalue().decode("utf-8"))
        st.session_state.agent_result = None
        st.rerun()
    if st.button("Reset plan to default"):
        st.session_state.plan = yaml.safe_load(load_plan_text())
        st.session_state.approvals = []
        st.session_state.agent_result = None
        st.rerun()


@st.cache_data
def load_data(file_bytes):
    import io
    return analysis.load(io.BytesIO(file_bytes) if file_bytes else SAMPLE_DATA)


try:
    data = load_data(upload.getvalue() if upload else None)
except Exception as e:  # bad workbook
    st.error(f"Couldn't read that workbook: {e}")
    st.stop()

plan = st.session_state.plan
errors, warnings, summary = validate(plan)

# ---------- header ----------
st.title("Paid Growth Command Center")
st.caption("Diagnose the account, edit the plan, ask the agent, export ready-to-import campaigns. "
           "The AI proposes, the code checks, and a person approves.")
c1, c2, c3, c4 = st.columns(4)
g = plan["guardrails"]["cpa_target"]
c1.metric("Monthly budget", f"${summary['total']:,.0f}")
c1.caption(f"Meta ${summary['meta_total']:,.0f} · Google ${summary['google_total']:,.0f}")
c2.metric("Projected trials", f"{summary['projected_trials']:,.0f}")
c2.caption(f"{plan['launch']['days']} days from {plan['launch']['start_date']}")
c3.metric("Projected blended CPA", f"${summary['projected_cpa']:,.0f}")
c3.caption(f"Target ${g['min']}–${g['max']}")
c4.metric("Plan checks", "Pass" if not errors else f"{len(errors)} error(s)")
c4.caption(f"{len(warnings)} launch to-do(s)")

tab_dx, tab_plan, tab_agent, tab_export = st.tabs(["1 · Diagnose", "2 · Plan", "3 · Agent", "4 · Export"])

# ---------- 1. Diagnose ----------
with tab_dx:
    w = analysis.weekly(data)
    tot = w.sum(numeric_only=True)
    st.subheader("Don't trust platform numbers until they match PostHog")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Meta CPA (Meta-reported)", f"${tot.meta_spend / tot.meta_reported:,.0f}")
    m2.metric("Meta CPA (PostHog)", f"${tot.meta_spend / tot.posthog_facebook:,.0f}")
    m3.metric("Google CPA (Google-reported)", f"${tot.google_spend / tot.google_reported:,.0f}")
    m4.metric("Google CPA (PostHog)", f"${tot.google_spend / tot.posthog_google:,.0f}")

    def trial_chart(reported, posthog, label):
        df = w.reset_index().rename(columns={"wk": "week"})
        long = pd.concat([
            pd.DataFrame({"week": df.week, "trials": df[reported], "source": f"{label}-reported"}),
            pd.DataFrame({"week": df.week, "trials": df[posthog], "source": "PostHog"})])
        lines = alt.Chart(long).mark_line(point=True).encode(
            x=alt.X("week:T", title=None), y=alt.Y("trials:Q", title="Trials per week"),
            color=alt.Color("source:N", scale=alt.Scale(range=["#9a9a9a", "#2f6fdb"]), legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["week:T", "source:N", "trials:Q"])
        cl = data["Change_Log"].rename(columns={analysis.col(data["Change_Log"], "change"): "change"})
        rules = alt.Chart(cl).mark_rule(strokeDash=[4, 4], color="#bbbbbb").encode(x="date:T", tooltip=["date:T", "change:N"])
        return (rules + lines).properties(height=280)

    a, b = st.columns(2)
    a.markdown("**Meta: reported vs PostHog trials** (dashed lines = change log, hover for detail)")
    a.altair_chart(trial_chart("meta_reported", "posthog_facebook", "Meta"), width="stretch")
    b.markdown("**Google: reported vs PostHog trials**")
    b.altair_chart(trial_chart("google_reported", "posthog_google", "Google"), width="stretch")

    st.markdown("**Flags**")
    z = analysis.zero_conversion(data)
    for _, r in z.iterrows():
        st.error(f"{r.channel} **{r.campaign}** spent ${r.spend:,.0f} with 0 conversions.")
    br = analysis.tracking_breaks(w, data["Change_Log"])
    if len(br):
        st.warning("Weeks where the platform/PostHog ratio moved more than 25% (tracking may have changed):")
        st.dataframe(br, hide_index=True, width="stretch")
    mm = analysis.spend_mismatch(data)
    if (mm.gap.abs() > mm.campaign_tab * 0.05).any():
        st.warning("Meta ad-level and campaign-level spend disagree by more than 5% for some campaigns. "
                   "Use campaign-level numbers for campaign decisions.")
        st.dataframe(mm, width="stretch")
    with st.expander("Campaign totals and weekly table"):
        st.dataframe(analysis.campaign_table(data), hide_index=True, width="stretch")
        st.dataframe(w.round(2), width="stretch")

# ---------- 2. Plan ----------
with tab_plan:
    st.subheader("Next month's plan")
    left, right = st.columns([1, 2])
    with left:
        start = dt.date.fromisoformat(str(plan["launch"]["start_date"]))
        new_start = st.date_input("Launch start date", start)
        if new_start != start:
            p = copy.deepcopy(plan)
            p["launch"]["start_date"] = new_start.isoformat()
            if new_start.day == 1:
                p["launch"]["days"] = calendar.monthrange(new_start.year, new_start.month)[1]
            st.session_state.plan = p
            st.rerun()
        st.caption(f"{plan['launch']['days']} days. Meta daily = monthly / {plan['launch']['days']}; "
                   f"Google daily = monthly / {GOOGLE_BILLING_DAYS} (Google's monthly billing cap).")

    rows = []
    for ch in ("meta", "google"):
        for c in plan[ch]["campaigns"]:
            d = plan["launch"]["days"] if ch == "meta" else GOOGLE_BILLING_DAYS
            exp = c.get("expected_cpa") or 0
            rows.append({"channel": ch, "campaign": c["name"], "paused": c.get("status") == "PAUSED",
                         "monthly_budget": c["monthly_budget"], "expected_cpa": exp,
                         "daily_budget": round(c["monthly_budget"] / d), "projected_trials": round(c["monthly_budget"] / exp) if exp else 0})
    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df, hide_index=True, width="stretch", key=f"editor_{len(st.session_state.approvals)}",
        disabled=["channel", "campaign", "daily_budget", "projected_trials"],
        column_config={"monthly_budget": st.column_config.NumberColumn("Monthly budget ($)", step=500, format="$%d"),
                       "expected_cpa": st.column_config.NumberColumn("Expected CPA ($)", step=5, format="$%d"),
                       "daily_budget": st.column_config.NumberColumn("Daily ($)", format="$%d"),
                       "paused": st.column_config.CheckboxColumn("Paused"),
                       "projected_trials": st.column_config.NumberColumn("Projected trials")})
    if not edited[["monthly_budget", "expected_cpa", "paused"]].equals(df[["monthly_budget", "expected_cpa", "paused"]]):
        p = copy.deepcopy(plan)
        for _, r in edited.iterrows():
            c = next(x for x in p[r.channel]["campaigns"] if x["name"] == r.campaign)
            c["monthly_budget"], c["expected_cpa"] = int(r.monthly_budget), int(r.expected_cpa)
            if r.paused:
                c["status"] = "PAUSED"
            else:
                c.pop("status", None)
        st.session_state.plan = p
        st.rerun()

    if errors:
        for e in errors:
            st.error(e)
    else:
        st.success("All plan checks pass.")
    if warnings:
        with st.expander(f"{len(warnings)} launch to-do(s) before switching on"):
            for wmsg in warnings:
                st.markdown(f"- {wmsg}")

    with st.expander("Edit the full plan as YAML (ad sets, ads, keywords, copy)"):
        txt = st.text_area("Plan YAML", plan_text(), height=400, label_visibility="collapsed")
        if st.button("Apply YAML"):
            try:
                st.session_state.plan = yaml.safe_load(txt)
                st.rerun()
            except yaml.YAMLError as e:
                st.error(f"Invalid YAML: {e}")

# ---------- 3. Agent ----------
with tab_agent:
    st.subheader("Ask the planning agent")
    st.caption("Claude gets the computed fact sheet and the current plan. Its proposal must pass the same checks, "
               "and it can't edit the guardrails. If a check fails, it gets the errors and up to 2 more attempts. "
               "Nothing changes until you approve.")
    cols = st.columns(len(PRESETS))
    for col, (label, text) in zip(cols, PRESETS.items()):
        if col.button(label, width="stretch"):
            st.session_state.brief = text
    brief = st.text_area("Request", key="brief", height=90, placeholder="e.g. Plan January with the same budget and add a new agency-focused concept to testing.")
    run = st.button("Run agent", type="primary", disabled=not (api_key and brief))
    if not api_key:
        st.info("Paste an Anthropic API key in the sidebar to use the agent. Every other tab works without one.")
    if run:
        import anthropic
        with st.spinner("Claude is drafting and checking a proposal..."):
            try:
                st.session_state.agent_result = agent.run(anthropic.Anthropic(api_key=api_key), brief, plan_text(),
                                                          analysis.facts(data), model=model)
                st.session_state.agent_brief = brief
            except Exception as e:
                st.session_state.agent_result = None
                st.error(f"Agent call failed: {type(e).__name__}: {e}")

    res = st.session_state.agent_result
    if res:
        for i, at in enumerate(res["attempts"], 1):
            ok = not at["errors"]
            with st.expander(f"Attempt {i}: {'passed checks' if ok else 'blocked by checks'}", expanded=not ok and i == len(res["attempts"])):
                st.markdown(at["proposal"].get("answer", ""))
                for e in at["errors"]:
                    st.error(e)
        final = res["final"]
        if final is None:
            st.error("The agent couldn't produce a plan that passes the checks in 3 attempts. The plan is unchanged.")
        else:
            st.markdown("#### Proposal")
            st.markdown(final["proposal"]["answer"])
            if final["proposal"].get("changes"):
                st.markdown("**Changes**\n" + "\n".join(f"- {c}" for c in final["proposal"]["changes"]))
            if final["proposal"].get("risks"):
                st.markdown("**Risks**\n" + "\n".join(f"- {r}" for r in final["proposal"]["risks"]))
            if final["plan"] is None:
                st.info("No plan change proposed.")
            else:
                s = final["summary"]
                st.markdown(f"**After this change:** ${s['total']:,.0f} total, {s['projected_trials']:,.0f} projected trials, "
                            f"${s['projected_cpa']:,.0f} blended CPA.")
                st.code(final.get("diff") or "(no textual difference)", language="diff")
                a1, a2 = st.columns(2)
                if a1.button("Approve and apply", type="primary"):
                    st.session_state.plan = final["plan"]
                    st.session_state.approvals.append({"when": dt.datetime.now().isoformat(timespec="seconds"),
                                                       "request": st.session_state.get("agent_brief", ""),
                                                       "changes": final["proposal"].get("changes", [])})
                    st.session_state.agent_result = None
                    st.rerun()
                if a2.button("Reject"):
                    st.session_state.agent_result = None
                    st.rerun()

# ---------- 4. Export ----------
with tab_export:
    st.subheader("Export ready-to-import files")
    if errors:
        st.error("Fix the plan errors in the Plan tab first. Nothing is exported while a check fails.")
    else:
        log = "# Approved agent changes\n\n" + ("\n".join(
            f"- {a['when']}: {a['request']}\n" + "".join(f"  - {c}\n" for c in a["changes"])
            for a in st.session_state.approvals) or "None. Plan built from the file as loaded.\n")
        zip_bytes, files = build_zip(plan, {"plan.yaml": plan_text(), "approvals.md": log})
        name = plan["launch"]["start_date"]
        st.download_button("Download everything (.zip)", zip_bytes, file_name=f"launch_{name}.zip", type="primary")
        cols = st.columns(len(files))
        for col, (fname, content) in zip(cols, files.items()):
            col.download_button(fname, content, file_name=fname, width="stretch")
        st.markdown(files["launch_summary.md"].decode("utf-8"))
        st.caption("Meta: Ads Manager → Import ads in bulk. Google: Google Ads Editor → Account → Import → From file. "
                   "Everything imports paused.")
