# Second Thought (再想想)

A personal finance assistant for people whose spending runs ahead of their intentions: adults with ADHD, people with bipolar disorder, emotional spenders and young shoppers who buy on impulse in live streams or with buy-now-pay-later.

It does the Topic A jobs (budgeting, bill analysis, spending insights, recommendations) and adds a pause between the urge and the payment. The agent can act, but only inside limits the user set while calm, and it can never move money to anyone else.

FinTechathon 2026, International Track, Topic A (Personal Finance Assistant).

Team: Alexander Schutz (Munich Business School) and Constantin Coblitz.

## Quick start

```bash
pip install -r requirements.txt
python scripts/generate_demo_data.py      # synthetic persona "Mei", no real data
streamlit run app/streamlit_app.py
```

Open http://localhost:8501 and click **Load demo persona (Mei)** in the sidebar. The demo clock is set to 23:50 so the night-time features show up whenever you record.

No API key is needed. Without one the assistant runs in offline mode (keyword intents in English and Chinese, same tools, same gate). To use a language model, see [LLM setup](#llm-setup).

## What it does

| Feature | Topic A job | Tier |
| --- | --- | --- |
| Unified money view and **safe to spend today** | Smart budgeting | T0 |
| Bill check: subscriptions, overlapping services, converted free trials, price rises, late fees, open instalments ("ADHD tax" report), cancellation drafts | Bill analysis | T0, drafts T2 |
| Money mirror: impulse share, night share, live-stream share, spending on stressful days, one suggestion | Spending insights | T0 |
| **The Pause**: impulse score with reasons, cost in hours of work, HALT check, park / skip / buy | Recommendations | T1 |
| Parking lot with timers, save-the-urge transfers to the user's own pot (sandbox) | Recommendations | T2, T3 within a daily cap |
| Regret rescue: return windows (7 days in China, 14 in the EU) and return request drafts | Recommendations | T2 |
| Calm-state plan: night hold, category caps, blocked categories, trusted ally | Budgeting | T3 |
| **Checkout Pause** browser extension: stops the shop's buy button, asks "do you really want this?" with the reasons, then shows what money is left afterwards; buying anyway unlocks after a countdown | Recommendations | T1, decisions T2 |
| Crisis protocol: stops the finance flow and shows local helplines (12356 in China) | Safety | always on |

We design around **patterns, not diagnoses**. Users pick descriptions like "I buy on impulse late at night". The app never asks for or stores a medical label.

## Demo in five steps

1. Load the demo persona. Today tab: safe to spend is ¥183.
2. Chat: `check my subscriptions and fees` → 8 subscriptions, 3 probably forgotten (a converted free trial and two on an old foreign account), 2 fees, drafts waiting for confirmation.
3. Chat: `Should I buy this ¥899 jacket from the live stream?` → score 70/100 (night, third purchase this hour, live stream, trigger category). The calm-state plan holds it for 12 hours and moves ¥90 to the savings pot.
4. Chat: `remove my night limit` → prepared for confirmation; after confirming it is queued for 24 hours.
5. Parking & returns tab: the ¥459 earphones from last night have 6 days left. Plan & safety tab: permission tiers, audit log, "verify hash chain".

The same script runs headless and writes the execution evidence:

```bash
python scripts/run_demo.py            # writes evidence/
```

## Browser extension: Checkout Pause

The app only helps if people open it. The extension (Chrome and Edge, Manifest V3, in `extension/`) puts the pause on the checkout button itself, on Taobao, Tmall, JD, Pinduoduo, Amazon, Zalando and other shops:

1. **First question.** The click on 立即购买 / 提交订单 / Buy now / Zur Kasse is stopped. "Do you really want to buy this now?" with the impulse score and every reason, the hours of work, and any calm-state hold.
2. **Second warning.** What is left after the purchase: safe to spend today before → after, money until payday, the category cap, how many days the savings goal moves back.
3. **Her call.** Park it (24 h) or don't buy in one tap. "Buy anyway" unlocks after a countdown (up to 20 s when her own rule holds the item), is logged, and then the shop's checkout continues.

Set up:

```bash
python -m second_thought.extension_api --region CN   # local API on 127.0.0.1:8765, prints a pairing code
python scripts/serve_demo_shop.py                    # optional fictional shop: http://127.0.0.1:8770/demo-shop/
```

Then open `chrome://extensions` (or `edge://extensions`), switch on Developer mode, choose **Load unpacked**, pick the `extension/` folder and type the pairing code in the extension's settings. Without the app the extension still asks twice, using the budget and night window from its settings.

Privacy and security: the content script runs only on listed shop domains; it sends amount, currency, product title, shop name and matched signal words, and only to the app on the same computer. The local API binds to 127.0.0.1, needs the pairing code on every call, refuses web-page origins and foreign Host headers, and goes through the same permission gate and audit log as the app. End-to-end check in a real Chromium: `pip install -r requirements-dev.txt`, then `python scripts/extension_e2e.py`.

## Payment connectors

One connector interface. We are explicit about what is real.

| Provider | How | Status |
| --- | --- | --- |
| Alipay 支付宝 | Parser for the user's exported bill CSV (GBK, info block above the table) | Real parser |
| WeChat Pay 微信支付 | Parser for the exported bill (CSV or XLSX) | Real parser |
| Huabei 花呗 / JD Baitiao 白条 | Instalments and BNPL detected from bill lines | Real, via parsers |
| UnionPay 银联 | Same interface, synthetic card statement with MCC codes | Mock |
| Plaid Sandbox (US, CA, UK, EU banks) | `/sandbox/public_token/create` → `/item/public_token/exchange` → `/transactions/sync` | Real sandbox API (needs free keys), fixture offline |
| e-CNY 数字人民币 | Capped sub-wallet as a hard limit | Roadmap |
| ISO 20022 camt.053 / MT940 | EU bank statement files | Roadmap |

As far as we know, Alipay's and WeChat Pay's open platforms are built for merchants receiving payments; there is no public API that lets a third-party app read a consumer's own history. The bill export the user triggers in the app is the route that works today and keeps the user in control of what is shared.

Live Plaid pull:

```bash
export PLAID_CLIENT_ID=... PLAID_SECRET=...   # sandbox keys from dashboard.plaid.com
python scripts/run_demo.py --live-plaid        # request ids land in evidence/plaid_requests.jsonl
```

## Architecture

```
connectors/   alipay_csv, wechat_bill, plaid_sandbox, unionpay_mock  -> Transaction
engine/       ledger (FX), categories, risk_score, safe_to_spend, subscriptions, returns, insights
policy/       gate (tiers), plan (calm-state rules, 24h cooldown), rules_engine (T3), audit_log (hash chain)
agent/        tools (gated toolbox), router (offline agent), llm (OpenAI-compatible), safety (crisis, redaction)
app/          streamlit_app.py (EN / 中文)
```

Main rule: **the model talks, the code calculates.** Every number comes from deterministic Python; the model only explains results and chooses which tool to call.

### Impulse risk score (0-100)

| Signal | Points |
| --- | --- |
| Purchase between 23:00 and 05:00 | 20 |
| 3 or more purchases within 60 minutes | 20 |
| Live-stream or flash-sale merchant | 15 |
| Amount above the 90-day category mean + 2 standard deviations | 15 |
| Category on the user's trigger list | 15 |
| Instalments / BNPL | 10 |
| Shopping festival (Double 11, 618, Black Friday) or 2 days after payday | 10 |
| Low mood or high stress logged in the last 3 hours | 10 |

Capped at 100. Below 40 green, 40-69 amber, 70+ red.

### Safe to spend today

`S = (B + I - F - G - R) / d` with B balances, I income expected before payday, F bills, repayments and subscriptions due before payday, G savings-goal share, R buffer (10% of monthly fixed costs), d days to payday.

## Security

| Tier | The agent may | Guard |
| --- | --- | --- |
| T0 Observe | Read and compute | No side effects |
| T1 Advise | The Pause, nudges | No side effects |
| T2 Confirm | Park, save to own pot, drafts, caps, rule changes | The model can only propose; a person taps confirm |
| T3 Bounded | Night holds, auto-save, ally alert | Only the deterministic rules engine, only rules set while calm, daily caps |
| Never | Pay third parties, borrow, trade, change credentials | These tools do not exist |

- **Asymmetric friction**: safer changes apply now; riskier ones (fewer protections, more agent power, removing the ally) wait 24 hours. Exception: the "I feel unsafe" exit removes the ally immediately.
- **Essentials are never held** (groceries, health, transport, utilities, housing, education).
- **Hash-chained audit log** of every call, proposal, confirmation and denial (`policy/audit_log.py`).
- **Prompt injection**: transaction text is data. The offline agent only reads what the user typed; the LLM agent can at most propose T2 actions; T3 is unreachable for it.
- **Redaction** before any model call: names, emails, phone numbers; order and account numbers become reversible tokens.
- **Data residency**: state is stored per region (`.st_state/cn`, `.st_state/eu`); CN users only use CN-hosted models (DeepSeek, Qwen).
- **Encryption at rest** (optional in the demo): set `ST_ENCRYPTION_KEY` from `python scripts/make_key.py`.
- Not a medical device, not financial advice, no ads, no credit products.

Permission tiers and the full known-risk list: [docs/security_self_assessment.pdf](docs/security_self_assessment.pdf). Architecture, algorithms and security design in detail: [docs/technical_documentation.md](docs/technical_documentation.md) (PDF: [docs/technical_documentation.pdf](docs/technical_documentation.pdf)).

## LLM setup

Any OpenAI-compatible endpoint works. Copy `.env.example` and set:

```bash
export LLM_PROVIDER=deepseek        # deepseek | qwen | qwen-intl | custom
export LLM_API_KEY=...
# custom: LLM_BASE_URL=... LLM_MODEL=... LLM_REGION=CN|INTL
```

Then tick "Allow sending redacted data to a language model" in the sidebar (consent is recorded in the audit log). Replies from the model are labeled "AI-generated".

## Tests

```bash
pytest -q
```

51 tests: parsers (GBK, info blocks, XLSX), risk score, safe-to-spend, subscription flags, return windows, gate tiers, cooldowns, essentials, daily caps, audit-chain tampering, crisis detection, redaction, prompt injection, data residency, a full headless demo run, the extension's local API (pairing, origin and host checks, holds, decisions) and its checkout detection (run in headless Chromium via Playwright; skipped if no browser is installed).

## Deployment

```bash
docker build -t second-thought .
docker run -p 8501:8501 second-thought
```

## Evidence for the submission

`evidence/` (from `scripts/run_demo.py`): `demo_video.mp4` (4:20, recorded with `scripts/record_demo_video.py` and `scripts/record_extension_video.py`), `extension/` (screenshots in English and Chinese plus `e2e_results.txt` from `scripts/extension_e2e.py`), transcript, hash-chained `audit_log.jsonl`, sandbox operations, Plaid request log, summary with the chain check. Verify any log with:

```bash
python scripts/verify_audit_log.py evidence/audit_log.jsonl
```

## Data and licences

All demo data is synthetic and generated by `scripts/generate_demo_data.py`. Merchant and platform names appear only the way they would in a person's own bill export; they say nothing about those companies, and the demo shop for the extension is fictional. Third-party packages: Streamlit (Apache 2.0), pandas (BSD 3), openpyxl (MIT), requests (Apache 2.0), cryptography (Apache 2.0 / BSD), pytest (MIT).
