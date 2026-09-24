# Composio Agent Audit — 100-App Toolkit Research

**By Eliza Arora**

Researches whether 100 real-world apps can become AI-agent toolkits: auth
method, self-serve vs. gated, API surface, and the main blocker if any —
done with an agent instead of by hand, with a verification loop to check it.

**Live case study:** https://elizaarora.github.io/composio-audit/

## How it works

Asking an LLM "what auth does Stripe use?" from memory gives confident,
sometimes-wrong answers. Instead, each app is grounded in a real fetched page:

1. **Fetch** the docs hint via Composio's `COMPOSIO_SEARCH_FETCH_URL_CONTENT`.
2. **Extract, grounded** — Gemini fills the schema only from that fetched
   text; unsupported fields must say "unclear," never guess. (Pass 1.)
3. **Escalate on low confidence** — a failed/thin fetch or an unclear core
   field triggers pass 2: search via `COMPOSIO_SEARCH_TAVILY` for a better
   URL, then re-extract from the combined text.
4. **Aggregate** (`analyze.py`) into cross-cutting patterns.
5. **Verify** — a stratified 20-app sample is checked by hand against real
   docs, comparing pass-1 vs. final answers to see what the loop actually fixed.

**Where a human was needed:** setting the escalation threshold, reading the
verification sample's real docs (the agent's own confidence isn't proof),
judging ambiguous gating calls, and diagnosing a Windows Application Control
policy that blocked the `google-generativeai` SDK's native `grpc` dependency
(`gemini.py` calls the Gemini REST API directly instead).

## Using Composio's own SDK

The grounding layer is Composio's SDK (`tools.py`), not a generic scraper:
`COMPOSIO_SEARCH_FETCH_URL_CONTENT` for fetching, `COMPOSIO_SEARCH_TAVILY`
for search — managed, no-extra-key actions called via
`composio.tools.execute(...)`. If `COMPOSIO_API_KEY` isn't set, both
functions fall back automatically to a free implementation (direct HTTP
fetch + Bing search) behind the same signatures, so the pipeline still runs
without a Composio account. Every result records which backend produced it.

An earlier full run on the free fallback is kept at
`data/baseline_direct_run/` for comparison:

| | Composio backend | Free fallback |
|---|---|---|
| Fields left "unclear" | 17.0% | 53.1% |
| Apps with "High" confidence | 97/100 | 92/100 |

## Running it yourself

```bash
python -m venv venv && source venv/Scripts/activate   # adjust for your OS
pip install -r requirements.txt
```

`.env` in the project root:
```
GEMINI_API_KEY=your_key_here       # free: aistudio.google.com/apikey
COMPOSIO_API_KEY=your_key_here     # free, optional: app.composio.dev/settings/api-keys
```

```bash
python research_agent.py   # -> data/results.json (~15-25 min)
python analyze.py          # -> data/report.json
python verify_sample.py    # -> data/verification_sample.json (actual_* fields left blank)
python build_page.py       # -> index.html
```

`verify_sample.py`'s `actual_*` fields are the one manual step: read each
sampled app's real docs, fill in what's true, and compare against
`agent_pass1`/`agent_final`. That produced `data/verification.json`, which
`build_page.py` reads for the case study's verification section.

## What's in this repo

`data/apps.json` (the 100 apps) → `research_agent.py` (+ `tools.py`,
`gemini.py`) → `data/results.json` → `analyze.py` → `data/report.json`,
alongside `verify_sample.py` → `data/verification_sample.json` →
`data/verification.json`. `page_template.html` + `build_page.py` assemble
all of the above into `index.html`, the self-contained case study.

## Known limitations

- The Bing-scraping fallback is a workaround, not a stable API.
- Some docs sites are JS-shell SPAs or bot-gated (403s hit both the
  pipeline and this author's independent checks) — pass 2 helps, doesn't
  fully solve it.
- **`has_mcp` is unreliable.** A targeted spot-check (not part of the main
  sample) found 2 of 3 "Yes" claims checked (Pumble, fanbasis) were false —
  neither source page mentions MCP at all. See `data/verification.json` →
  `field_reliability_notes`.
- `research_agent.py` targets `gemini-3.5-flash-lite` because this
  project's key lacked access to `gemini-1.5-flash`/`gemini-2.5-flash-lite`
  (both 404'd). Change the model in `gemini.py` if needed.
