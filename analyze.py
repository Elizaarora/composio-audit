"""
Turn data/results.json into the aggregate patterns the case study leads with:
auth method distribution, self-serve vs gated by category, buildability
verdicts, common blockers, and which apps needed the pass-2 grounding loop.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

RESULTS_PATH = Path(__file__).parent / "data" / "results.json"
OUT_PATH = Path(__file__).parent / "data" / "report.json"


def normalize_gating(g: str) -> str:
    g = (g or "").lower()
    if "unclear" in g:
        return "Unclear"
    if "open source" in g:
        return "Open source"
    if "self-serve free" in g:
        return "Self-serve (free)"
    if "self-serve" in g:
        return "Self-serve (paid/trial)"
    if "admin approval" in g:
        return "Admin approval required"
    if "partner" in g or "contact-sales" in g or "gated" in g:
        return "Partner/contact-sales gated"
    return "Other"


def normalize_auth(a: str) -> str:
    a = (a or "").lower()
    if "unclear" in a:
        return "Unclear"
    if "oauth" in a:
        return "OAuth2"
    if "api key" in a or "apikey" in a:
        return "API key"
    if "basic" in a:
        return "Basic auth"
    if "token" in a:
        return "Token"
    if "webhook" in a:
        return "Webhook secret"
    return "Other"


def main():
    results = json.loads(RESULTS_PATH.read_text())
    valid = [r for r in results if "final" in r and "error" not in r]
    errored = [r for r in results if "error" in r]

    auth_counts = Counter(normalize_auth(r["final"]["auth_method"]) for r in valid)
    gating_counts = Counter(normalize_gating(r["final"]["gating"]) for r in valid)
    verdict_counts = Counter(r["final"]["buildability_verdict"] for r in valid)
    confidence_counts = Counter(r["final"]["confidence"] for r in valid)

    gating_by_category = defaultdict(Counter)
    verdict_by_category = defaultdict(Counter)
    for r in valid:
        gating_by_category[r["category"]][normalize_gating(r["final"]["gating"])] += 1
        verdict_by_category[r["category"]][r["final"]["buildability_verdict"]] += 1

    blockers = Counter(
        r["final"]["blocker"].strip() for r in valid
        if r["final"]["blocker"] and r["final"]["blocker"].lower() != "none"
    )

    pass2_count = sum(1 for r in valid if r.get("used_pass2"))
    low_confidence_final = [r["name"] for r in valid if r["final"]["confidence"] == "Low"]
    fetch_failed = [r["name"] for r in valid if r["pass1"]["fetch_status"] != 200]

    report = {
        "total_apps": len(results),
        "valid_apps": len(valid),
        "errored_apps": [r["name"] for r in errored],
        "auth_counts": dict(auth_counts.most_common()),
        "gating_counts": dict(gating_counts.most_common()),
        "verdict_counts": dict(verdict_counts.most_common()),
        "confidence_counts": dict(confidence_counts.most_common()),
        "gating_by_category": {k: dict(v) for k, v in gating_by_category.items()},
        "verdict_by_category": {k: dict(v) for k, v in verdict_by_category.items()},
        "top_blockers": dict(blockers.most_common(10)),
        "pass2_count": pass2_count,
        "pass2_pct": round(100 * pass2_count / len(valid), 1) if valid else 0,
        "low_confidence_final": low_confidence_final,
        "fetch_failed_pass1": fetch_failed,
    }

    OUT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
