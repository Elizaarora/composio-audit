"""
Pick a stratified verification sample (2 apps per category = 20 apps) from
data/results.json and emit a worksheet for manual cross-checking against
real docs. Fill in the "actual_*" fields by hand (or via a second grounded
pass) after reading each app's real documentation, then run score_sample.py.
"""

import json
import random
from pathlib import Path

RESULTS_PATH = Path(__file__).parent / "data" / "results.json"
OUT_PATH = Path(__file__).parent / "data" / "verification_sample.json"

random.seed(42)  # reproducible sample selection


def main():
    results = json.loads(RESULTS_PATH.read_text())
    valid = [r for r in results if "final" in r and "error" not in r]

    by_category = {}
    for r in valid:
        by_category.setdefault(r["category"], []).append(r)

    sample = []
    for category, apps in by_category.items():
        picks = random.sample(apps, min(2, len(apps)))
        sample.extend(picks)

    worksheet = []
    for r in sample:
        worksheet.append({
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "hint": r["hint"],
            "agent_pass1": {
                "auth_method": r["pass1"]["extraction"]["auth_method"],
                "gating": r["pass1"]["extraction"]["gating"],
                "api_surface": r["pass1"]["extraction"]["api_surface"],
                "buildability_verdict": r["pass1"]["extraction"]["buildability_verdict"],
            },
            "agent_final": {
                "auth_method": r["final"]["auth_method"],
                "gating": r["final"]["gating"],
                "api_surface": r["final"]["api_surface"],
                "buildability_verdict": r["final"]["buildability_verdict"],
            },
            "evidence_url": r["final"]["evidence_url"],
            # to be filled in by hand after reading the real docs:
            "actual_auth_method": None,
            "actual_gating": None,
            "actual_api_surface": None,
            "actual_buildability_verdict": None,
            "pass1_correct_fields": None,   # list of field names pass1 got right
            "final_correct_fields": None,   # list of field names final answer got right
            "notes": None,
        })

    OUT_PATH.write_text(json.dumps(worksheet, indent=2))
    print(f"Sampled {len(worksheet)} apps across {len(by_category)} categories -> {OUT_PATH}")
    for w in worksheet:
        print(f"  [{w['id']:>3}] {w['name']} ({w['category']})")


if __name__ == "__main__":
    main()
