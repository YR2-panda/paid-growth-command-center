# Deploy and submit: exact steps

Allow about 45 minutes. Do the steps in order.

## 1. Run it on your laptop (10 min)

```bash
unzip campaign-builder.zip && cd campaign-builder
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python test_rules.py && python test_agent.py  # expect 14 "pass" lines
streamlit run app.py                                     # opens http://localhost:8501
```

Click through all 4 tabs. The Diagnose tab should show a red flag for Search_NonBrand_UK ($15,090 spent, 0 conversions).

## 2. Get an Anthropic API key with a spending cap (5 min)

1. Go to console.anthropic.com → **API Keys** → **Create Key**. Name it `growth-command-center`.
2. Under **Billing / Limits**, set a low monthly spend limit (for example $20). Each agent run costs a few cents.
3. Never commit the key and never put it in the repo. You paste it into the app's sidebar when you use the app.

## 3. Test the agent for real (10 min)

In the local app, paste the key, open the Agent tab and run each preset button:

| Preset | What should happen |
|---|---|
| Add a UK test | Attempt 1 is blocked (UK tracking not verified). The agent then keeps UK paused and explains why. If it gets it right first time with no plan change, that's also correct. |
| CEO: double Meta | A clear "no, here's the staged plan" answer, usually with no plan change |
| Rebalance Google | A diff moving $3K from PMax to non-brand, checks pass. Click **Approve and apply** and the header numbers update. |

If you get a "model not found" error, change the **Claude model** field in the sidebar to a model your key can use (see docs.claude.com → Models).

Write down anything the agent got wrong. That goes in the "What the AI got wrong" section.

## 4. Put the code on GitHub (5 min)

Web option, no git needed:
1. github.com → **New repository** → name `paid-growth-command-center` → **Public** → Create.
2. Click **uploading an existing file**, drag in everything inside the `campaign-builder` folder (not the folder itself, and not `.venv`), then **Commit changes**.

Command-line option:
```bash
git init && git add . && git commit -m "Paid Growth Command Center"
git branch -M main
git remote add origin https://github.com/<your-username>/paid-growth-command-center.git
git push -u origin main
```

Check that `app.py` and `requirements.txt` are at the top level of the repo.

## 5. Deploy on Streamlit Community Cloud (5 min, free)

1. share.streamlit.io → sign in with GitHub.
2. **Create app** → deploy from GitHub → repository `paid-growth-command-center`, branch `main`, main file `app.py`.
3. **Advanced settings** → Python 3.12. Don't add the API key as a secret: reviewers paste their own.
4. **Deploy**. The first build takes 2 to 3 minutes. Copy the app URL.
5. Open the URL in a private browser window to confirm it loads without being signed in.

Free apps go to sleep after a few days without visits. Open the link the morning of your interview so it's awake.

## 6. Record the Loom (5 min max)

| Time | Show | Say |
|---|---|---|
| 0:00–0:30 | Header | "This is how I'd run launches: one plan file, checks written from this account's own mistakes, and an AI agent that proposes but can't approve." |
| 0:30–1:30 | Diagnose tab | The Meta chart: "After 9/22, Meta reported half the trials PostHog saw, so the tracking broke, not the ads." Then the UK flag: $15K, 0 trials. |
| 1:30–2:15 | Plan tab | Change AdvPlus to $60,000 → checks fail, export is blocked. Reset. Change the start date to Feb 1 → days become 28. |
| 2:15–3:45 | Agent tab | Run **Add a UK test**. Show attempt 1 blocked by the tracking rule and the agent backing off. Explain that it can't edit the guardrails, so it can't "fix" this by marking UK as verified. Then run **Rebalance Google**, show the diff, and approve. |
| 3:45–4:30 | Export tab | Download the zip and open `launch_summary.md` and `approvals.md`. "Everything imports paused." |
| 4:30–5:00 | README roadmap | Direct API push, tracking QA bot, daily decision loop. All plug into the same plan and checks. |

## 7. Fill in the assessment doc

- **Link to your build:** the GitHub repo URL and the Streamlit app URL.
- **Link to your AI chat history:** share this Claude conversation (Share → copy link). Add the ChatGPT conversation link too if you used it. Comparing the two is good evidence that you were steering the AI.
- **Loom link.**
- **What the AI got wrong:** keep the brand-check bug, and add anything you saw in step 3.
- Set the doc to **Anyone with the link → Viewer**, then open it in a private window to check.

## 8. Before the live interview

- [ ] Open the app link so it's awake. Have the API key ready to paste.
- [ ] Have the local version running as a backup (`streamlit run app.py`).
- [ ] Be ready for "what happens if the AI is wrong?". Answer: the checks, the guardrail lock, the diff and Approve, and the agent tests (`test_agent.py`) that use a fake model to prove the guardrails hold.
