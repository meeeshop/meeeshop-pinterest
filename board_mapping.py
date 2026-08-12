from typing import List, Dict, Optional, Any

# Complete list of 1-year-old Pinterest boards from MeeeShop account screenshots
OLD_BOARDS_1Y = [
    "Must-Have Fashion...",
    "Feminine & Flowy Fits",
    "Confident Looks",
    "Trendy & Timeless...",
    "Farm clothes",
    "Bow heels",
    "My Shop #1737732113",
    "Emory Park Clothing",
    "Davi & Dani Womens...",
    "Beauty",
    "BFCM Deals",
    "Umgee USA",
    "Short fall dresses",
    "Shop For Holidays",
    "Thanks giving Outfits",
    "Winter Outfits",
    "comfy fall outfits",
    "LE LIS Womens Clothi...",
    "MeeeShop's Luxe Styles",
    "Mustard Seed Clothing",
    "American Bazi",
    "Our Recommended...",
    "\"Music Clothes\"",
    "Rompers, Jumpsuits &...",
    "Blogs",
    "Outerwear",
    "Women's Cardigans",
    "Footwear",
    "Zenana Women's...",
    "Fall outfits",
    "Relaxed Yet Trendy...",
    "Wardrobe Goals",
    "Weekend to Workwear",
    "Wardrobe Must-Hav...",
]

# Complete list of MeeeShop Pinterest boards
MEEESHOP_BOARDS = [
    "All Pins",
    "Fashion Models",
    "Fresh Finds New...",
    "\"Fresh Finds: New...",
    "Music Clothes",
    "\"Music Clothes\"",
    "American Ball",
    "American Bazi",
    "Ankle Strap Flats",
    "Bags",
    "Beauty",
    "Best selling products",
    "BFCM Deals",
    "Blouse",
    "Blouses",
    "Boat Shoes",
    "Bow heels",
    "Blogs",
    "Camis & Tanks",
    "Casual",
    "Chic & Cozy Anim...",
    "Chic & Cozy: Annie...",
    "Chic & Effortless Styles",
    "Chic Looks",
    "Chic & Cozy: Annie...",
    "Coats & Jackets",
    "Cocktail Dresses",
    "comfy fall outfits",
    "Confident Looks",
    "Confidence Ladies",
    "Cool & Casual Styles",
    "Davi & Dani Womens...",
    "Daris & Desi Womens...",
    "Dress",
    "Dresses",
    "Dressy Outfits",
    "Edgy Fashion",
    "Effortless Looks",
    "Emory Park Clothing",
    "Every Peak Clothing",
    "Everyday Style",
    "Fall outfits",
    "Fall looks",
    "Fall Outfits 2026",
    "Farm clothes",
    "Fern Clothes",
    "Festival",
    "Festive & Flora Fits",
    "Festive Styles",
    "Feminine & Flowy Fits",
    "Fitted Jeans",
    "Flares Jeans",
    "Footwear",
    "Handbag #handsips",
    "Jeans",
    "Kancan USA Jeans",
    "Kimchi USA Jeans",
    "LE LIS Womens Clothi...",
    "LE US Womens Cloth...",
    "Look casual...",
    "Loungewear",
    "Luxe Clothing",
    "MeeeShop's Luxe Styles",
    "Meshohn Luxe Styles",
    "Must-Have Fashion...",
    "Mist More Fashion...",
    "Mustard Seed Clothing",
    "My Shop #1737732113",
    "My Shop 8727/2019",
    "New",
    "new products",
    "New Trendy Woman...",
    "New Trendy Women...",
    "Nylon backpack",
    "Ootd #ootd",
    "Our Recommended...",
    "Outerwear",
    "Outer wear",
    "Outfit Ideas",
    "Pants & Leggings",
    "Plus Size",
    "Puff Sleeves Tops",
    "Relaxed Yet Trendy...",
    "Rompers, Jumpsuits &...",
    "Rompers_Jumpsuits &...",
    "Shirts & Tops",
    "Shop For Holidays",
    "Shop For Hotties",
    "Shop Responsibly",
    "Short fall dresses",
    "Short Tall dresses",
    "Simple Outfits",
    "Skirts",
    "Social",
    "Spicing Outfits",
    "Straight Leg Jeans",
    "Style Ideas",
    "Stylish Finds",
    "Sweaters",
    "Sweaters #Sweaters...",
    "Sweaters & Sweater...",
    "Sweaters for women",
    "Thanks giving Outfits",
    "Trends",
    "Trendy & Timeless...",
    "Trendy & Trendes...",
    "Trendy Backpacks",
    "Umgee USA",
    "Unique USA",
    "Wardrobe Goals",
    "Wardrobe Oozes",
    "Wardrobe Must-Hav...",
    "Wardrobe Must Haves",
    "Weekend to Workwear",
    "Weekend to Workout",
    "Winter Outfits",
    "Woman Fashion!",
    "Women's Cardigans",
    "Womens Cardigans",
    "Women's shacket",
    "Womens shacket",
    "Zenana Women's...",
    "Zenana Womens...",
    "Poetcore Aesthetics",
    "Vamp Romantic Styles",
    "Off-Duty Athlete Looks",
    "Gimme Gummy Playful Nostalgia",
    "Moody Blues & Vintage Pinks",
    "Affordable Women's Fashion USA",
    "Casual Chic Style",
]

# High-traffic and priority boards for rotation pools
HIGH_TRAFFIC_BOARDS = [
    "Trends",
    "New",
    "Best selling products",
    "New Trendy Woman...",
    "Poetcore Aesthetics",
    "Vamp Romantic Styles",
    "Off-Duty Athlete Looks",
    "Must-Have Fashion...",
    "Trendy & Timeless...",
]

PRIORITY_BOARDS = [
    "Trends",
    "New",
    "Best selling products",
    "Outfit Ideas",
    "Ootd #ootd",
    "Style Ideas",
    "Everyday Style",
    "Wardrobe Must-Hav...",
    "Wardrobe Must Haves",
    "Woman Fashion!",
    "Chic & Effortless Styles",
    "Stylish Finds",
    "Confidence Ladies",
    "Feminine & Flowy Fits",
    "Confident Looks",
    "Must-Have Fashion...",
    "Trendy & Timeless...",
    "Poetcore Aesthetics",
    "Vamp Romantic Styles",
    "Off-Duty Athlete Looks",
]

# Dedicated Blog & Editorial Boards
BLOG_BOARDS = [
    "Our Recommended...",
    "My Shop #1737732113",
    "My Shop 8727/2019",
    "Social",
    "Blogs",
    "Fashion Models",
    "Style Ideas",
    "Outfit Ideas",
    "Trends",
    "Everyday Style",
    "Casual Chic Style",
    "Affordable Women's Fashion USA",
]


# Comprehensive category to board mapping covering ALL active & 1-year-old boards
CATEGORY_TO_BOARDS = {
    "dress": [
        "Dresses",
        "Dress",
        "Short fall dresses",
        "Short Tall dresses",
        "Feminine & Flowy Fits",
        "Cocktail Dresses",
        "Dressy Outfits",
        "Rompers, Jumpsuits &...",
        "Rompers_Jumpsuits &...",
        "Festive Styles",
        "Thanks giving Outfits",
        "Confident Looks",
        "Emory Park Clothing",
        "Davi & Dani Womens...",
        "LE LIS Womens Clothi...",
        "Mustard Seed Clothing",
        "Poetcore Aesthetics",
        "Vamp Romantic Styles",
        "Festive & Flora Fits",
        "Trends",
        "New",
        "Best selling products",
    ],
    "top": [
        "Shirts & Tops",
        "Blouses",
        "Blouse",
        "Camis & Tanks",
        "Puff Sleeves Tops",
        "Confident Looks",
        "Must-Have Fashion...",
        "Trendy & Timeless...",
        "Farm clothes",
        "American Bazi",
        "MeeeShop's Luxe Styles",
        "Zenana Women's...",
        "Chic & Effortless Styles",
        "Effortless Looks",
        "Trends",
        "New",
        "Best selling products",
    ],
    "jeans": [
        "Jeans",
        "Flares Jeans",
        "Kancan USA Jeans",
        "Fitted Jeans",
        "Straight Leg Jeans",
        "Kimchi USA Jeans",
        "Pants & Leggings",
        "Farm clothes",
        "Casual Chic Style",
        "Everyday Style",
        "Trends",
        "New",
    ],
    "jacket": [
        "Outerwear",
        "Outer wear",
        "Coats & Jackets",
        "Women's shacket",
        "Womens shacket",
        "Winter Outfits",
        "Fall outfits",
        "comfy fall outfits",
        "Women's Cardigans",
        "Womens Cardigans",
        "Sweaters",
        "Fall Outfits 2026",
        "Trends",
        "New",
    ],
    "pants": [
        "Pants & Leggings",
        "Jeans",
        "Flares Jeans",
        "Casual",
        "Cool & Casual Styles",
        "Weekend to Workwear",
        "Weekend to Workout",
        "Off-Duty Athlete Looks",
        "Trends",
        "New",
    ],
    "skirt": [
        "Skirts",
        "Dressy Outfits",
        "Chic Looks",
        "Fashion Models",
        "Feminine & Flowy Fits",
        "Poetcore Aesthetics",
        "Trends",
        "New",
    ],
    "sweater": [
        "Sweaters",
        "Sweaters #Sweaters...",
        "Sweaters & Sweater...",
        "Sweaters for women",
        "Women's Cardigans",
        "Womens Cardigans",
        "comfy fall outfits",
        "Fall outfits",
        "Winter Outfits",
        "Chic & Cozy: Annie...",
        "Chic & Cozy Anim...",
        "Fall Outfits 2026",
        "Trends",
        "New",
    ],
    "cardigan": [
        "Women's Cardigans",
        "Womens Cardigans",
        "Sweaters",
        "Sweaters #Sweaters...",
        "Sweaters & Sweater...",
        "Chic & Cozy: Annie...",
        "Chic & Cozy Anim...",
        "comfy fall outfits",
        "Fall outfits",
        "Trends",
        "New",
    ],
    "bag": [
        "Bags",
        "Handbag #handsips",
        "Trendy Backpacks",
        "Nylon backpack",
        "Gimme Gummy Playful Nostalgia",
        "Trends",
        "New",
    ],
    "shoe": [
        "Footwear",
        "Bow heels",
        "Boat Shoes",
        "Ankle Strap Flats",
        "Off-Duty Athlete Looks",
        "Casual Chic Style",
        "Trends",
        "New",
    ],
    "accessory": [
        "Beauty",
        "Handbag #handsips",
        "Music Clothes",
        "\"Music Clothes\"",
        "Gimme Gummy Playful Nostalgia",
        "Moody Blues & Vintage Pinks",
        "Trends",
        "New",
    ],
    "jumpsuit": [
        "Rompers, Jumpsuits &...",
        "Rompers_Jumpsuits &...",
        "Dressy Outfits",
        "Casual Chic Style",
        "Trends",
        "New",
    ],
    "lounge": [
        "Loungewear",
        "Relaxed Yet Trendy...",
        "Weekend to Workwear",
        "Weekend to Workout",
        "Look casual...",
        "Simple Outfits",
        "Cool & Casual Styles",
        "Off-Duty Athlete Looks",
    ],
    "dark": [
        "Vamp Romantic Styles",
        "Moody Blues & Vintage Pinks",
        "Edgy Fashion",
        "Trends",
    ],
    "aesthetic": [
        "Poetcore Aesthetics",
        "Festive & Flora Fits",
        "Gimme Gummy Playful Nostalgia",
        "Trends",
    ],
    "luxe": [
        "Luxe Clothing",
        "MeeeShop's Luxe Styles",
        "Meshohn Luxe Styles",
        "Wardrobe Goals",
        "Wardrobe Oozes",
        "Mustard Seed Clothing",
        "Zenana Women's...",
        "Zenana Womens...",
        "Emory Park Clothing",
        "Davi & Dani Womens...",
        "LE LIS Womens Clothi...",
        "Umgee USA",
    ],
    "default": [
        "Must-Have Fashion...",
        "Trendy & Timeless...",
        "Our Recommended...",
        "Wardrobe Must-Hav...",
        "Wardrobe Must Haves",
        "Wardrobe Goals",
        "Confident Looks",
        "My Shop #1737732113",
        "Shop For Holidays",
        "BFCM Deals",
        "Trends",
        "New",
        "new products",
        "Best selling products",
        "New Trendy Woman...",
        "Outfit Ideas",
        "Style Ideas",
        "Ootd #ootd",
        "Everyday Style",
        "Woman Fashion!",
        "Chic & Effortless Styles",
        "Stylish Finds",
        "Confidence Ladies",
        "Fresh Finds New...",
        "Casual Chic Style",
        "Affordable Women's Fashion USA",
        "Shop Responsibly",
        "Social",
        "Fashion Models",
        "Blogs",
        "All Pins",
    ],
}


# Load and merge dynamically generated AI boards
import json
from pathlib import Path

DYNAMIC_BOARDS_FILE = Path(__file__).parent / "dynamic_boards.json"
if DYNAMIC_BOARDS_FILE.exists():
    try:
        dynamic_boards = json.loads(DYNAMIC_BOARDS_FILE.read_text(encoding="utf-8"))
        for cat, boards in dynamic_boards.items():
            if cat not in CATEGORY_TO_BOARDS:
                CATEGORY_TO_BOARDS[cat] = []
            for b in boards:
                if b not in CATEGORY_TO_BOARDS[cat]:
                    CATEGORY_TO_BOARDS[cat].append(b)
                if b not in MEEESHOP_BOARDS:
                    MEEESHOP_BOARDS.append(b)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to load dynamic boards: {e}")


def get_candidate_boards_for_product(
    product_title: str, product_type: str = None, prioritize_old_boards: bool = False
) -> list:
    """
    Get all matching candidate board names for a product based on title & type.

    Args:
        product_title: Product title from Shopify
        product_type: Product type from Shopify
        prioritize_old_boards: If True, candidate 1-year-old boards are ordered first.

    Returns:
        List of board names matching the product (ordered by relevance)
    """
    title_lower = (product_title or "").lower()
    type_lower = (product_type or "").lower()
    search_text = f"{title_lower} {type_lower}"

    candidates = []

    for category, boards in CATEGORY_TO_BOARDS.items():
        if category != "default" and category in search_text:
            for b in boards:
                if b in MEEESHOP_BOARDS and b not in candidates:
                    candidates.append(b)

    # Always append default/general boards to ensure broad options
    for b in CATEGORY_TO_BOARDS["default"]:
        if b in MEEESHOP_BOARDS and b not in candidates:
            candidates.append(b)

    if prioritize_old_boards:
        old_cands = [b for b in candidates if b in OLD_BOARDS_1Y or any(b.lower().startswith(o.rstrip(".").strip().lower()) for o in OLD_BOARDS_1Y)]
        other_cands = [b for b in candidates if b not in old_cands]
        candidates = old_cands + other_cands

    return candidates


def match_live_board(
    candidate_name: str, live_boards: List[Dict]
) -> Optional[Dict]:
    """
    Match candidate_name (handling trailing dots '...') against live board dicts from Pinterest.
    Returns matching live board dict or None.
    """
    cand_clean = candidate_name.rstrip(".").strip().lower()

    # 1. Exact match
    for b in live_boards:
        if b.get("name", "").lower() == candidate_name.lower():
            return b

    # 2. Cleaned prefix/substring match (handles trailing '...')
    for b in live_boards:
        b_name_lower = b.get("name", "").lower()
        if b_name_lower.startswith(cand_clean) or cand_clean in b_name_lower or b_name_lower in cand_clean:
            return b

    return None


def select_best_lru_board(
    product_title: str,
    product_type: str = None,
    live_boards: List[Dict] = None,
    board_last_used: dict = None,
    used_boards_in_run: set = None,
    prioritize_old_boards: bool = False,
) -> Dict:
    """
    Select the best live Pinterest board object matching the product category,
    using Least Recently Used (LRU) logic. Strictly avoids cross-category misassignments.

    Args:
        product_title: Product title
        product_type: Product type
        live_boards: List of live board dicts from Pinterest API [{'name': ..., 'id': ...}]
        board_last_used: Dict mapping board_name -> ISO timestamp string
        used_boards_in_run: Set of board names already used in the current run
        prioritize_old_boards: If True, prioritizes 1-year-old boards first

    Returns:
        Selected live board dict
    """
    if board_last_used is None:
        board_last_used = {}
    if used_boards_in_run is None:
        used_boards_in_run = set()
    if not live_boards:
        live_boards = [
            {"name": b, "id": f"mock_{i}"} for i, b in enumerate(MEEESHOP_BOARDS)
        ]

    candidates = get_candidate_boards_for_product(
        product_title, product_type, prioritize_old_boards=prioritize_old_boards
    )

    # Resolve candidate names to live board objects
    resolved_boards = []
    for cand_name in candidates:
        matched = match_live_board(cand_name, live_boards)
        if matched and matched not in resolved_boards:
            resolved_boards.append(matched)

    # Filter out boards used in current run if possible
    available = [
        b for b in resolved_boards if b.get("name") not in used_boards_in_run
    ]
    if not available:
        available = resolved_boards

    if not available:
        available = live_boards

    # If prioritizing old boards, split into old vs normal available boards
    if prioritize_old_boards:
        old_available = [
            b for b in available
            if any(b.get("name", "").lower().startswith(o.rstrip(".").strip().lower()) for o in OLD_BOARDS_1Y)
        ]
        if old_available:
            available = old_available

    # Sort available boards by last_used timestamp (LRU first)
    def get_last_used_score(board_dict: Dict) -> str:
        b_name = board_dict.get("name", "")
        return board_last_used.get(b_name, "1970-01-01T00:00:00")

    available.sort(key=get_last_used_score)
    return available[0]


def get_board_for_product(product_title: str, product_type: str = None) -> str:
    """
    Legacy wrapper — returns candidate board for product.
    """
    candidates = get_candidate_boards_for_product(product_title, product_type)
    return candidates[0] if candidates else MEEESHOP_BOARDS[0]


def validate_board(board_name: str) -> str:
    """
    Validate and return a board name from the list.
    """
    if board_name in MEEESHOP_BOARDS:
        return board_name
    return MEEESHOP_BOARDS[0]


if __name__ == "__main__":
    print(f"Total boards indexed: {len(MEEESHOP_BOARDS)}")
    print(f"Total 1-year-old boards indexed: {len(OLD_BOARDS_1Y)}\n")
    samples = [
        ("Puff Sleeve Dress", "Dress"),
        ("Blue Denim Jeans", "Jeans"),
        ("Leather Jacket", "Jacket"),
        ("Gold Necklace", "Accessory"),
        ("Canvas Nylon Backpack", "Bag"),
        ("Ankle Strap Flats", "Shoes"),
    ]
    mock_last_used = {
        "Dresses": "2026-08-01T00:00:00",
        "Jeans": "2026-08-01T00:00:00",
    }
    for title, ptype in samples:
        cands = get_candidate_boards_for_product(title, ptype, prioritize_old_boards=True)
        best = select_best_lru_board(title, ptype, mock_last_used=mock_last_used, prioritize_old_boards=True)
        print(f"'{title}' -> Candidate Count: {len(cands)} | Best Old LRU Board: '{best.get('name')}'")


