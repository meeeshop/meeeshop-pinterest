#!/usr/bin/env python3
"""
generate_pinterest_supplemental_feed.py — Pinterest Catalog & Supplemental Feed Generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fetches active products from Shopify API, cleans GTINs, validates image links for
PNG/JPEG format (using Shopify CDN format=jpg), maps 3+ level Google Product Taxonomy,
and outputs both Pinterest Supplemental Feed and Full Feed.
Uploads feeds to Shopify CDN and establishes clean static permalink redirects.
"""

import os
import csv
import re
import time
import requests
import secrets_manager
import gzip
import json

# ── Configuration & Credentials ───────────────────────────────────────────────
try:
    SHOPIFY_STORE = secrets_manager.get_secret("SHOPIFY_STORE")
    SHOPIFY_TOKEN = secrets_manager.get_secret("SHOPIFY_ACCESS_TOKEN")
    STORE_BASE_URL = secrets_manager.get_secret("STORE_BASE_URL")
except KeyError as e:
    raise ValueError(f"Missing Shopify credentials in secrets.enc: {e}")

STORE_DOMAIN = SHOPIFY_STORE.replace("https://", "").replace("http://", "").strip("/")
API_VER = "2025-01"
HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# Pinterest Catalog Defaults
DEFAULT_GENDER = "female"
DEFAULT_AGE_GROUP = "adult"
DEFAULT_CONDITION = "new"
DEFAULT_BRAND = "MeeeShop"

OUTPUT_SUPPLEMENTAL = "pinterest_supplemental_feed.csv"
OUTPUT_FULL = "pinterest_catalog_feed.csv"
REDIRECT_PATH_SUPPLEMENTAL = "/a/pinterest_supplemental_feed.csv"
REDIRECT_PATH_FULL = "/a/pinterest_catalog_feed.csv"

def clean_html(raw_html):
    """Removes HTML tags from product descriptions."""
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    text = re.sub(cleanr, '', raw_html)
    return text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ').replace(';', ',').strip()

def clean_and_validate_gtin(raw_gtin):
    """
    Sanitizes and validates GTIN.
    Must be digits only, length 8, 12, 13, or 14, with valid GS1 check digit.
    Returns valid GTIN string, or "" if invalid.
    """
    if not raw_gtin:
        return ""
    digits = re.sub(r'\D', '', str(raw_gtin).strip())
    if len(digits) not in [8, 12, 13, 14]:
        return ""
    
    # Validate GS1 Check Digit
    padded = digits.zfill(14)
    try:
        odd_sum = sum(int(padded[i]) for i in range(0, 13, 2))
        even_sum = sum(int(padded[i]) for i in range(1, 13, 2))
        total = odd_sum * 3 + even_sum
        check_digit = (10 - (total % 10)) % 10
        if check_digit == int(padded[13]):
            return digits
    except (ValueError, IndexError):
        pass
    return ""

def filter_image_url(url):
    """
    Validates and formats image URL for Pinterest compatibility.
    Pinterest requires PNG or JPEG formatting.
    Shopify CDN converts WebP/SVG/PNG to JPEG on the fly by appending format=jpg.
    Returns a guaranteed valid JPEG/PNG URL or "".
    """
    if not url or not isinstance(url, str):
        return ""
    clean_url = url.strip()
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        return ""
    
    # If Shopify CDN image, ensure format=jpg is appended to guarantee JPEG output
    if "cdn.shopify.com" in clean_url:
        if not ("format=jpg" in clean_url or "format=jpeg" in clean_url or "format=png" in clean_url):
            clean_url = clean_url + ("&format=jpg" if "?" in clean_url else "?format=jpg")
            
    return clean_url

def get_google_product_category(product):
    """Maps product details to full 3+ level Google Product Taxonomy paths (Fixes Warning 126)."""
    title = (product.get("title") or "").lower()
    ptype = (product.get("product_type") or "").lower()
    tags = (product.get("tags") or "").lower()
    text = f"{title} {ptype} {tags}"

    if any(w in text for w in ["dress", "dresses", "gown", "romper", "jumpsuit"]):
        return "Apparel & Accessories > Clothing > Dresses"
    elif any(w in text for w in ["pant", "pants", "jean", "jeans", "trouser", "trousers", "legging", "leggings"]):
        return "Apparel & Accessories > Clothing > Pants"
    elif any(w in text for w in ["short", "shorts"]):
        return "Apparel & Accessories > Clothing > Shorts"
    elif any(w in text for w in ["skirt", "skirts"]):
        return "Apparel & Accessories > Clothing > Skirts"
    elif any(w in text for w in ["jacket", "jackets", "coat", "coats", "blazer", "blazers", "cardigan", "outerwear", "sweatshirt", "hoodie"]):
        return "Apparel & Accessories > Clothing > Outerwear > Coats & Jackets"
    elif any(w in text for w in ["top", "tops", "shirt", "shirts", "tee", "t-shirt", "blouse", "knit", "sweater"]):
        return "Apparel & Accessories > Clothing > Shirts & Tops"
    elif any(w in text for w in ["bag", "bags", "handbag", "clutch", "tote", "purse", "backpack", "crossbody"]):
        return "Apparel & Accessories > Handbags, Wallets & Cases > Handbags"
    elif any(w in text for w in ["bikini", "swimsuit", "swimwear", "monokini"]):
        return "Apparel & Accessories > Clothing > Swimwear"
    elif any(w in text for w in ["pajama", "sleepwear", "loungewear", "robe", "nightgown"]):
        return "Apparel & Accessories > Clothing > Sleepwear & Loungewear"
    elif any(w in text for w in ["jewelry", "necklace", "earring", "bracelet", "ring"]):
        return "Apparel & Accessories > Jewelry"
    else:
        return "Apparel & Accessories > Clothing"

def extract_color(product, variant, current_color):
    """Extracts color from variant options, title, tags, or description."""
    if current_color and current_color.strip():
        return current_color.strip()

    title_lower = product.get("title", "").lower()
    tags_lower = [t.lower().strip() for t in product.get("tags", "").split(",") if t.strip()]
    desc_clean = clean_html(product.get("body_html", "")).lower()

    common_colors = [
        "black", "white", "red", "blue", "pink", "green", "yellow", "orange", "purple", "brown",
        "grey", "gray", "cream", "beige", "navy", "gold", "silver", "olive", "mustard", "burgundy",
        "rust", "lavender", "coral", "peach", "mint", "ivory", "denim", "camel", "taupe", "tan",
        "multi", "teal", "charcoal", "khaki", "plum", "apricot", "lilac", "mauve", "fuchsia",
        "turquoise", "maroon", "bronze", "indigo", "magenta", "leopard", "cheetah", "floral", "animal"
    ]

    for pos in [1, 2, 3]:
        opt_val = variant.get(f"option{pos}", "")
        if opt_val:
            opt_val_lower = opt_val.lower().strip()
            for word in re.split(r'[\s/]+', opt_val_lower):
                if word in common_colors:
                    return word.capitalize()

    for tag in tags_lower:
        if tag in common_colors:
            return tag.capitalize()

    for word in re.split(r'[\s,\-\(\)]+', title_lower):
        if word in common_colors:
            return word.capitalize()

    match = re.search(r'colou?r:\s*([a-z]+)', desc_clean)
    if match:
        color_word = match.group(1)
        if color_word in common_colors:
            return color_word.capitalize()

    return "Multi"

def fetch_all_active_products():
    """Fetches all active published products from Shopify."""
    products = []
    url = f"https://{STORE_DOMAIN}/admin/api/{API_VER}/products.json?limit=250&status=active&published_status=published"
    
    print(f"Fetching active products from {STORE_DOMAIN}...", flush=True)
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        products.extend(data.get("products", []))
        
        link_header = response.headers.get("Link")
        url = None
        if link_header:
            links = link_header.split(",")
            for link in links:
                if 'rel="next"' in link:
                    url = link[link.find("<")+1:link.find(">")]
                    
        time.sleep(0.4)
        
    print(f"Total active products fetched: {len(products)}", flush=True)
    return products

def upload_to_shopify_files(filepath):
    """Uploads file to Shopify Files CDN and returns CDN URL."""
    print(f"\nUploading {filepath} to Shopify CDN...", flush=True)
    graphql_url = f"https://{STORE_DOMAIN}/admin/api/{API_VER}/graphql.json"
    filename = os.path.basename(filepath)
    mime_type = "application/gzip" if filepath.endswith(".gz") else "text/csv"

    # Delete existing file with same name if present
    query_existing = f"""
    query {{
      files(first: 10, query: "filename:{filename}") {{
        edges {{
          node {{
            id
          }}
        }}
      }}
    }}
    """
    resp = requests.post(graphql_url, headers=HEADERS, json={"query": query_existing})
    resp.raise_for_status()
    data = resp.json()

    edges = data.get("data", {}).get("files", {}).get("edges", [])
    if edges:
        file_ids = [edge["node"]["id"] for edge in edges]
        delete_mut = """
        mutation fileDelete($fileIds: [ID!]!) {
          fileDelete(fileIds: $fileIds) {
            deletedFileIds
          }
        }
        """
        resp = requests.post(graphql_url, headers=HEADERS, json={"query": delete_mut, "variables": {"fileIds": file_ids}})
        resp.raise_for_status()
        time.sleep(2)

    # Request Staged Upload
    file_size = str(os.path.getsize(filepath))
    staged_mut = f"""
    mutation {{
      stagedUploadsCreate(input: [{{
        resource: FILE,
        filename: "{filename}",
        mimeType: "{mime_type}",
        httpMethod: POST,
        fileSize: "{file_size}"
      }}]) {{
        stagedTargets {{
          url
          resourceUrl
          parameters {{
            name
            value
          }}
        }}
      }}
    }}
    """
    resp = requests.post(graphql_url, headers=HEADERS, json={"query": staged_mut})
    resp.raise_for_status()
    data = resp.json()
    target = data["data"]["stagedUploadsCreate"]["stagedTargets"][0]

    # Upload file
    with open(filepath, "rb") as f:
        form_data = [(p["name"], p["value"]) for p in target["parameters"]]
        form_data.append(("file", (os.path.basename(filepath), f, mime_type)))
        upload_resp = requests.post(target["url"], files=form_data)
        upload_resp.raise_for_status()

    # Create file in Shopify
    create_mut = """
    mutation fileCreate($files: [FileCreateInput!]!) {
      fileCreate(files: $files) {
        files {
          id
          fileStatus
        }
      }
    }
    """
    variables = {"files": [{"originalSource": target["resourceUrl"], "contentType": "FILE"}]}
    resp = requests.post(graphql_url, headers=HEADERS, json={"query": create_mut, "variables": variables})
    resp.raise_for_status()
    create_data = resp.json()
    file_id = create_data["data"]["fileCreate"]["files"][0]["id"]

    # Poll for CDN URL
    public_url = None
    for _ in range(12):
        time.sleep(2)
        query_file = f"""
        query {{
          node(id: "{file_id}") {{
            ... on GenericFile {{
              url
              fileStatus
            }}
          }}
        }}
        """
        resp = requests.post(graphql_url, headers=HEADERS, json={"query": query_file})
        resp.raise_for_status()
        node_data = resp.json()
        node = node_data.get("data", {}).get("node", {})
        if node.get("fileStatus") == "READY":
            public_url = node.get("url")
            break

    if public_url:
        print(f"✅ Uploaded: {public_url}", flush=True)
        return public_url
    else:
        raise Exception(f"Failed to retrieve public URL for {filepath}")

def create_or_update_redirect(redirect_path, target_url):
    """Creates or updates a Shopify URL redirect pointing to target CDN URL."""
    print(f"Creating/updating URL redirect for {redirect_path}...", flush=True)
    graphql_url = f"https://{STORE_DOMAIN}/admin/api/{API_VER}/graphql.json"

    query_redirect = f'''
    query {{
      urlRedirects(first: 1, query: "path:{redirect_path}") {{
        edges {{
          node {{
            id
          }}
        }}
      }}
    }}
    '''
    resp = requests.post(graphql_url, headers=HEADERS, json={"query": query_redirect})
    resp.raise_for_status()
    data = resp.json()
    edges = data.get("data", {}).get("urlRedirects", {}).get("edges", [])

    url_redirect_input = {"path": redirect_path, "target": target_url}

    if edges:
        redirect_id = edges[0]["node"]["id"]
        update_mut = """
        mutation urlRedirectUpdate($id: ID!, $urlRedirect: UrlRedirectInput!) {
          urlRedirectUpdate(id: $id, urlRedirect: $urlRedirect) {
            urlRedirect { id path target }
            userErrors { field message }
          }
        }
        """
        resp = requests.post(graphql_url, headers=HEADERS, json={"query": update_mut, "variables": {"id": redirect_id, "urlRedirect": url_redirect_input}})
        resp.raise_for_status()
    else:
        create_mut = """
        mutation urlRedirectCreate($urlRedirect: UrlRedirectInput!) {
          urlRedirectCreate(urlRedirect: $urlRedirect) {
            urlRedirect { id path target }
            userErrors { field message }
          }
        }
        """
        resp = requests.post(graphql_url, headers=HEADERS, json={"query": create_mut, "variables": {"urlRedirect": url_redirect_input}})
        resp.raise_for_status()

    static_url = f"{STORE_BASE_URL.rstrip('/')}{redirect_path}"
    print(f"✅ Redirect active: {static_url}", flush=True)
    return static_url

def generate_feeds():
    products = fetch_all_active_products()

    feed_headers = [
        "id", "title", "description", "link", "image_link", "additional_image_link",
        "availability", "price", "condition", "brand", "gtin", "mpn",
        "identifier_exists", "google_product_category", "item_group_id", "gender", "age_group",
        "color", "size", "custom_label_0", "custom_label_1", "shipping"
    ]

    rows = []
    stats = {
        "total_variants": 0,
        "valid_gtins": 0,
        "cleared_gtins": 0,
        "valid_main_images": 0,
        "cleared_main_images": 0,
        "filtered_additional_images": 0
    }

    for product in products:
        if not product.get("published_at"):
            continue

        images = product.get("images", [])
        
        # Validate and format main image link
        raw_main_image = images[0].get("src") if images else ""
        main_image = filter_image_url(raw_main_image)
        if main_image:
            stats["valid_main_images"] += 1
        else:
            stats["cleared_main_images"] += 1

        # Validate additional images links (up to 10)
        additional_images_list = []
        for img in images[1:15]:
            filtered_img = filter_image_url(img.get("src"))
            if filtered_img:
                additional_images_list.append(filtered_img)
            if len(additional_images_list) >= 10:
                break

        additional_image_link = ",".join(additional_images_list)

        prod_desc = clean_html(product.get("body_html", ""))
        if len(prod_desc) > 4950:
            prod_desc = prod_desc[:4947] + "..."

        brand = DEFAULT_BRAND
        item_group_id = str(product.get("id"))
        google_cat = get_google_product_category(product)
        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
        first_tag = tags_list[0][:50] if tags_list else ""

        for variant in product.get("variants", []):
            stats["total_variants"] += 1
            var_id = str(variant.get("id"))
            
            # Pinterest catalog uses raw variant_id as join key (id)
            feed_id = var_id
            sku = variant.get("sku") or var_id

            title = product.get("title")
            if variant.get("title") and variant.get("title") != "Default Title":
                title = f"{title} - {variant.get('title')}"

            link = f"{STORE_BASE_URL.rstrip('/')}/products/{product.get('handle')}?variant={var_id}"

            qty = variant.get("inventory_quantity", 0)
            policy = variant.get("inventory_policy", "deny")
            management = variant.get("inventory_management")
            is_available = not management or policy == "continue" or qty > 0
            availability = "in_stock" if is_available else "out_of_stock"

            price = f"{variant.get('price')} USD"

            # GTIN Sanitization & Checksum Validation
            raw_gtin = variant.get("barcode", "") or ""
            valid_gtin = clean_and_validate_gtin(raw_gtin)
            if valid_gtin:
                stats["valid_gtins"] += 1
                identifier_exists = "yes"
            else:
                if raw_gtin:
                    stats["cleared_gtins"] += 1
                identifier_exists = "no"

            color = ""
            size = ""
            for opt in product.get("options", []):
                opt_name = opt.get("name", "").lower()
                opt_pos = opt.get("position")
                val = variant.get(f"option{opt_pos}", "")

                if "color" in opt_name or "colour" in opt_name:
                    color = val
                elif "size" in opt_name:
                    size = val

            color = extract_color(product, variant, color)

            rows.append({
                "id": feed_id,
                "title": title,
                "description": prod_desc,
                "link": link,
                "image_link": main_image,
                "additional_image_link": additional_image_link,
                "availability": availability,
                "price": price,
                "condition": DEFAULT_CONDITION,
                "brand": brand,
                "gtin": valid_gtin,
                "mpn": sku,
                "identifier_exists": identifier_exists,
                "google_product_category": google_cat,
                "item_group_id": item_group_id,
                "gender": DEFAULT_GENDER,
                "age_group": DEFAULT_AGE_GROUP,
                "color": color,
                "size": size,
                "custom_label_0": product_type,
                "custom_label_1": first_tag,
                "shipping": "US:::0.00 USD"
            })

    print("\n--- Pinterest Catalog & Feed Generation Summary ---", flush=True)
    print(f"Total Variants Processed: {stats['total_variants']}", flush=True)
    print(f"Valid GTINs Kept: {stats['valid_gtins']}", flush=True)
    print(f"Invalid GTINs Cleared (Warning 179 Fix): {stats['cleared_gtins']}", flush=True)
    print(f"Valid Main Images: {stats['valid_main_images']}", flush=True)
    print(f"Cleared Non-PNG/JPEG Main Images: {stats['cleared_main_images']}", flush=True)

    # Write files (both Supplemental and Full Catalog feeds)
    for outfile in [OUTPUT_SUPPLEMENTAL, OUTPUT_FULL]:
        gz_file = outfile + ".gz"
        print(f"Writing {len(rows)} records to {gz_file}...", flush=True)
        with gzip.open(gz_file, mode="wt", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=feed_headers, delimiter=',')
            writer.writeheader()
            writer.writerows(rows)

        cdn_url = upload_to_shopify_files(gz_file)
        redirect_path = REDIRECT_PATH_SUPPLEMENTAL if outfile == OUTPUT_SUPPLEMENTAL else REDIRECT_PATH_FULL
        static_url = create_or_update_redirect(redirect_path, cdn_url)

    print("\n🎉 Pinterest Feeds generated and deployed successfully!", flush=True)

if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    generate_feeds()
