# Composio Agent Audit — 100-App Toolkit Research

A small pipeline that researches whether 100 real-world apps (CRM, support,
messaging, ecommerce, fintech, dev infra, and more) can be turned into
AI-agent toolkits: what auth they use, whether credentials are self-serve or
gated, how broad the API surface is, and what would block building a toolkit
today. It's a scaled-down version of the research Composio does before
building a new toolkit — done here with an agent instead of by hand, with a
verification loop to keep the agent honest.

**Live case study:** _[link to be added on submission]_

## What's in this repo

| File | Purpose |
|---|---|
| `data/apps.json` | The 100 apps to research, as given in the assignment (category, name, docs hint) |
| `tools.py` | Grounding tools: fetch a real page, or search when the hint isn't enough |
| `gemini.py` | Minimal Gemini REST client (see [Why REST, not the SDK](#why-rest-not-the-sdk)) |
| `research_agent.py` | The research agent — two-pass pipeline, writes `data/results.json` |
| `analyze.py` | Rolls the 100 results into the cross-cutting patterns (auth mix, gating by category, common blockers) |
| `verify_sample.py` | Picks a stratified 20-app sample for manual accuracy cross-checking |
| `data/results.json` | Raw per-app output, both passes, for all 100 apps |
| `data/report.json` | Aggregated patterns consumed by the case study page |
| `data/verification_sample.json` | The accuracy-check worksheet: agent's answer vs. what a human found reading the real docs |
| `index.html` | The self-contained case study: findings, patterns, agent design, verification results |

## How it works

**The problem with just asking an LLM.** The obvious first draft of this
agent — ask Gemini "what auth does Stripe use?" — produces confident,
plausible-sounding answers that are sometimes just wrong, because the model
is recalling training data, not reading current docs. Since the assignment's
own success criterion is *verified accuracy*, that approach doesn't hold up.

**What this agent does instead:**

1. **Fetch.** For each app, fetch the real page at its given docs hint (or
   homepage) and strip it down to text (`tools.py::fetch_page`).
2. **Extract, grounded.** Feed that fetched text — not the model's general
   knowledge — to Gemini with a strict instruction: answer each field only
   from what's in the text, and say "unclear from fetched text" rather than
   guess. This is pass 1.
3. **Escalate on low confidence.** If pass 1's fetch failed, returned a thin
   page (a JS-rendered shell with no real content is common for SPA docs
   sites), or the model itself flagged a field as unclear, the agent runs a
   pass 2: search for a better docs URL, fetch it too, and re-extract from
   the combined text. This is the grounding loop — it exists specifically to
   catch the cases pass 1 wasn't enough for, not to redo everything.
4. **Aggregate.** `analyze.py` clusters all 100 results into the patterns
   that actually matter: which auth method dominates, which categories skew
   self-serve vs. gated, the most common blocker, where the API surface is
   thin or missing.
5. **Verify.** A stratified sample (2 apps per category, 20 total) is
   cross-checked by hand against the real documentation, comparing what the
   agent said after pass 1 against its final answer after pass 2 — showing
   where the grounding loop actually fixed something, and being honest about
   the cases it didn't.

### Why REST, not the SDK

`google-generativeai` depends on `grpc`, whose native `cygrpc` binary was
blocked outright by this machine's Windows Application Control policy — not
a fixable dependency issue, a platform security policy. `gemini.py` calls
the same Gemini API over plain HTTPS with `requests` instead, which sidesteps
the native dependency entirely and turned out to be simpler to reason about.

### Where a human was needed

- **Choosing the escalation trigger and its threshold** (thin-page character
  count, which fields count as "unclear enough" to justify pass 2) — a
  judgment call about where grounding effort is worth the extra API calls.
- **Reading the verification sample's real docs pages** — the agent's own
  self-reported confidence isn't proof of accuracy; someone has to actually
  open the docs and check.
- **Deciding what "gated" means in ambiguous cases** — e.g. an app with a
  public API that nonetheless requires a sales call for production keys is
  a judgment call the schema can't fully automate.
- **Apps the agent couldn't resolve at all** — a small number of hints
  point to marketing pages with no discoverable API docs; those are called
  out explicitly rather than papered over with a guess.

## Running it yourself

```bash
python -m venv venv
source venv/Scripts/activate        # Windows Git Bash / macOS / Linux: adjust as needed
pip install -r requirements.txt
```

Create a `.env` file in the project root with a free Gemini API key
([aistudio.google.com/apikey](https://aistudio.google.com/apikey)):

```
GEMINI_API_KEY=your_key_here
```

Then run the pipeline:

```bash
python research_agent.py      # researches all 100 apps -> data/results.json (~10-15 min)
python analyze.py             # aggregates patterns -> data/report.json
python verify_sample.py       # picks the 20-app verification sample -> data/verification_sample.json
```

`verify_sample.py` leaves the `actual_*` fields blank — fill those in by
reading each sampled app's real docs, then compare against `agent_pass1`
and `agent_final` to score accuracy per pass.

No Composio account is required to run this — see the note on scope below.

## A note on "using Composio's SDK"

Composio's toolkits are per-app integrations (Gmail, Slack, GitHub, and so
on), not a generic "fetch or search an arbitrary third-party doc site" tool
— so there wasn't a literal Composio SDK call that fit *this specific job*
of researching 100 *other* companies' docs. `tools.py` is written as a small,
swappable interface (`fetch_page`, `search_web`) for exactly that reason: it
currently runs on free, no-key methods, but a Composio-backed search/browser
toolkit would plug in behind the same two functions without touching the
rest of the pipeline.

## Known limitations

- The no-key search fallback (Bing HTML scraping) is a workaround, not a
  stable API, and could break if Bing changes its markup.
- Some docs sites are JS-rendered SPAs that return a near-empty page to a
  plain HTTP fetch; pass 2 mitigates this but doesn't fully solve it for
  every app.
- Gemini's own stated "confidence" is a signal, not ground truth — that's
  exactly why the manual verification sample exists.
