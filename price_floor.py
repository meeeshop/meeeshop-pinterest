"""
price_floor.py - Enforce minimum price floor of $44.99 on all active Shopify variants.

Rule: Any variant with a selling price below $44.99 -> set to $44.99

Run modes:
  python price_floor.py            -- dry run, preview only
  python price_floor.py --apply    -- live update on Shopify
"""

import os
import sys
import json
import time
import re
import math
import requests
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# -- Credential loading -------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from secrets_manager import inject_to_env
    inject_to_env()
except Exception:
    pass

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

FLOOR_PRICE = 44.99   # Minimum allowed price

# -- GraphQL helpers ----------------------------------------------------------

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
        return resp.json()
    raise RuntimeError("GraphQL failed after 5 attempts")


def parse_gid(gid: str) -> str:
    m = re.search(r"/(\d+)$", gid)
    return m.group(1) if m else gid


# -- Fetch all products -------------------------------------------------------

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


def fetch_all_variants():
    variants = []
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
                try:
                    price = float(v.get("price") or 0)
                    cost  = float(cost_info.get("amount") or 0)
                except (ValueError, TypeError):
                    price = 0.0
                    cost  = 0.0

                variants.append({
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
                })
        page_info = data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return variants


# -- Price update mutation ----------------------------------------------------

UPDATE_MUTATION = """
mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id price }
    userErrors { field message }
  }
}
"""


def update_variants_for_product(product_gid: str, updates: list) -> dict:
    variables = {
        "productId": product_gid,
        "variants":  [{"id": u["id"], "price": str(u["price"])} for u in updates],
    }
    res    = gql(UPDATE_MUTATION, variables)
    result = res.get("data", {}).get("productVariantsBulkUpdate", {})
    return {"ok": result.get("productVariants", []), "errors": result.get("userErrors", [])}


# -- Console preview ----------------------------------------------------------

def print_preview(candidates: list):
    print(f"\n{'='*115}")
    print(f"  PRICE FLOOR PREVIEW  ({len(candidates)} variants below ${FLOOR_PRICE:.2f})")
    print(f"{'='*115}")
    header = f"{'Product':<48} {'Variant':<22} {'Cost':>8} {'Old Price':>10} {'New Price':>10}  Vendor"
    print(header)
    print("-" * 115)
    for r in candidates:
        variant   = r["variant_title"] if r["variant_title"] != "Default Title" else "-"
        cost_s    = f"${r['cost']:.2f}" if r["cost"] > 0 else "N/A"
        old_s     = f"${r['price']:.2f}"
        new_s     = f"${FLOOR_PRICE:.2f}"
        title     = r["product_title"][:47]
        print(f"{title:<48} {variant:<22} {cost_s:>8} {old_s:>10} {new_s:>10}  {r['vendor']}")


# -- HTML Report --------------------------------------------------------------

def build_html(candidates: list, generated_at: str, is_apply: bool) -> str:
    rows = []
    for c in candidates:
        variant   = c["variant_title"] if c["variant_title"] != "Default Title" else "&mdash;"
        url       = f"https://us.meeeshop.com/products/{c['handle']}"
        cost_s    = f"${c['cost']:.2f}"  if c["cost"] > 0 else "N/A"
        diff      = FLOOR_PRICE - c["price"]
        diff_s    = f"+${diff:.2f}"
        rows.append(f"""
        <tr>
          <td><a href="{url}" target="_blank" class="prod-link">{c['product_title']}</a></td>
          <td class="sm">{variant}</td>
          <td class="sm">{c.get('vendor','')}</td>
          <td class="sm">{c.get('product_type','')}</td>
          <td class="num cost">{cost_s}</td>
          <td class="num money-old">${c['price']:.2f}</td>
          <td class="num money-new">${FLOOR_PRICE:.2f}</td>
          <td class="num price-up">{diff_s}</td>
        </tr>""")
    rows_html = "".join(rows)
    mode_badge = (
        '<span class="mode-live">LIVE UPDATE APPLIED</span>'
        if is_apply else
        '<span class="mode-dry">DRY RUN PREVIEW</span>'
    )
    cnt = len(candidates)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>MeeeShop - Price Floor Report</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg:#0d1117; --surface:#161b22; --surface2:#1e2530; --border:#30363d;
    --accent:#7c3aed; --accent2:#a78bfa; --red:#ef4444; --orange:#f97316;
    --green:#22c55e; --text:#e6edf3; --muted:#8b949e;
  }}
  body {{ font-family:'Inter',sans-serif; background:var(--bg); color:var(--text); padding:0 0 60px; }}
  .hero {{
    background: linear-gradient(135deg, #011520 0%, #0d1117 55%, #150a2a 100%);
    border-bottom:1px solid var(--border); padding:48px 40px 36px;
    position:relative; overflow:hidden;
  }}
  .hero::before {{
    content:''; position:absolute; inset:0;
    background:radial-gradient(ellipse 50% 70% at 10% 60%, rgba(34,197,94,.08), transparent);
  }}
  .hero-inner {{ max-width:1300px; margin:0 auto; position:relative; }}
  .hero h1 {{
    font-size:2rem; font-weight:800;
    background:linear-gradient(135deg,#fff 30%,var(--green));
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
  }}
  .hero p {{ margin-top:6px; color:var(--muted); font-size:.9rem; }}
  .hero .ts {{ margin-top:4px; color:#5a6270; font-size:.8rem; }}
  .mode-dry  {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:.8rem; font-weight:700; background:rgba(249,115,22,.15); color:var(--orange); border:1px solid rgba(249,115,22,.4); margin-top:10px; }}
  .mode-live {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:.8rem; font-weight:700; background:rgba(34,197,94,.15); color:var(--green); border:1px solid rgba(34,197,94,.4); margin-top:10px; }}

  .stats {{ max-width:1300px; margin:28px auto 0; padding:0 40px; display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
  .stat-card {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:20px 24px; transition:border-color .2s; }}
  .stat-card:hover {{ border-color:var(--accent); }}
  .stat-card .label {{ font-size:.75rem; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}
  .stat-card .value {{ font-size:2rem; font-weight:800; margin-top:6px; }}
  .stat-card.org .value {{ color:var(--orange); }}
  .stat-card.grn .value {{ color:var(--green); }}
  .stat-card.pur .value {{ color:var(--accent2); }}
  .stat-card .sub {{ font-size:.78rem; color:var(--muted); margin-top:4px; }}

  .rule-box {{ max-width:1300px; margin:22px auto 0; padding:0 40px; }}
  .rule-inner {{
    background:rgba(34,197,94,.06); border:1px solid rgba(34,197,94,.2);
    border-radius:10px; padding:16px 24px;
    font-size:.9rem; display:flex; align-items:center; gap:16px;
  }}
  .rule-icon {{ font-size:1.8rem; }}
  .rule-text {{ color:var(--muted); line-height:1.6; }}
  .rule-text strong {{ color:var(--green); font-size:1rem; }}

  .section {{ max-width:1300px; margin:28px auto 0; padding:0 40px; }}
  .section h2 {{ font-size:1.15rem; font-weight:700; margin-bottom:16px; }}
  .table-wrap {{ background:var(--surface); border:1px solid var(--border); border-radius:14px; overflow:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:.83rem; }}
  thead th {{
    background:var(--surface2); padding:12px 14px; text-align:left;
    font-weight:600; font-size:.75rem; color:var(--muted);
    text-transform:uppercase; letter-spacing:.06em;
    border-bottom:1px solid var(--border); white-space:nowrap;
  }}
  tbody tr {{ border-bottom:1px solid rgba(48,54,61,.6); transition:background .15s; }}
  tbody tr:last-child {{ border-bottom:none; }}
  tbody tr:hover {{ background:rgba(124,58,237,.06); }}
  td {{ padding:10px 14px; vertical-align:middle; }}
  td.num {{ text-align:right; }}
  td.sm {{ font-size:.8rem; color:var(--muted); }}
  .cost {{ color:#60a5fa; font-weight:600; font-variant-numeric:tabular-nums; }}
  .money-old {{ color:var(--red); font-weight:600; text-decoration:line-through; opacity:.8; font-variant-numeric:tabular-nums; }}
  .money-new {{ color:var(--green); font-weight:700; font-size:.9rem; font-variant-numeric:tabular-nums; }}
  .price-up  {{ color:var(--orange); font-weight:600; }}
  .prod-link {{ color:var(--text); text-decoration:none; font-weight:500; transition:color .15s; }}
  .prod-link:hover {{ color:var(--accent2); text-decoration:underline; }}
  @media (max-width:768px) {{ .stats {{ grid-template-columns:1fr 1fr; }} .hero, .section, .rule-box {{ padding-left:16px; padding-right:16px; }} }}
</style>
</head>
<body>
<div class="hero">
  <div class="hero-inner">
    <h1>MeeeShop &mdash; Price Floor Enforcement</h1>
    <p>All variants priced below <strong style="color:#34d399">$44.99</strong> are being raised to the store minimum</p>
    <p class="ts">Generated: {generated_at} &nbsp;|&nbsp; Store: us-meeeshop.myshopify.com</p>
    <div>{mode_badge}</div>
  </div>
</div>

<div class="rule-box">
  <div class="rule-inner">
    <div class="rule-icon">&#128274;</div>
    <div class="rule-text">
      <strong>Store Price Floor Rule: $44.99 minimum</strong><br>
      Any active variant selling below $44.99 is raised to $44.99 &mdash; regardless of cost.
      This protects against selling at a loss due to fees, shipping, and overhead.
    </div>
  </div>
</div>

<div class="stats">
  <div class="stat-card org">
    <div class="label">Variants Below Floor</div>
    <div class="value">{cnt}</div>
    <div class="sub">priced under $44.99</div>
  </div>
  <div class="stat-card grn">
    <div class="label">New Price</div>
    <div class="value">$44.99</div>
    <div class="sub">store minimum floor</div>
  </div>
  <div class="stat-card pur">
    <div class="label">Price Floor</div>
    <div class="value">$44.99</div>
    <div class="sub">enforced across all products</div>
  </div>
</div>

<div class="section">
  <h2>Variants Being Updated to $44.99</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Product</th>
          <th>Variant</th>
          <th>Vendor</th>
          <th>Type</th>
          <th style="text-align:right">Cost/Item</th>
          <th style="text-align:right">Old Price</th>
          <th style="text-align:right">New Price</th>
          <th style="text-align:right">Price Lift</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>
</body>
</html>"""


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Enforce $44.99 minimum price floor on all Shopify variants")
    parser.add_argument("--apply", action="store_true", help="Actually update prices (default: dry run)")
    args = parser.parse_args()

    print("\n[MeeeShop Price Floor Enforcer]")
    print("=" * 60)
    print(f"  Store       : {STORE_URL}")
    print(f"  Floor Price : ${FLOOR_PRICE:.2f}")
    print(f"  Mode        : {'*** LIVE APPLY ***' if args.apply else 'DRY RUN (no changes)'}")
    print()

    if not ACCESS_TOKEN:
        print("[ERROR] No Shopify access token found.")
        sys.exit(1)

    print("[...] Fetching all active published variants...")
    all_variants = fetch_all_variants()
    print(f"\n  [OK] {len(all_variants)} total variants fetched")

    # Filter: price strictly below floor
    candidates = [v for v in all_variants if v["price"] < FLOOR_PRICE]
    candidates.sort(key=lambda x: x["price"])  # lowest price first

    print(f"\n  Variants below ${FLOOR_PRICE:.2f} : {len(candidates)}")
    print(f"  All will be set to      : ${FLOOR_PRICE:.2f}")

    if not candidates:
        print("\n  [OK] No variants below the price floor. Nothing to update.")
        return

    # Console preview
    print_preview(candidates)

    # Save JSON
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = Path(__file__).parent / f"price_floor_preview_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, default=str)
    print(f"\n[SAVED] Preview JSON -> {json_path}")

    # Save HTML
    html_path = Path(__file__).parent / "price_floor_report.html"
    generated_at = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(candidates, generated_at, args.apply))
    print(f"[SAVED] HTML report  -> {html_path}")

    if not args.apply:
        print(f"\n[DRY RUN] No prices changed.")
        print(f"  Review the HTML report, then run:")
        print(f"  python price_floor.py --apply")
        return

    # -- LIVE UPDATE ----------------------------------------------------------
    print(f"\n[LIVE] Pushing ${FLOOR_PRICE:.2f} to {len(candidates)} variants on Shopify...")

    by_product = defaultdict(list)
    for c in candidates:
        by_product[c["product_gid"]].append({
            "id":    c["variant_gid"],
            "price": f"{FLOOR_PRICE:.2f}",
        })

    ok_count    = 0
    error_count = 0
    errors      = []

    for i, (prod_gid, updates) in enumerate(by_product.items(), 1):
        prod_title = next(
            (c["product_title"] for c in candidates if c["product_gid"] == prod_gid),
            prod_gid
        )
        print(f"  [{i}/{len(by_product)}] {prod_title[:55]}  ({len(updates)} variants)...", end=" ", flush=True)
        try:
            result = update_variants_for_product(prod_gid, updates)
            if result["errors"]:
                print(f"ERRORS: {result['errors']}")
                error_count += len(result["errors"])
                errors.extend(result["errors"])
            else:
                print(f"OK")
                ok_count += len(result["ok"])
        except Exception as e:
            print(f"EXCEPTION: {e}")
            error_count += 1
            errors.append({"product": prod_gid, "message": str(e)})
        time.sleep(0.25)

    print(f"\n[DONE]")
    print(f"  Updated successfully : {ok_count} variants -> ${FLOOR_PRICE:.2f}")
    print(f"  Errors               : {error_count}")
    if errors:
        for e in errors[:10]:
            print(f"    - {e}")

    # Save result HTML with applied state
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(candidates, datetime.now().strftime("%d %b %Y, %H:%M:%S"), True))
    print(f"[SAVED] Final report -> {html_path}")


if __name__ == "__main__":
    main()
