"""Agent loop tests with a fake Claude client: no API key or network needed.
Run: python tests/test_agent.py
"""
import copy
import os
import sys
from types import SimpleNamespace as NS

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from builder import agent  # noqa: E402

PLAN_TEXT = open(os.path.join(os.path.dirname(__file__), "..", "plans", "next_month.yaml")).read()
PLAN = yaml.safe_load(PLAN_TEXT)


class FakeClient:
    """Returns the scripted proposals in order and records what it was sent."""
    def __init__(self, proposals):
        self.proposals, self.calls = list(proposals), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(copy.deepcopy(kw["messages"]))
        p = self.proposals.pop(0)
        return NS(content=[NS(type="tool_use", id=f"tu_{len(self.calls)}", input=p)])


def plan_with(mutate):
    p = copy.deepcopy(PLAN)
    mutate(p)
    return yaml.safe_dump(p, sort_keys=False)


def enable_uk(p):
    uk = p["google"]["campaigns"][-1]
    uk.pop("status")
    uk["monthly_budget"], uk["expected_cpa"] = 5000, 280
    p["google"]["campaigns"][1]["monthly_budget"] -= 5000


def test_answer_without_plan_change():
    c = FakeClient([{"answer": "No. Fix tracking first.", "changes": [], "risks": []}])
    r = agent.run(c, "double meta?", PLAN_TEXT, "facts")
    assert r["final"]["plan"] is None and len(r["attempts"]) == 1


def test_valid_change_produces_diff():
    def m(p):
        p["google"]["campaigns"][2]["monthly_budget"] -= 3000
        p["google"]["campaigns"][1]["monthly_budget"] += 3000
    c = FakeClient([{"answer": "Moved $3K.", "changes": ["PMax -3K", "NonBrand +3K"], "risks": [], "plan_yaml": plan_with(m)}])
    r = agent.run(c, "move 3k", PLAN_TEXT, "facts")
    assert r["final"]["plan"]["google"]["campaigns"][1]["monthly_budget"] == 33000
    assert "-      monthly_budget: 30000" in r["final"]["diff"] or "monthly_budget: 33000" in r["final"]["diff"]


def test_blocked_uk_then_agent_backs_off():
    c = FakeClient([
        {"answer": "Added UK.", "changes": ["UK +5K"], "risks": [], "plan_yaml": plan_with(enable_uk)},
        {"answer": "Can't: UK tracking isn't verified.", "changes": [], "risks": ["UK untracked"]},
    ])
    r = agent.run(c, "add UK test", PLAN_TEXT, "facts")
    assert "tracking is only verified" in r["attempts"][0]["errors"][0]
    assert r["final"]["plan"] is None and len(r["attempts"]) == 2
    # the validator's error was fed back to the model as a tool_result
    fed_back = c.calls[1][-1]["content"][0]
    assert fed_back["type"] == "tool_result" and fed_back["is_error"]


def test_guardrail_edit_is_rejected():
    def sneaky(p):
        enable_uk(p)
        p["guardrails"]["verified_geos"].append("UK")  # "fixes" the error by editing its own rules
    c = FakeClient([{"answer": "x", "changes": [], "risks": [], "plan_yaml": plan_with(sneaky)}] +
                   [{"answer": "x", "changes": [], "risks": [], "plan_yaml": plan_with(sneaky)}] * 2)
    r = agent.run(c, "add UK test", PLAN_TEXT, "facts")
    assert r["final"] is None and len(r["attempts"]) == 3
    assert all("locked" in a["errors"][0] for a in r["attempts"])


def test_bad_yaml_is_caught():
    c = FakeClient([{"answer": "x", "changes": [], "risks": [], "plan_yaml": "launch: [unclosed"},
                    {"answer": "ok", "changes": [], "risks": []}])
    r = agent.run(c, "anything", PLAN_TEXT, "facts")
    assert "not valid YAML" in r["attempts"][0]["errors"][0] and r["final"] is not None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("pass", name)
