"""
run_analysis.py
===============
Loads queries.sql, executes each named block, and writes:
  - results.json    — full results, one entry per @name block
  - dashboard.html  — populated standalone dashboard (Plotly via CDN)

Usage:
    python run_analysis.py
"""

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "tax_practice.db"
QUERIES_FILE = ROOT / "queries.sql"
RESULTS_JSON = ROOT / "results.json"
DASHBOARD_HTML = ROOT / "dashboard.html"
TEMPLATE_HTML = ROOT / "dashboard_template.html"


def parse_named_queries(sql_text: str) -> list[tuple[str, str]]:
    """Split queries.sql into [(name, sql), ...] using the -- @name header convention."""
    pattern = re.compile(r"--\s*@name\s+(\w+)\s*\n", re.MULTILINE)
    parts = pattern.split(sql_text)
    # parts == ['<preamble>', name1, body1, name2, body2, ...]
    pairs = []
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1].strip().rstrip(";").strip()
        pairs.append((name, body))
    return pairs


def run_query(conn: sqlite3.Connection, sql: str) -> dict:
    """Execute a SQL block and return {columns, rows}."""
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [list(r) for r in cur.fetchall()]
    return {"columns": cols, "rows": rows}


def main() -> None:
    sql_text = QUERIES_FILE.read_text()
    queries = parse_named_queries(sql_text)

    conn = sqlite3.connect(DB)
    results = {}
    for name, sql in queries:
        try:
            results[name] = run_query(conn, sql)
            print(f"  ✓ {name:35s} {len(results[name]['rows'])} rows")
        except Exception as exc:
            print(f"  ✗ {name:35s} FAILED — {exc}")
            results[name] = {"columns": [], "rows": [], "error": str(exc)}
    conn.close()

    RESULTS_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n✓ Wrote {RESULTS_JSON.name}  ({RESULTS_JSON.stat().st_size / 1024:.1f} KB)")

    # Bake into dashboard.html + index.html (the latter is what GH Pages serves)
    if TEMPLATE_HTML.exists():
        template = TEMPLATE_HTML.read_text()
        embedded = template.replace(
            "/* __DATA_PLACEHOLDER__ */",
            "window.__DATA__ = " + json.dumps(results, default=str) + ";"
        )
        DASHBOARD_HTML.write_text(embedded)
        (ROOT / "index.html").write_text(embedded)
        print(f"✓ Wrote {DASHBOARD_HTML.name}  ({DASHBOARD_HTML.stat().st_size / 1024:.1f} KB)")
        print(f"✓ Wrote index.html         (GitHub Pages entry point)")
    else:
        print("  (skipped dashboard.html — template not found)")


if __name__ == "__main__":
    main()
