"""Each test breaks the plan the way the old account was broken and checks the validator stops it.
Run: python -m pytest  (or: python test_rules.py)
"""
import copy
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import validate  # noqa: E402

PLAN = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "next_month.yaml")))


def errs(mutate):
    p = copy.deepcopy(PLAN)
    mutate(p)
    return " | ".join(validate(p)[0])


def test_clean_plan_passes():
    assert validate(PLAN)[0] == []


def test_uk_live_without_verified_tracking_is_blocked():
    def m(p):
        uk = p["google"]["campaigns"][-1]
        uk["status"], uk["monthly_budget"], uk["expected_cpa"] = "ENABLED", 5000, 280
        p["google"]["campaigns"][1]["monthly_budget"] -= 5000
    assert "tracking is only verified" in errs(m)


def test_shared_budget_is_blocked():
    assert "Shared budgets" in errs(lambda p: p["google"].__setitem__("shared_budgets", ["Google_Main_Shared"]))


def test_over_budget_is_blocked():
    assert "over the $120,000 cap" in errs(lambda p: p["meta"]["campaigns"][0].__setitem__("monthly_budget", 60000))


def test_retargeting_cap():
    def m(p):
        p["meta"]["campaigns"][2]["monthly_budget"] = 20000
        p["meta"]["campaigns"][0]["monthly_budget"] = 30000
    assert "Retargeting is" in errs(m)


def test_missing_trialist_exclusion():
    assert "must exclude" in errs(lambda p: p["meta"]["campaigns"][0]["ad_sets"][0].__setitem__("exclude_audiences", []))


def test_cpa_ceiling():
    assert "above the $280 ceiling" in errs(
        lambda p: [c.__setitem__("expected_cpa", 330) for c in p["meta"]["campaigns"]])


def test_brand_in_nonbrand():
    def m(p):
        p["google"]["campaigns"][1]["ad_groups"][0]["keywords"]["exact"].append("search atlas ai")
    assert "Brand term" in errs(m)


def test_month_length_matches_calendar():
    assert "has 31 days" in errs(lambda p: p["launch"].__setitem__("days", 30))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("pass", name)
