#!/usr/bin/env python3
"""Plan -> validated, ready-to-import Meta and Google campaigns.

Usage:
    python build.py plans/next_month.yaml            # validate + generate into output/<plan name>/
    python build.py plans/next_month.yaml --check    # validate only
"""
import argparse
import os
import sys

import yaml

from builder.generate import build_google, build_meta
from builder.report import write_summary
from builder.validate import validate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--out", default="output")
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as f:
        plan = yaml.safe_load(f)

    errors, warnings, s = validate(plan)
    print(f"Budget ${s['total']:,.0f} (Meta ${s['meta_total']:,.0f} / Google ${s['google_total']:,.0f})")
    print(f"Projected {s['projected_trials']:,.0f} trials at ${s['projected_cpa']:,.0f} blended CPA")
    for w in warnings:
        print("  warning:", w)
    for e in errors:
        print("  ERROR:", e)
    if errors:
        print(f"\n{len(errors)} error(s). Fix the plan and re-run. Nothing was generated.")
        sys.exit(1)
    if args.check:
        print("\nPlan is valid.")
        return

    outdir = os.path.join(args.out, os.path.splitext(os.path.basename(args.plan))[0])
    os.makedirs(outdir, exist_ok=True)
    meta_path, n_meta = build_meta(plan, outdir)
    g_path, n_g, pmax_path = build_google(plan, outdir)
    summary_path = write_summary(plan, errors, warnings, s, outdir)
    print(f"\nWrote {meta_path} ({n_meta} ads)")
    print(f"Wrote {g_path} ({n_g} rows)")
    print(f"Wrote {pmax_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
