"""Assemble index.html from page_template.html + the data/*.json files.

Run this after research_agent.py / analyze.py produce fresh data, or after
editing page_template.html's copy/markup, to regenerate index.html.
"""

import datetime
import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"

template = (ROOT / "page_template.html").read_text(encoding="utf-8")
results = json.loads((DATA / "results.json").read_text())
report = json.loads((DATA / "report.json").read_text())
verification = json.loads((DATA / "verification.json").read_text())
sample = json.loads((DATA / "verification_sample.json").read_text())

def to_row(r):
    f = r["final"]
    return [
        r["id"], r["category"], r["name"], r["hint"],
        f["auth_method"], f["gating"], f["api_surface"], f["has_mcp"],
        f["buildability_verdict"], f["blocker"], f["evidence_url"], f["confidence"],
        r.get("used_pass2", False),
    ]

table_rows = [to_row(r) for r in results if "final" in r and "error" not in r]

ready_pct = round(100 * report["verdict_counts"]["Ready"] / report["valid_apps"])
oauth_apikey_pct = round(100 * (report["auth_counts"]["OAuth2"] + report["auth_counts"]["API key"]) / report["valid_apps"])
gating_unclear_pct = round(100 * report["gating_counts"]["Unclear"] / report["valid_apps"])

headline = (
    f'<b>{oauth_apikey_pct}% of these apps authenticate with OAuth2 or a plain API key</b> &mdash; the mechanics '
    f'of authentication are rarely what blocks agent integration. What blocks it is approval: '
    f'<b>{gating_unclear_pct}% of docs never state</b> whether access is self-serve, because that’s a pricing-page '
    f'question, not a docs-page one. The friction that does show up concentrates hard in two places: Marketing &amp; '
    f'Ads, where 4 of 10 apps need a manual platform review (Google, Meta, LinkedIn, Threads all gate production '
    f'access behind human approval), and enterprise data platforms, where both fully <b>Blocked</b> apps '
    f'(iPayX, PitchBook) sit. <b>{ready_pct} of 100 apps are buildable as agent tools today</b> with no blocker at all.'
)

stat_tiles = [
    (f"{report['verdict_counts']['Ready']}/100", "apps Ready to build today, no blocker found"),
    (f"{oauth_apikey_pct}%", "authenticate via OAuth2 or a plain API key"),
    (f"{gating_unclear_pct}%", "have gating status undocumented, not just gated"),
    (f"{report['pass2_pct']}%", "of apps needed the grounding loop to reach a confident answer"),
]
stat_tiles_html = "\n".join(
    f'<div class="stat-tile"><div class="n">{n}</div><div class="l">{l}</div></div>' for n, l in stat_tiles
)

miss_boxes_html = "\n".join(
    f'''<div class="finding-box miss">
  <div class="fb-head"><span class="tag">Miss</span>{", ".join(m["apps"])} &mdash; {m["field"]}</div>
  <p>{m["issue"]}</p>
</div>''' for m in verification["confirmed_misses"]
)
mcp_note = verification["field_reliability_notes"][0]
miss_boxes_html += f'''
<div class="finding-box miss">
  <div class="fb-head"><span class="tag">Field flagged unreliable</span>has_mcp</div>
  <p>{mcp_note["issue"]}</p>
</div>'''

win_boxes_html = "\n".join(
    f'''<div class="finding-box win">
  <div class="fb-head"><span class="tag">Fixed by pass 2</span>{w["app"]}</div>
  <p>{w["note"]}</p>
</div>''' for w in verification["confirmed_wins"]
)

out = template
out = out.replace("__GEN_DATE__", datetime.date.today().isoformat())
out = out.replace("__HEADLINE_TEXT__", headline)
out = out.replace("__STAT_TILES__", stat_tiles_html)
out = out.replace("__MISS_BOXES__", miss_boxes_html)
out = out.replace("__WIN_BOXES__", win_boxes_html)
out = out.replace("__TABLE_ROWS_JSON__", json.dumps(table_rows, separators=(",", ":")))
out = out.replace("__REPORT_JSON__", json.dumps(report, separators=(",", ":")))
out = out.replace("__SAMPLE_JSON__", json.dumps(sample, separators=(",", ":")))

(ROOT / "index.html").write_text(out, encoding="utf-8")
print("wrote index.html:", len(out), "bytes")
