"""
Research agent: for each app in data/apps.json, fetch real docs/site text and
ask Gemini to extract the assignment's schema *only* from that fetched text.

Two passes, logged separately so the before/after is visible in the output:
  Pass 1 (fast):     fetch the given hint URL only, extract from it.
  Pass 2 (targeted):  only runs for apps pass 1 flagged low-confidence
                       (fetch failed, thin/JS-shell page, or the model itself
                       said a field was unclear). Searches for a better docs
                       URL, fetches it too, and re-extracts from the combined
                       text.

This is the grounding loop referenced in the case study: pass 2 exists
specifically to catch cases where the hint URL alone wasn't enough, not to
re-run everything twice.
"""

import json
import time
from pathlib import Path

from dotenv import load_dotenv

from gemini import generate_json
from tools import backend, fetch_page, search_web

load_dotenv()

APPS_PATH = Path(__file__).parent / "data" / "apps.json"
OUT_PATH = Path(__file__).parent / "data" / "results.json"

THIN_TEXT_THRESHOLD = 400  # below this, a 200 is probably a JS shell, not real content
RATE_LIMIT_SLEEP = 3.0

RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "description": {"type": "string"},
        "auth_method": {"type": "string"},
        "gating": {"type": "string"},
        "api_surface": {"type": "string"},
        "has_mcp": {"type": "string"},
        "buildability_verdict": {"type": "string", "enum": ["Ready", "Friction", "Blocked"]},
        "blocker": {"type": "string"},
        "evidence_url": {"type": "string"},
        "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
    },
    "required": [
        "category", "description", "auth_method", "gating", "api_surface",
        "has_mcp", "buildability_verdict", "blocker", "evidence_url", "confidence",
    ],
}


EXTRACTION_PROMPT = """You are extracting facts about the app "{name}" for a
developer researching whether it can be turned into an AI agent tool.

Below is TEXT FETCHED FROM A REAL WEB PAGE about this app. Base every field
ONLY on this text. Do not use outside/prior knowledge about the app. If the
text does not contain enough information for a field, you MUST answer that
field with exactly "Unclear from fetched text" -- never guess.

SOURCE URL(S): {urls}

FETCHED TEXT:
---
{text}
---

Return fields:
- category: broad category (e.g. CRM, Support, Messaging, Dev/Infra, Fintech, AI/Research)
- description: one line, what the app does
- auth_method: e.g. OAuth2, API key, Basic auth, token, webhook secret -- or "Unclear from fetched text"
- gating: one of "Self-serve free", "Self-serve paid/trial", "Requires admin approval", "Partner/contact-sales gated", "Open source", or "Unclear from fetched text"
- api_surface: e.g. "REST", "GraphQL", "REST + GraphQL", "CLI only", "No public API found" -- or "Unclear from fetched text"
- has_mcp: "Yes", "No", or "Unclear from fetched text" -- whether the text mentions an MCP server
- buildability_verdict: exactly one of "Ready", "Friction", "Blocked"
- blocker: the main blocker/friction point in a few words, or "None" if Ready
- evidence_url: the single URL from SOURCE URL(S) above that best supports your answer
- confidence: "High", "Medium", or "Low" -- your own confidence that the fetched text actually supports these answers
"""


def extract(app: dict, text: str, urls: list[str]) -> dict:
    prompt = EXTRACTION_PROMPT.format(
        name=app["name"], urls=", ".join(urls) or "none", text=text or "(fetch failed, no text)"
    )
    return generate_json(prompt, RESEARCH_SCHEMA)


def needs_pass2(fetch_result: dict, extraction: dict) -> bool:
    if not fetch_result["ok"] or fetch_result["char_count"] < THIN_TEXT_THRESHOLD:
        return True
    if extraction.get("confidence") == "Low":
        return True
    if any(extraction.get(f) == "Unclear from fetched text" for f in ("auth_method", "gating", "api_surface")):
        return True
    return False


def rank_search_results(results: list[dict]) -> list[dict]:
    good_keywords = ("docs", "developer", "api", "reference")
    return sorted(
        results,
        key=lambda r: any(k in r["url"].lower() for k in good_keywords),
        reverse=True,
    )[:2]


def research_app(app: dict) -> dict:
    print(f"[{app['id']:>3}] {app['name']} -- pass 1 (fetch {app['hint']})")
    fetch1 = fetch_page(app["hint"])
    extraction1 = extract(app, fetch1["text"], [fetch1["final_url"]])
    record = {
        "id": app["id"],
        "category": app["category"],
        "name": app["name"],
        "hint": app["hint"],
        "pass1": {
            "fetch_status": fetch1["status_code"],
            "char_count": fetch1["char_count"],
            "fetch_error": fetch1["error"],
            "extraction": extraction1,
        },
        "pass2": None,
        "final": extraction1,
        "used_pass2": False,
        "backend": backend(),
    }

    if needs_pass2(fetch1, extraction1):
        time.sleep(RATE_LIMIT_SLEEP)
        query = f"{app['name']} API documentation authentication"
        print(f"      -- pass 2 (low confidence, searching: {query!r})")
        search_results = search_web(query)
        top_results = rank_search_results(search_results)

        combined_text = fetch1["text"]
        all_urls = [fetch1["final_url"]]
        for r in top_results:
            if r.get("content") and len(r["content"]) > 200:
                # search backend (Composio/Tavily) already returned real text
                combined_text += "\n\n" + r["content"]
                all_urls.append(r["url"])
            else:
                # no-key fallback: search gave a URL only, fetch it separately
                fetch2 = fetch_page(r["url"])
                if fetch2["ok"] and fetch2["char_count"] > 200:
                    combined_text += "\n\n" + fetch2["text"]
                    all_urls.append(fetch2["final_url"])

        extraction2 = extract(app, combined_text[:10000], all_urls)
        record["pass2"] = {
            "search_query": query,
            "candidate_urls": [r["url"] for r in top_results],
            "extraction": extraction2,
        }
        record["final"] = extraction2
        record["used_pass2"] = True

    return record


def main():
    apps = json.loads(APPS_PATH.read_text())
    results = []
    for i, app in enumerate(apps):
        try:
            results.append(research_app(app))
        except Exception as e:
            print(f"      !! failed: {e}")
            results.append({"id": app["id"], "name": app["name"], "category": app["category"], "error": str(e)})
        if i < len(apps) - 1:
            time.sleep(RATE_LIMIT_SLEEP)
        if (i + 1) % 10 == 0:
            OUT_PATH.write_text(json.dumps(results, indent=2))
            print(f"      -- checkpoint saved ({i + 1}/{len(apps)})")

    OUT_PATH.write_text(json.dumps(results, indent=2))
    pass2_count = sum(1 for r in results if r.get("used_pass2"))
    print(f"\nDone. {len(results)} apps researched, {pass2_count} needed pass 2. Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
