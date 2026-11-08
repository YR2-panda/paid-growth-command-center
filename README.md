# Paid Growth Command Center

**Live app:** [add Streamlit link] · **Assessment doc:** [add link]

A small, reusable system for launching paid campaigns on Meta and Google:

1. **Diagnose:** reconciles platform-reported conversions with PostHog and flags tracking breaks, zero-conversion campaigns and report mismatches.
2. **Plan:** one YAML file holds the whole launch. Edit budgets in the app and watch the checks, projected trials and CPA update.
3. **Agent:** Claude turns a plain-English request into a plan change. The change has to pass the same checks, and a person approves it before it's applied.
4. **Export:** generates paused, ready-to-import files for Meta Ads Manager and Google Ads Editor, plus a founder-readable launch summary.

**The design rule: the AI proposes, the code checks, a person approves.**

## How the agent is kept honest

| Control | Why |
|---|---|
| Every number comes from Python (`builder/analysis.py`), not the model | Language models misquote figures. The agent gets a computed fact sheet and is told to use only that. |
| The agent answers through one structured tool (`submit_proposal`) | Every output is either an answer, or an answer plus a complete plan, so there's nothing to parse from free text |
| The `guardrails` block is locked | Otherwise the agent could "fix" a failed check by editing the rule (for example, marking UK tracking as verified). Any guardrail edit is rejected. |
| Proposals run through the same validator as human edits | One set of rules for people and AI |
| Failed checks go back to the agent, which gets up to 2 more attempts | It either fixes the plan or explains why the request can't be done |
| Changes are shown as a diff and need Approve | Nothing changes without a person. Approvals are logged into the export (`approvals.md`). |

## The checks (`builder/validate.py`)

| Rule | Data that led to it |
|---|---|
| No shared budgets | UK was added to a shared budget and took about $560/day from US campaigns |
| No live spend in a geo without verified tracking | UK spent $15K with 0 trials |
| Launch days must match the calendar month | A 30-day split run over 31-day December overspends by about $4K |
| Projected blended CPA must be within target | Stops a plan that can't hit $250 to $280 |
| Retargeting ≤ 15% of Meta | Retargeting_30d had the worst CPA in the account ($433) |
| Prospecting must exclude trialists and customers | Stops paying to reach people who already signed up |
| Brand terms blocked from non-brand search and PMax | Stops cheap brand conversions inflating prospecting results |
| Keyword can't be blocked by its own negative list | Caught "search atlas login" vs the "login" negative |
| Test ad sets must afford a 7-day verdict | A test that can't spend 2.5x CPA in a week can't be called |
| Every ad gets `utm_content` = ad name | PostHog couldn't check Meta's ad-level numbers when the pixel broke |
| RSA limits, naming, missing ads and assets | Import errors |

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py                                    # the app
python build.py plans/next_month.yaml                   # same build from the command line
python analyze.py sample_data/account_export_sample.xlsx
python tests/test_rules.py && python tests/test_agent.py   # 14 tests, no API key needed
```

The Agent tab needs an Anthropic API key, which you paste in the sidebar. It's used for that session only and never stored. Every other tab works without a key.

## Reuse it for the next launch

1. Upload the latest account export in the sidebar and read the Diagnose tab before changing anything.
2. Load last month's plan, or `plans/_template.yaml`, and change the start date. The number of days updates to match the month.
3. Edit budgets in the Plan tab, or ask the agent ("Plan January, same budget, add an agency concept to testing").
4. Export, upload creative, import (Meta: Ads Manager → Import ads in bulk; Google: Ads Editor → Account → Import → From file), work through the `launch_summary.md` checklist, then switch campaigns on.

Before the first real import, export one existing campaign from each platform and compare the column headers. Both importers let you map columns that don't match.

## Roadmap

1. **Direct API push** (Meta Marketing API, Google Ads API) to replace CSV import. Same plan and checks; only the export step changes.
2. **Tracking QA bot:** a headless browser runs a test signup from a tagged ad URL and checks that the Meta Pixel, Conversions API, Google conversion and PostHog all fired. Runs after every site deploy and daily. Would have caught the 9/22 break the same day.
3. **Daily decision loop:** pulls yesterday's results, applies the kill, graduate and scale rules, and posts proposals to Slack with Approve buttons. Approvals edit the plan through this same agent and validator.
