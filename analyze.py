#!/usr/bin/env python3
"""Reconcile platform-reported results with PostHog before trusting any number.

Usage: python analyze.py path/to/export.xlsx
"""
import sys

import pandas as pd

from builder import analysis as a


def main(path):
    d = a.load(path)
    w = a.weekly(d)
    pd.set_option("display.width", 200)
    print("\n1) Weekly platform vs PostHog\n")
    print(w.round(2).to_string())
    print("\n2) Tracking breaks (platform/PostHog ratio moved >25% vs prior 3-week average)\n")
    br = a.tracking_breaks(w, d["Change_Log"])
    print(br.to_string(index=False) if len(br) else "  none")
    print("\n3) Campaigns with spend > 2x CPA ceiling ($560) and zero conversions\n")
    z = a.zero_conversion(d)
    print(z.to_string(index=False) if len(z) else "  none")
    print("\n4) Ad-level vs campaign-level spend (Meta)\n")
    m = a.spend_mismatch(d)
    print(m.to_string())
    if (m.gap.abs() > m.campaign_tab * 0.05).any():
        print("  -> gap over 5%: ads are mapped to the wrong campaign in one of the tabs. Fix before judging ads by campaign.")


if __name__ == "__main__":
    main(sys.argv[1])
