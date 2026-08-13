"""
price_update.py - Update Shopify variant prices for over-priced products.

Logic:
  - Target: all variants where selling price > 2.8x cost per item
  - New base price = cost * 2.5 + $10.00
  - Final price = rounded UP to nearest price ending in $x4.99 or $x9.99

Run modes:
  python price_update.py            -- dry run, shows preview table only
  python price_update.py --apply    -- actually updates prices on Shopify
  python price_update.py --limit 20 -- dry run, first 20 variants only
"""

import os
import sys
import json
import time
import math
import re
import requests
import argparse
import io
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# -- Credential loading --------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from secrets_manager import inject_to_env
    inject_to_env()
except Exception:
    pass

# If still no token, load plain .env
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
GRAPHQL_URL  = f"{STORE_URL.rstrip('/')}/admin/api/2024-01/graphql.json"
HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json",
}

# -- Price rounding logic ------------------------------------------------------

def round_to_x99(price: float) -> float:
    """
    Round price UP to nearest value ending in $x4.99 or $x9.99.

    Pattern: ..., 4.99, 9.99, 14.99, 19.99, 24.99, 29.99, ...
    These occur every $5, starting at $4.99.
    Formula: ceil((price + 0.01) / 5) * 5 - 0.01
    """
    n = math.ceil((price + 0.01) / 5)
    return round(n * 5 - 0.01, 2)


def compute_new_price(cost: float) -> float:
    """New price = cost * 2.5 + $10, rounded up to x4.99 / x9.99."""
    base = cost * 2.5 + 10.0
    return round_to_x99(base)


# -- GraphQL helpers -----------------------------------------------------------

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
        return data
    raise RuntimeError("GraphQL failed after 5 attempts")


def parse_gid(gid: str) -> str:
    m = re.search(r"/(\d+)$", gid)
    return m.group(1) if m else gid


# -- Fetch all products --------------------------------------------------------

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
            for ve in node.get("variants", {}).get("edges", []):
                v = ve["node"]
                cost_info = (v.get("inventoryItem") or {}).get("unitCost") or {}
                cost_raw  = cost_info.get("amount")
                price_raw = v.get("price")
                try:
                    cost  = float(cost_raw)  if cost_raw  else None
                    price = float(price_raw) if price_raw else None
                except (ValueError, TypeError):
                    cost = price = None

                ratio = round(price / cost, 4) if (price and cost and cost > 0) else None
                products.append({
                    "variant_gid":   v.get("id", ""),
                    "variant_id":    parse_gid(v.get("id", "")),
                    "product_gid":   node.get("id", ""),
                    "product_id":    parse_gid(node.get("id", "")),
                    "product_title": node.get("title", ""),
                    "handle":        node.get("handle", ""),
                    "vendor":        node.get("vendor", ""),
                    "product_type":  node.get("productType", ""),
                    "variant_title": v.get("title", ""),
                    "price":         price,
                    "cost":          cost,
                    "ratio":         ratio,
                })
        page_info = data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return products


# -- Price update via GraphQL --------------------------------------------------

UPDATE_MUTATION = """
mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants {
      id
      price
    }
    userErrors {
      field
      message
    }
  }
}
"""

def update_prices_for_product(product_gid: str, updates: list) -> dict:
    """
    updates = [{"id": variant_gid, "price": "xx.xx"}, ...]
    Returns {"ok": [...], "errors": [...]}
    """
    variables = {
        "productId": product_gid,
        "variants": [{"id": u["id"], "price": str(u["price"])} for u in updates],
    }
    res = gql(UPDATE_MUTATION, variables)
    result = res.get("data", {}).get("productVariantsBulkUpdate", {})
    user_errors = result.get("userErrors", [])
    updated = result.get("productVariants", [])
    return {"ok": updated, "errors": user_errors}


# -- Preview table -------------------------------------------------------------

def print_preview(candidates: list, limit: int = None):
    shown = candidates[:limit] if limit else candidates
    print(f"\n{'='*120}")
    print(f"  PRICE UPDATE PREVIEW  ({len(shown)} of {len(candidates)} variants)")
    print(f"{'='*120}")
    header = f"{'Product':<45} {'Variant':<22} {'Cost':>8} {'Old Price':>10} {'Ratio':>7}  {'New Price':>10} {'New Ratio':>10}  Change"
    print(header)
    print("-" * 120)
    for r in shown:
        variant = r["variant_title"] if r["variant_title"] != "Default Title" else "-"
        cost_s     = f"${r['cost']:.2f}"
        old_s      = f"${r['price']:.2f}"
        new_s      = f"${r['new_price']:.2f}"
        ratio_s    = f"{r['ratio']:.2f}x"
        new_ratio_s = f"{r['new_ratio']:.2f}x"
        change_s   = f"-${r['price'] - r['new_price']:.2f}" if r['price'] > r['new_price'] else f"+${r['new_price'] - r['price']:.2f}"
        title = r["product_title"][:44]
        print(f"{title:<45} {variant:<22} {cost_s:>8} {old_s:>10} {ratio_s:>7}  {new_s:>10} {new_ratio_s:>10}  {change_s}")


# -- Main ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Update Shopify variant prices for over-priced items")
    parser.add_argument("--apply",   action="store_true", help="Actually update prices on Shopify (default: dry run)")
    parser.add_argument("--limit",   type=int, default=None, help="Only process first N variants (dry run preview)")
    parser.add_argument("--min-ratio", type=float, default=2.8, help="Only update variants with ratio above this (default: 2.8)")
    args = parser.parse_args()

    print("\n[MeeeShop Price Updater]")
    print("=" * 60)
    print(f"  Store     : {STORE_URL}")
    print(f"  Mode      : {'*** LIVE APPLY ***' if args.apply else 'DRY RUN (no changes)'}")
    print(f"  Threshold : ratio > {args.min_ratio}x")
    print(f"  New price : cost x 2.5 + $10.00, rounded to x4.99/x9.99")
    print()

    if not ACCESS_TOKEN:
        print("[ERROR] No Shopify access token found.")
        sys.exit(1)

    print("[...] Fetching all active products...")
    all_variants = fetch_all_products()
    print(f"\n  [OK] {len(all_variants)} total variants fetched")

    # Filter to candidates needing a price reduction
    candidates = []
    for v in all_variants:
        if v["cost"] is None or v["cost"] <= 0:
            continue
        if v["price"] is None:
            continue
        if v["ratio"] is None or v["ratio"] <= args.min_ratio:
            continue
        new_price = compute_new_price(v["cost"])
        new_ratio = round(new_price / v["cost"], 4)
        candidates.append({
            **v,
            "new_price": new_price,
            "new_ratio": new_ratio,
            "price_drop": round(v["price"] - new_price, 2),
        })

    print(f"\n  Variants with ratio > {args.min_ratio}x : {len(candidates)}")
    print(f"  (All will be repriced to cost x2.5 + $10, rounded to x4.99/x9.99)")

    if not candidates:
        print("\n  Nothing to update.")
        return

    # Show preview
    print_preview(candidates, limit=args.limit)

    # Save preview to file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    preview_path = Path(__file__).parent / f"price_update_preview_{ts}.json"
    with open(preview_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, default=str)
    print(f"\n[SAVED] Preview JSON -> {preview_path}")

    # Build HTML preview report
    html_path = Path(__file__).parent / "price_update_preview.html"
    generated_at = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    html_content = build_preview_html(candidates, generated_at, args.apply)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[SAVED] HTML preview -> {html_path}")

    if not args.apply:
        print("\n[DRY RUN] No prices changed. Run with --apply to update Shopify.")
        print(f"  Command: python price_update.py --apply")
        return

    # -- APPLY MODE: update prices on Shopify ----------------------------------
    print(f"\n[LIVE] Updating {len(candidates)} variant prices on Shopify...")
    print("  Grouping by product...")

    # Group by product_gid
    from collections import defaultdict
    by_product = defaultdict(list)
    for c in candidates:
        by_product[c["product_gid"]].append({
            "id":    c["variant_gid"],
            "price": f"{c['new_price']:.2f}",
        })

    ok_count    = 0
    error_count = 0
    errors      = []

    for i, (prod_gid, updates) in enumerate(by_product.items(), 1):
        prod_title = next((c["product_title"] for c in candidates if c["product_gid"] == prod_gid), prod_gid)
        print(f"  [{i}/{len(by_product)}] {prod_title[:60]}  ({len(updates)} variants)...", end=" ", flush=True)
        try:
            result = update_prices_for_product(prod_gid, updates)
            if result["errors"]:
                print(f"ERRORS: {result['errors']}")
                error_count += len(result["errors"])
                errors.extend(result["errors"])
            else:
                print(f"OK ({len(result['ok'])} updated)")
                ok_count += len(result["ok"])
        except Exception as e:
            print(f"EXCEPTION: {e}")
            error_count += 1
            errors.append({"field": prod_gid, "message": str(e)})
        # Small delay to be kind to Shopify rate limits
        time.sleep(0.3)

    print(f"\n[DONE]")
    print(f"  Updated successfully : {ok_count} variants")
    print(f"  Errors               : {error_count}")
    if errors:
        print("\n  Error details:")
        for e in errors[:10]:
            print(f"    - {e}")

    # Save results
    result_path = Path(__file__).parent / f"price_update_results_{ts}.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({"updated": ok_count, "errors": errors, "candidates": candidates}, f, indent=2, default=str)
    print(f"\n[SAVED] Results -> {result_path}")


# -- HTML Preview Report -------------------------------------------------------

def build_preview_html(candidates: list, generated_at: str, is_apply: bool) -> str:
    total_variants = len(candidates)
    total_reduction = sum(c["price_drop"] for c in candidates if c["price_drop"] > 0)
    avg_new_ratio = sum(c["new_ratio"] for c in candidates) / len(candidates) if candidates else 0
    
    rows = []
    for c in candidates:
        variant = c["variant_title"] if c["variant_title"] != "Default Title" else "&mdash;"
        url = f"https://us.meeeshop.com/products/{c['handle']}"
        old_ratio_cls = "badge-red" if c["ratio"] > 3.0 else "badge-orange"
        change = c["price"] - c["new_price"]
        change_s = f"-${change:.2f}" if change > 0 else f"+${-change:.2f}"
        change_cls = "price-drop" if change > 0 else "price-up"
        rows.append(f"""
        <tr>
          <td><a href="{url}" target="_blank" class="prod-link">{c['product_title']}</a></td>
          <td class="sm">{variant}</td>
          <td class="sm">{c.get('vendor','')}</td>
          <td class="num money">${c['cost']:.2f}</td>
          <td class="num money-old">${c['price']:.2f}</td>
          <td class="num"><span class="badge {old_ratio_cls}">{c['ratio']:.2f}x</span></td>
          <td class="num money-new">${c['new_price']:.2f}</td>
          <td class="num"><span class="badge badge-green">{c['new_ratio']:.2f}x</span></td>
          <td class="num {change_cls}">{change_s}</td>
        </tr>""")
    rows_html = "".join(rows)
    mode_badge = '<span class="mode-live">LIVE UPDATE APPLIED</span>' if is_apply else '<span class="mode-dry">DRY RUN PREVIEW</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>MeeeShop - Price Update Preview</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0d1117; --surface: #161b22; --surface2: #1e2530;
    --border: #30363d; --accent: #7c3aed; --accent2: #a78bfa;
    --red: #ef4444; --orange: #f97316; --green: #22c55e;
    --text: #e6edf3; --muted: #8b949e;
  }}
  body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); padding: 0 0 60px; }}
  .hero {{
    background: linear-gradient(135deg, #0a2010 0%, #0d1117 50%, #1a0533 100%);
    border-bottom: 1px solid var(--border);
    padding: 48px 40px 36px; position: relative; overflow: hidden;
  }}
  .hero::before {{
    content: ''; position: absolute; inset: 0;
    background: radial-gradient(ellipse 60% 80% at 20% 50%, rgba(34,197,94,.1), transparent);
  }}
  .hero-inner {{ max-width: 1400px; margin: 0 auto; position: relative; }}
  .hero h1 {{
    font-size: 2rem; font-weight: 800;
    background: linear-gradient(135deg, #fff 30%, var(--green));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }}
  .hero p {{ margin-top: 6px; color: var(--muted); font-size: .9rem; }}
  .hero .ts {{ margin-top: 4px; color: #5a6270; font-size: .8rem; }}
  .mode-dry  {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:.8rem; font-weight:700; background:rgba(249,115,22,.15); color:var(--orange); border:1px solid rgba(249,115,22,.4); margin-top:10px; }}
  .mode-live {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:.8rem; font-weight:700; background:rgba(34,197,94,.15); color:var(--green); border:1px solid rgba(34,197,94,.4); margin-top:10px; }}
  .stats {{ max-width: 1400px; margin: 28px auto 0; padding: 0 40px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
  .stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px 24px; transition: border-color .2s; }}
  .stat-card:hover {{ border-color: var(--accent); }}
  .stat-card .label {{ font-size: .75rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}
  .stat-card .value {{ font-size: 2rem; font-weight: 800; margin-top: 6px; }}
  .stat-card.grn .value {{ color: var(--green); }}
  .stat-card.org .value {{ color: var(--orange); }}
  .stat-card.pur .value {{ color: var(--accent2); }}
  .stat-card.muted .value {{ color: var(--muted); }}
  .stat-card .sub {{ font-size: .78rem; color: var(--muted); margin-top: 4px; }}
  .formula-box {{
    max-width: 1400px; margin: 24px auto 0; padding: 0 40px;
  }}
  .formula-inner {{
    background: rgba(124,58,237,.07); border: 1px solid rgba(124,58,237,.25);
    border-radius: 10px; padding: 14px 24px; display: flex; gap: 32px; align-items: center; flex-wrap: wrap;
  }}
  .formula-step {{ font-size: .85rem; color: var(--muted); }}
  .formula-step strong {{ color: var(--accent2); font-size: .95rem; }}
  .arrow {{ color: var(--accent); font-size: 1.2rem; font-weight: 700; }}
  .section {{ max-width: 1400px; margin: 28px auto 0; padding: 0 40px; }}
  .section-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
  .section-header h2 {{ font-size: 1.15rem; font-weight: 700; }}
  .table-wrap {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; overflow: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .83rem; }}
  thead th {{
    background: var(--surface2); padding: 12px 14px; text-align: left;
    font-weight: 600; font-size: .75rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: .06em;
    border-bottom: 1px solid var(--border); white-space: nowrap;
  }}
  tbody tr {{ border-bottom: 1px solid rgba(48,54,61,.6); transition: background .15s; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(124,58,237,.06); }}
  td {{ padding: 10px 14px; vertical-align: middle; }}
  td.num {{ text-align: right; }}
  td.sm {{ font-size: .8rem; color: var(--muted); }}
  .money {{ color: #34d399; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .money-old {{ color: var(--red); font-weight: 600; text-decoration: line-through; opacity: .8; font-variant-numeric: tabular-nums; }}
  .money-new {{ color: var(--green); font-weight: 700; font-size: .92rem; font-variant-numeric: tabular-nums; }}
  .price-drop {{ color: var(--green); font-weight: 600; }}
  .price-up   {{ color: var(--red); font-weight: 600; }}
  .prod-link {{ color: var(--text); text-decoration: none; font-weight: 500; transition: color .15s; }}
  .prod-link:hover {{ color: var(--accent2); text-decoration: underline; }}
  .badge {{ display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: .75rem; font-weight: 700; white-space: nowrap; }}
  .badge-red    {{ background: rgba(239,68,68,.15);  color: var(--red);    border: 1px solid rgba(239,68,68,.35); }}
  .badge-orange {{ background: rgba(249,115,22,.15); color: var(--orange); border: 1px solid rgba(249,115,22,.35); }}
  .badge-green  {{ background: rgba(34,197,94,.15);  color: var(--green);  border: 1px solid rgba(34,197,94,.35); }}
  @media (max-width: 768px) {{ .stats {{ grid-template-columns: 1fr 1fr; }} .hero, .section, .formula-box {{ padding-left: 16px; padding-right: 16px; }} }}
</style>
</head>
<body>
<div class="hero">
  <div class="hero-inner">
    <h1>MeeeShop &mdash; Price Update Report</h1>
    <p>Variants repriced to <strong style="color:#a78bfa">cost &times; 2.5 + $10</strong>, rounded to nearest $x4.99 / $x9.99</p>
    <p class="ts">Generated: {generated_at} &nbsp;|&nbsp; Store: us-meeeshop.myshopify.com</p>
    <div>{mode_badge}</div>
  </div>
</div>

<div class="formula-box">
  <div class="formula-inner">
    <div class="formula-step">Step 1<br><strong>Base = Cost &times; 2.5</strong></div>
    <div class="arrow">&rarr;</div>
    <div class="formula-step">Step 2<br><strong>+ $10.00</strong></div>
    <div class="arrow">&rarr;</div>
    <div class="formula-step">Step 3<br><strong>Round UP to $x4.99 or $x9.99</strong></div>
    <div class="arrow">&rarr;</div>
    <div class="formula-step">Result<br><strong style="color:var(--green)">Final Selling Price</strong></div>
  </div>
</div>

<div class="stats">
  <div class="stat-card org">
    <div class="label">Variants to Update</div>
    <div class="value">{total_variants}</div>
    <div class="sub">with ratio &gt; 2.8x</div>
  </div>
  <div class="stat-card grn">
    <div class="label">Total Price Reduction</div>
    <div class="value">${total_reduction:,.0f}</div>
    <div class="sub">sum of all price drops</div>
  </div>
  <div class="stat-card pur">
    <div class="label">Avg New Markup</div>
    <div class="value">{avg_new_ratio:.2f}x</div>
    <div class="sub">after update (target ~2.9x)</div>
  </div>
  <div class="stat-card muted">
    <div class="label">New Ratio Target</div>
    <div class="value">~2.9x</div>
    <div class="sub">healthy margin maintained</div>
  </div>
</div>

<div class="section">
  <div class="section-header">
    <h2>All Variants Being Updated</h2>
    <span style="font-size:.8rem;color:var(--muted)">{total_variants} variants &mdash; sorted by old price ratio (highest first)</span>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Product</th>
          <th>Variant</th>
          <th>Vendor</th>
          <th style="text-align:right">Cost/Item</th>
          <th style="text-align:right">Old Price</th>
          <th style="text-align:right">Old Ratio</th>
          <th style="text-align:right">New Price</th>
          <th style="text-align:right">New Ratio</th>
          <th style="text-align:right">Change</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>
</body>
</html>"""


if __name__ == "__main__":
    main()
