"""
price_analysis.py - Fetch all Shopify products with Cost Per Item and flag high markup ratios.

Flags products where:
  - Selling price > 2.8x cost  (>2.8x bucket)
  - Selling price > 3.0x cost  (>3.0x bucket)

Outputs:
  1. Console table summary
  2. price_analysis_report.html — rich HTML report saved next to this script
"""

import os
import sys
import json
import time
import re
import requests
import io
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ── credential loading ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Step 1: try to inject from encrypted secrets.enc
try:
    from secrets_manager import inject_to_env
    inject_to_env()
except Exception as _e:
    pass  # fall back to plain .env / os.environ

# Step 2: if still no token, load plain .env file directly
if not os.getenv("SHOPIFY_ACCESS_TOKEN"):
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        for _line in open(env_file, encoding="utf-8"):
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

STORE_URL    = os.getenv("SHOPIFY_STORE_URL",    "https://us-meeeshop.myshopify.com")
ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

GRAPHQL_URL = f"{STORE_URL.rstrip('/')}/admin/api/2024-01/graphql.json"
HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json",
}

# ── GraphQL helpers ─────────────────────────────────────────────────────────

def gql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    for attempt in range(5):
        resp = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30)
        if resp.status_code == 429:
            time.sleep(float(resp.headers.get("Retry-After", 2)))
            continue
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            print(f"  [GraphQL errors] {data['errors']}")
        return data
    raise RuntimeError("GraphQL failed after 5 attempts")


def parse_gid(gid: str) -> str:
    if not gid:
        return ""
    m = re.search(r"/(\d+)$", gid)
    return m.group(1) if m else gid


# ── Fetch all products with variant cost ────────────────────────────────────

PRODUCT_QUERY = """
query ($first: Int!, $after: String) {
  products(first: $first, after: $after, query: "status:active published_status:published") {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        title
        handle
        vendor
        productType
        variants(first: 100) {
          edges {
            node {
              id
              title
              price
              inventoryItem {
                unitCost { amount currencyCode }
              }
            }
          }
        }
      }
    }
  }
}
"""


def fetch_all_products():
    products = []
    cursor = None
    page = 0
    while True:
        page += 1
        print(f"  Fetching page {page}...", end=" ", flush=True)
        res = gql(PRODUCT_QUERY, {"first": 250, "after": cursor})
        data = res.get("data", {}).get("products", {})
        edges = data.get("edges", [])
        print(f"{len(edges)} products")
        for edge in edges:
            node = edge["node"]
            pid  = parse_gid(node["id"])
            for ve in node.get("variants", {}).get("edges", []):
                v = ve["node"]
                cost_info = (v.get("inventoryItem") or {}).get("unitCost") or {}
                cost_raw  = cost_info.get("amount")
                price_raw = v.get("price")

                try:
                    cost  = float(cost_raw)  if cost_raw  else None
                    price = float(price_raw) if price_raw else None
                except (ValueError, TypeError):
                    cost  = None
                    price = None

                products.append({
                    "product_id":    pid,
                    "product_title": node.get("title", ""),
                    "handle":        node.get("handle", ""),
                    "vendor":        node.get("vendor", ""),
                    "product_type":  node.get("productType", ""),
                    "variant_id":    parse_gid(v.get("id", "")),
                    "variant_title": v.get("title", ""),
                    "price":         price,
                    "cost":          cost,
                    "ratio":         round(price / cost, 4) if (price and cost and cost > 0) else None,
                })

        page_info = data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return products


# ── Analysis ────────────────────────────────────────────────────────────────

def analyse(products: list) -> dict:
    above_2_8 = []
    above_3_0 = []
    no_cost   = []

    for p in products:
        if p["cost"] is None or p["cost"] == 0:
            no_cost.append(p)
            continue
        if p["price"] is None:
            continue
        if p["ratio"] > 3.0:
            above_3_0.append(p)
        elif p["ratio"] > 2.8:
            above_2_8.append(p)

    # sort by ratio desc
    above_3_0.sort(key=lambda x: x["ratio"], reverse=True)
    above_2_8.sort(key=lambda x: x["ratio"], reverse=True)

    return {"above_3_0": above_3_0, "above_2_8": above_2_8, "no_cost": no_cost, "all": products}


# ── Console output ──────────────────────────────────────────────────────────

def print_table(rows: list, label: str):
    print(f"\n{'='*100}")
    print(f"  {label}  ({len(rows)} variants)")
    print(f"{'='*100}")
    if not rows:
        print("  (none)")
        return
    header = f"{'Product Title':<45} {'Variant':<20} {'Cost':>8} {'Price':>8} {'Ratio':>7}  Vendor"
    print(header)
    print("-" * 100)
    for r in rows:
        variant = r["variant_title"] if r["variant_title"] != "Default Title" else "-"
        cost_s  = f"${r['cost']:.2f}"  if r["cost"]  is not None else "N/A"
        price_s = f"${r['price']:.2f}" if r["price"] is not None else "N/A"
        ratio_s = f"{r['ratio']:.2f}x"  if r["ratio"] is not None else "N/A"
        title   = r["product_title"][:44]
        print(f"{title:<45} {variant:<20} {cost_s:>8} {price_s:>8} {ratio_s:>7}  {r['vendor']}")


# ── HTML Report ─────────────────────────────────────────────────────────────

def build_html(result: dict, generated_at: str) -> str:
    def rows_html(rows, badge_class):
        if not rows:
            return "<tr><td colspan='7' style='text-align:center;color:#aaa;padding:24px'>No products in this category</td></tr>"
        out = []
        for r in rows:
            variant = r["variant_title"] if r["variant_title"] != "Default Title" else "—"
            cost_s  = f"${r['cost']:.2f}"  if r["cost"]  is not None else "N/A"
            price_s = f"${r['price']:.2f}" if r["price"] is not None else "N/A"
            ratio_s = f"{r['ratio']:.2f}×"  if r["ratio"] is not None else "N/A"
            handle  = r["handle"]
            store   = STORE_URL.replace("us-meeeshop.myshopify.com", "us.meeeshop.com").replace("myshopify.com", "meeeshop.com")
            url     = f"https://us.meeeshop.com/products/{handle}"
            title   = r["product_title"]
            out.append(f"""
            <tr>
              <td><a href="{url}" target="_blank" class="prod-link">{title}</a></td>
              <td>{variant}</td>
              <td class="num">{r.get('vendor','')}</td>
              <td class="num">{r.get('product_type','')}</td>
              <td class="num money">{cost_s}</td>
              <td class="num money">{price_s}</td>
              <td class="num"><span class="badge {badge_class}">{ratio_s}</span></td>
            </tr>""")
        return "".join(out)

    a3_html  = rows_html(result["above_3_0"], "badge-red")
    a28_html = rows_html(result["above_2_8"], "badge-orange")

    total    = len(result["all"])
    cnt_3    = len(result["above_3_0"])
    cnt_28   = len(result["above_2_8"])
    cnt_nc   = len(result["no_cost"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>MeeeShop — Price Markup Analysis</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:       #0d1117;
    --surface:  #161b22;
    --surface2: #1e2530;
    --border:   #30363d;
    --accent:   #7c3aed;
    --accent2:  #a78bfa;
    --red:      #ef4444;
    --orange:   #f97316;
    --green:    #22c55e;
    --text:     #e6edf3;
    --muted:    #8b949e;
    --money:    #34d399;
  }}

  body {{
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 0 0 60px;
  }}

  /* ── Header ── */
  .hero {{
    background: linear-gradient(135deg, #1a0533 0%, #0d1117 50%, #0a1628 100%);
    border-bottom: 1px solid var(--border);
    padding: 48px 40px 36px;
    position: relative;
    overflow: hidden;
  }}
  .hero::before {{
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(ellipse 60% 80% at 80% 50%, rgba(124,58,237,.15), transparent);
    pointer-events: none;
  }}
  .hero-inner {{ max-width: 1200px; margin: 0 auto; position: relative; }}
  .hero h1 {{
    font-size: 2rem; font-weight: 800;
    background: linear-gradient(135deg, #fff 30%, var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
  }}
  .hero p {{ margin-top: 6px; color: var(--muted); font-size: .9rem; }}
  .hero .ts {{ margin-top: 4px; color: #5a6270; font-size: .8rem; }}

  /* ── Stats strip ── */
  .stats {{
    max-width: 1200px; margin: 28px auto 0; padding: 0 40px;
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    position: relative; overflow: hidden;
    transition: border-color .2s;
  }}
  .stat-card:hover {{ border-color: var(--accent); }}
  .stat-card .label {{ font-size: .75rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}
  .stat-card .value {{ font-size: 2rem; font-weight: 800; margin-top: 6px; }}
  .stat-card.red  .value {{ color: var(--red);    }}
  .stat-card.org  .value {{ color: var(--orange);  }}
  .stat-card.grn  .value {{ color: var(--green);   }}
  .stat-card.muted .value{{ color: var(--muted);   }}
  .stat-card .sub {{ font-size: .78rem; color: var(--muted); margin-top: 4px; }}

  /* ── Section ── */
  .section {{
    max-width: 1200px; margin: 36px auto 0; padding: 0 40px;
  }}
  .section-header {{
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 16px;
  }}
  .section-header h2 {{ font-size: 1.15rem; font-weight: 700; }}
  .pill {{
    display: inline-block; padding: 3px 10px;
    border-radius: 999px; font-size: .75rem; font-weight: 700;
  }}
  .pill-red    {{ background: rgba(239,68,68,.15);  color: var(--red);    border: 1px solid rgba(239,68,68,.3);   }}
  .pill-orange {{ background: rgba(249,115,22,.15); color: var(--orange); border: 1px solid rgba(249,115,22,.3); }}

  /* ── Table ── */
  .table-wrap {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: auto;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: .86rem; }}
  thead th {{
    background: var(--surface2);
    padding: 12px 16px;
    text-align: left;
    font-weight: 600;
    font-size: .78rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .06em;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }}
  tbody tr {{
    border-bottom: 1px solid rgba(48,54,61,.6);
    transition: background .15s;
  }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(124,58,237,.06); }}
  td {{ padding: 11px 16px; vertical-align: middle; }}
  td.num {{ text-align: right; }}
  td.money {{ color: var(--money); font-weight: 600; font-variant-numeric: tabular-nums; }}
  .prod-link {{
    color: var(--text); text-decoration: none; font-weight: 500;
    transition: color .15s;
  }}
  .prod-link:hover {{ color: var(--accent2); text-decoration: underline; }}

  /* ── Badges ── */
  .badge {{
    display: inline-block; padding: 3px 10px;
    border-radius: 999px; font-size: .78rem; font-weight: 700;
    letter-spacing: .02em; white-space: nowrap;
  }}
  .badge-red    {{ background: rgba(239,68,68,.15);  color: var(--red);    border: 1px solid rgba(239,68,68,.35);   }}
  .badge-orange {{ background: rgba(249,115,22,.15); color: var(--orange); border: 1px solid rgba(249,115,22,.35); }}

  /* ── Note ── */
  .note {{
    max-width: 1200px; margin: 20px auto 0; padding: 0 40px;
  }}
  .note-box {{
    background: rgba(124,58,237,.07);
    border: 1px solid rgba(124,58,237,.25);
    border-radius: 10px;
    padding: 14px 20px;
    font-size: .85rem; color: var(--muted); line-height: 1.6;
  }}
  .note-box strong {{ color: var(--accent2); }}

  @media (max-width: 768px) {{
    .stats {{ grid-template-columns: 1fr 1fr; }}
    .hero, .section, .note {{ padding-left: 16px; padding-right: 16px; }}
  }}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-inner">
    <h1>🛍️ MeeeShop — Price Markup Analysis</h1>
    <p>Active products where selling price significantly exceeds cost per item</p>
    <p class="ts">Generated: {generated_at} &nbsp;|&nbsp; Store: us-meeeshop.myshopify.com</p>
  </div>
</div>

<div class="stats">
  <div class="stat-card red">
    <div class="label">Above 3× Markup</div>
    <div class="value">{cnt_3}</div>
    <div class="sub">variants · price &gt; 3× cost</div>
  </div>
  <div class="stat-card org">
    <div class="label">2.8× – 3× Markup</div>
    <div class="value">{cnt_28}</div>
    <div class="sub">variants · price between 2.8× and 3×</div>
  </div>
  <div class="stat-card muted">
    <div class="label">No Cost Data</div>
    <div class="value">{cnt_nc}</div>
    <div class="sub">variants missing cost per item</div>
  </div>
  <div class="stat-card grn">
    <div class="label">Total Variants</div>
    <div class="value">{total}</div>
    <div class="sub">active &amp; published</div>
  </div>
</div>

<!-- >3x section -->
<div class="section">
  <div class="section-header">
    <h2>Variants with &gt; 3× Markup</h2>
    <span class="pill pill-red">{cnt_3} items</span>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Product</th>
          <th>Variant</th>
          <th>Vendor</th>
          <th>Type</th>
          <th style="text-align:right">Cost / Item</th>
          <th style="text-align:right">Selling Price</th>
          <th style="text-align:right">Markup Ratio</th>
        </tr>
      </thead>
      <tbody>{a3_html}</tbody>
    </table>
  </div>
</div>

<!-- 2.8x–3x section -->
<div class="section">
  <div class="section-header">
    <h2>Variants with 2.8× – 3× Markup</h2>
    <span class="pill pill-orange">{cnt_28} items</span>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Product</th>
          <th>Variant</th>
          <th>Vendor</th>
          <th>Type</th>
          <th style="text-align:right">Cost / Item</th>
          <th style="text-align:right">Selling Price</th>
          <th style="text-align:right">Markup Ratio</th>
        </tr>
      </thead>
      <tbody>{a28_html}</tbody>
    </table>
  </div>
</div>

<div class="note">
  <div class="note-box">
    <strong>How to read this report:</strong>
    "Cost / Item" is the <em>inventory unit cost</em> entered in Shopify (Admin → Products → Inventory → Cost per item).
    "Markup Ratio" = Selling Price ÷ Cost per Item.
    <strong>Red rows (&gt;3x)</strong> may warrant a price review — check competitor pricing before reducing.
    <strong>Orange rows (2.8x–3x)</strong> are borderline — healthy margin but worth monitoring.
    Products with no cost data are excluded from the markup calculation.
  </div>
</div>

</body>
</html>"""



def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print("\n[MeeeShop Price Markup Analyser]")
    print("=" * 50)
    print(f"  Store   : {STORE_URL}")
    print(f"  API URL : {GRAPHQL_URL}")
    print()

    if not ACCESS_TOKEN:
        print("[ERROR] No Shopify access token found. Check .env or secrets.enc")
        sys.exit(1)

    print("[...] Fetching all active products with cost data...")
    products = fetch_all_products()
    print(f"\n  [OK] {len(products)} total product variants fetched")

    result = analyse(products)

    # Console output
    print_table(result["above_3_0"], "ABOVE 3.0x MARKUP  [HIGH]")
    print_table(result["above_2_8"], "ABOVE 2.8x (up to 3x) MARKUP  [WATCH]")

    print(f"\n\n[SUMMARY]")
    print(f"  Variants > 3.0x markup  : {len(result['above_3_0'])}")
    print(f"  Variants 2.8-3.0x markup: {len(result['above_2_8'])}")
    print(f"  Variants missing cost   : {len(result['no_cost'])}")
    print(f"  Total variants checked  : {len(result['all'])}")

    # Save JSON
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = Path(__file__).parent / f"price_analysis_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[SAVED] JSON -> {json_path}")

    # Save HTML report
    html_path = Path(__file__).parent / "price_analysis_report.html"
    generated_at = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    html_content = build_html(result, generated_at)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[SAVED] HTML report -> {html_path}")
    print("\n[DONE] Open price_analysis_report.html in your browser for the full report.\n")


if __name__ == "__main__":
    main()
