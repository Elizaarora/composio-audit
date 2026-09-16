# Composio Agent Audit — 100-App Toolkit Research

A small pipeline that researches whether 100 real-world apps (CRM, support,
messaging, ecommerce, fintech, dev infra, and more) can be turned into
AI-agent toolkits: what auth they use, whether credentials are self-serve or
gated, how broad the API surface is, and what would block building a toolkit
today. It's a scaled-down version of the research Composio does before
building a new toolkit — done here with an agent instead of by hand, with a
verification loop to keep the agent honest.

**Live case study:** _add your deployed GitHub Pages / hosting URL here before submitting_

## What's in this repo

| File | Purpose |
|---|---|
| `data/apps.json` | The 100 apps to research, as given in the assignment (category, name, docs hint) |
| `tools.py` | Grounding tools: fetch a real page, or search when the hint isn't enough (Composio SDK, with a no-key fallback) |
| `gemini.py` | Minimal Gemini REST client (see [Why REST, not the SDK](#why-rest-not-the-sdk)) |
| `research_agent.py` | The research agent — two-pass pipeline, writes `data/results.json` |
| `analyze.py` | Rolls the 100 results into the cross-cutting patterns (auth mix, gating by category, common blockers) → `data/report.json` |
| `verify_sample.py` | Picks a stratified 20-app sample for manual accuracy cross-checking → `data/verification_sample.json` |
| `page_template.html` + `build_page.py` | The case-study page source and its build script — injects the JSON data files into the template to produce `index.html` |
| `data/results.json` | Raw per-app output, both passes, for all 100 apps |
| `data/report.json` | Aggregated patterns consumed by the case study page |
| `data/verification_sample.json` | The 20-app worksheet: agent's pass-1/final answers vs. what an independent check of the real docs found |
| `data/verification.json` | The scored rollup of that worksheet — unclear-rate before/after, confirmed misses, confirmed wins |
| `data/baseline_direct_run/` | A full earlier run on the free (non-Composio) fallback backend, kept for comparison |
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

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here       # free: aistudio.google.com/apikey
COMPOSIO_API_KEY=your_key_here     # free: app.composio.dev/settings/api-keys (optional, see below)
```

Then run the pipeline:

```bash
python research_agent.py      # researches all 100 apps -> data/results.json (~15-25 min)
python analyze.py             # aggregates patterns -> data/report.json
python verify_sample.py       # picks the 20-app verification sample -> data/verification_sample.json
python build_page.py          # assembles page_template.html + the data files -> index.html
```

`verify_sample.py` leaves the `actual_*` fields blank. Filling them in is
the one genuinely manual step: read each sampled app's real docs and record
what's actually true, then compare against `agent_pass1` and `agent_final`
to see which pass got it right. That's how `data/verification.json` (the
scored rollup `build_page.py` reads) was produced for this run.

`COMPOSIO_API_KEY` is optional — omit it and the pipeline runs on the free
fallback backend automatically (see below). No paid account of any kind is
required to run this end to end.

## Using Composio's own SDK

The grounding layer runs on Composio's SDK: `tools.py` calls
`COMPOSIO_SEARCH_FETCH_URL_CONTENT` to fetch a docs page as clean markdown,
and `COMPOSIO_SEARCH_TAVILY` to search when a hint URL isn't enough — both
managed, no-extra-key actions under Composio's `COMPOSIO_SEARCH` toolkit,
called through `composio.tools.execute(...)` with just a `COMPOSIO_API_KEY`.
Concretely, this is the agent researching Composio's own future integrations
*using Composio*.

If `COMPOSIO_API_KEY` isn't set, both functions fall back automatically to a
free, no-key implementation (direct HTTP fetch + Bing HTML scraping) with
the exact same signatures — so the pipeline still runs for anyone without a
Composio account, and swapping backends never touches `research_agent.py`.
Every result in `data/results.json` records which `backend` produced it.

### Two grounding backends, compared

An earlier full 100-app run made entirely on the free fallback is kept at
`data/baseline_direct_run/` for comparison against the Composio-grounded run
in `data/results.json`:

| | Composio backend | Free fallback (direct fetch + Bing) |
|---|---|---|
| Fields left "unclear" (of 3 core fields × ~100 apps) | 17.0% | 53.1% |
| Apps with final "High" confidence | 97/100 | 92/100 |
| Apps that needed pass 2 | 93/100 | 89/100 |

Composio's `FETCH_URL_CONTENT` returns pre-cleaned markdown (vs. this
project's own HTML-stripping for the raw-HTTP path) and its `TAVILY` search
returns real content snippets directly instead of just links to fetch
separately — both cut down on the JS-shell/thin-page failures that drove
most of the free fallback's "unclear" rate.

## Known limitations

- The no-key search fallback (Bing HTML scraping) is a workaround, not a
  stable API, and could break if Bing changes its markup.
- Some docs sites are JS-rendered SPAs that return a near-empty page to a
  plain HTTP fetch, and some are bot-gated outright (403s were hit on both
  the pipeline's fetches and this README author's independent checks).
  Pass 2 mitigates the former but neither is fully solvable without a
  headless browser or an account.
- Gemini's own stated "confidence" is a signal, not ground truth — that's
  exactly why the manual verification sample exists.
- `has_mcp` is unreliable and should not be trusted as reported. It wasn't
  part of the 20-app stratified sample, so it got its own targeted
  spot-check: of 3 "Yes" claims checked against their own cited evidence
  URLs, 2 (Pumble, fanbasis) were confirmed false — neither source page
  mentions MCP at all. See `data/verification.json` →
  `field_reliability_notes` and the case study's verification section.
- `research_agent.py` targets `gemini-3.5-flash-lite` — this project's
  Gemini API key didn't have access to the 1.5/2.5 model family
  (`gemini-1.5-flash` and `gemini-2.5-flash-lite` both 404'd with "no
  longer available to new users"). Change the model name in `gemini.py` if
  your key has access to a different one.
