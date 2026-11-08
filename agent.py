"""The planning agent: Claude proposes, code checks, a human approves.

Flow for one request:
  1. Claude gets the brief, the current plan and a computed fact sheet (its only source of numbers).
  2. It must answer through one tool, `submit_proposal`: a written answer, plus an updated plan
     only if the plan should change.
  3. Code checks the proposal: the YAML parses, the human-owned `guardrails` block is unchanged,
     and the validator passes.
  4. If a check fails, the errors go back to Claude, which gets up to 2 more attempts.
  5. The result is shown as a diff. Nothing is applied until a person clicks Approve.
"""
import difflib

import yaml

from validate import validate

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_ATTEMPTS = 3

SYSTEM = """You are the paid media planning agent for a B2B SaaS company. You work for a Senior Performance Marketing Manager, who approves everything you propose.

Rules:
- Use only numbers from the FACT SHEET or the CURRENT PLAN. Never estimate or invent historical figures. If a number you need isn't there, say it's missing.
- "PostHog CPA" (channel spend / PostHog trials for that utm_source) is the source of truth. Platform-reported CPA is for diagnostics only.
- The `guardrails` block in the plan is set by the human. Never change it. If a request can't be met inside the guardrails, leave the plan unchanged and explain which guardrail blocks it and what would have to be true to unblock it.
- If the plan should change, return the COMPLETE updated plan as YAML in `plan_yaml`, keeping the exact same schema and every field. Change only what the request needs. If no change is needed, omit `plan_yaml`.
- Keep total budget, channel split and projected blended CPA inside the guardrails. If you add budget to something, say where it comes from.
- Be decisive. Lead `answer` with the decision in one sentence, then the evidence (with numbers), then the risk. Plain English a founder can follow. Under 200 words.
"""

TOOL = {
    "name": "submit_proposal",
    "description": "Submit your answer and, if the plan should change, the full updated plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "Decision first, then evidence with numbers, then risk. Under 200 words."},
            "changes": {"type": "array", "items": {"type": "string"}, "description": "One line per plan change. Empty if no change."},
            "risks": {"type": "array", "items": {"type": "string"}},
            "plan_yaml": {"type": "string", "description": "The complete updated plan YAML. Omit if the plan should not change."},
        },
        "required": ["answer", "changes", "risks"],
    },
}


def check(proposal, original_plan, allow_guardrail_edits=False):
    """Return (parsed_plan or None, errors, warnings, summary)."""
    text = proposal.get("plan_yaml")
    if not text:
        return None, [], [], None
    try:
        plan = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return None, [f"plan_yaml is not valid YAML: {e}"], [], None
    if not isinstance(plan, dict) or not {"launch", "guardrails", "meta", "google"} <= set(plan):
        return None, ["plan_yaml must contain launch, guardrails, meta and google sections."], [], None
    if not allow_guardrail_edits and plan["guardrails"] != original_plan["guardrails"]:
        changed = sorted(k for k in set(plan["guardrails"]) | set(original_plan["guardrails"])
                         if plan["guardrails"].get(k) != original_plan["guardrails"].get(k))
        return None, [f"You changed guardrails ({', '.join(changed)}). Guardrails are owned by the human and are locked. "
                      "Restore them exactly. If the request can't be met within them, return no plan_yaml and explain why."], [], None
    try:
        errors, warnings, summary = validate(plan)
    except Exception as e:  # malformed field types etc.
        return None, [f"Validator could not read the plan: {type(e).__name__}: {e}"], [], None
    return plan, errors, warnings, summary


def diff(original_text, new_plan):
    new_text = yaml.safe_dump(new_plan, sort_keys=False, width=120)
    old_text = yaml.safe_dump(yaml.safe_load(original_text), sort_keys=False, width=120)
    return "".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), "current plan", "proposed plan", n=1))


def run(client, brief, plan_text, facts, model=DEFAULT_MODEL, allow_guardrail_edits=False):
    """Returns {"attempts": [...], "final": attempt or None}. `client` is anthropic.Anthropic() or a test double."""
    original = yaml.safe_load(plan_text)
    messages = [{"role": "user", "content":
                 f"FACT SHEET (computed from the account export):\n{facts}\n\nCURRENT PLAN (YAML):\n{plan_text}\n\nREQUEST:\n{brief}"}]
    attempts = []
    for _ in range(MAX_ATTEMPTS):
        resp = client.messages.create(model=model, max_tokens=8000, system=SYSTEM, tools=[TOOL],
                                      tool_choice={"type": "tool", "name": "submit_proposal"}, messages=messages)
        block = next(b for b in resp.content if getattr(b, "type", None) == "tool_use")
        proposal = dict(block.input)
        plan, errors, warnings, summary = check(proposal, original, allow_guardrail_edits)
        attempt = {"proposal": proposal, "plan": plan, "errors": errors, "warnings": warnings, "summary": summary}
        attempts.append(attempt)
        if not errors:
            if plan is not None:
                attempt["diff"] = diff(plan_text, plan)
            return {"attempts": attempts, "final": attempt}
        messages += [
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                          "content": "The plan checks failed:\n- " + "\n- ".join(errors) +
                                          "\nFix these and resubmit, or return no plan_yaml and explain why the request can't be met."}]},
        ]
    return {"attempts": attempts, "final": None}
