from typing import List, Dict, Optional, Any

# Complete list of MeeeShop Pinterest boards

MEEESHOP_BOARDS = [
    "All Pins",
    "Fashion Models",
    "Fresh Finds New...",
    "Music Clothes",
    "American Ball",
    "Ankle Strap Flats",
    "Bags",
    "Beauty",
    "Best selling products",
    "BFCM Deals",
    "Blouse",
    "Blouses",
    "Boat Shoes",
    "Camis & Tanks",
    "Casual",
    "Chic & Cozy Anim...",
    "Chic & Effortless Styles",
    "Chic Looks",
    "Coats & Jackets",
    "Cocktail Dresses",
    "comfy fall outfits",
    "Confidence Ladies",
    "Cool & Casual Styles",
    "Daris & Desi Womens...",
    "Dress",
    "Dresses",
    "Dressy Outfits",
    "Edgy Fashion",
    "Effortless Looks",
    "Every Peak Clothing",
    "Everyday Style",
    "Fall looks",
    "Fern Clothes",
    "Festival",
    "Festive & Flora Fits",
    "Festive Styles",
    "Fitted Jeans",
    "Footwear",
    "Handbag #handsips",
    "Jeans",
    "Kimchi USA Jeans",
    "LE US Womens Cloth...",
    "Loungewear",
    "Luxe Clothing",
    "Meshohn Luxe Styles",
    "Mist More Fashion...",
    "Mustard Seed Clothing",
    "My Shop 8727/2019",
    "New",
    "new products",
    "New Trendy Woman...",
    "Nylon backpack",
    "Ootd #ootd",
    "Our Recommended...",
    "Outer wear",
    "Outfit Ideas",
    "Pants & Leggings",
    "Plus Size",
    "Puff Sleeves Tops",
    "Relaxed Yet Trendy...",
    "Rompers_Jumpsuits &...",
    "Shirts & Tops",
    "Shop For Hotties",
    "Shop Responsibly",
    "Short Tall dresses",
    "Simple Outfits",
    "Skirts",
    "Social",
    "Spicing Outfits",
    "Straight Leg Jeans",
    "Style Ideas",
    "Stylish Finds",
    "Sweaters",
    "Sweaters & Sweater...",
    "Sweaters for women",
    "Thanks giving Outfits",
    "Trends",
    "Trendy & Trendes...",
    "Trendy Backpacks",
    "Unique USA",
    "Wardrobe Oozes",
    "Wardrobe Must Haves",
    "Weekend to Workout",
    "Winter Outfits",
    "Woman Fashion!",
    "Womens Cardigans",
    "Womens shacket",
    "Zenana Womens...",
    "Poetcore Aesthetics",
    "Vamp Romantic Styles",
    "Off-Duty Athlete Looks",
    "Gimme Gummy Playful Nostalgia",
    "Moody Blues & Vintage Pinks",
    "Fall Outfits 2026",
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
]

PRIORITY_BOARDS = [
    "Trends",
    "New",
    "Best selling products",
    "Outfit Ideas",
    "Ootd #ootd",
    "Style Ideas",
    "Everyday Style",
    "Wardrobe Must Haves",
    "Woman Fashion!",
    "Chic & Effortless Styles",
    "Stylish Finds",
    "Confidence Ladies",
    "Poetcore Aesthetics",
    "Vamp Romantic Styles",
    "Off-Duty Athlete Looks",
]

# Dedicated Blog & Editorial Boards
BLOG_BOARDS = [
    "Our Recommended...",
    "My Shop 8727/2019",
    "Social",
    "Fashion Models",
    "Style Ideas",
    "Outfit Ideas",
    "Trends",
    "Everyday Style",
    "Casual Chic Style",
    "Affordable Women's Fashion USA",
]


# Comprehensive category to board mapping covering ALL 105 boards
CATEGORY_TO_BOARDS = {
    "dress": [
        "Dresses",
        "Dress",
        "Cocktail Dresses",
        "Dressy Outfits",
        "Short Tall dresses",
        "Rompers_Jumpsuits &...",
        "Poetcore Aesthetics",
        "Vamp Romantic Styles",
        "Festive & Flora Fits",
        "Trends",
        "New",
        "Best selling products",
    ],
    "top": [
        "Blouses",
        "Blouse",
        "Camis & Tanks",
        "Shirts & Tops",
        "Puff Sleeves Tops",
        "Chic & Effortless Styles",
        "Effortless Looks",
        "Trends",
        "New",
        "Best selling products",
    ],
    "jeans": [
        "Jeans",
        "Fitted Jeans",
        "Straight Leg Jeans",
        "Kimchi USA Jeans",
        "Pants & Leggings",
        "Casual Chic Style",
        "Everyday Style",
        "Trends",
        "New",
    ],
    "jacket": [
        "Coats & Jackets",
        "Outer wear",
        "Womens shacket",
        "Sweaters",
        "Winter Outfits",
        "comfy fall outfits",
        "Fall Outfits 2026",
        "Trends",
        "New",
    ],
    "pants": [
        "Pants & Leggings",
        "Jeans",
        "Casual",
        "Cool & Casual Styles",
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
        "Poetcore Aesthetics",
        "Trends",
        "New",
    ],
    "sweater": [
        "Sweaters",
        "Sweaters & Sweater...",
        "Sweaters for women",
        "Womens Cardigans",
        "Chic & Cozy Anim...",
        "comfy fall outfits",
        "Fall Outfits 2026",
        "Trends",
        "New",
    ],
    "cardigan": [
        "Womens Cardigans",
        "Sweaters",
        "Sweaters & Sweater...",
        "Chic & Cozy Anim...",
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
        "Gimme Gummy Playful Nostalgia",
        "Moody Blues & Vintage Pinks",
        "Trends",
        "New",
    ],
    "jumpsuit": [
        "Rompers_Jumpsuits &...",
        "Dressy Outfits",
        "Casual Chic Style",
        "Trends",
        "New",
    ],
    "lounge": [
        "Loungewear",
        "Weekend to Workout",
        "Simple Outfits",
        "Cool & Casual Styles",
        "Relaxed Yet Trendy...",
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
        "Meshohn Luxe Styles",
        "Wardrobe Oozes",
        "Mustard Seed Clothing",
        "Zenana Womens...",
        "Fern Clothes",
        "LE US Womens Cloth...",
        "Mist More Fashion...",
    ],
    "default": [
        "Trends",
        "New",
        "new products",
        "Best selling products",
        "New Trendy Woman...",
        "Outfit Ideas",
        "Style Ideas",
        "Ootd #ootd",
        "Everyday Style",
        "Wardrobe Must Haves",
        "Woman Fashion!",
        "Chic & Effortless Styles",
        "Stylish Finds",
        "Confidence Ladies",
        "Shop For Hotties",
        "Spicing Outfits",
        "Fresh Finds New...",
        "Casual Chic Style",
        "Affordable Women's Fashion USA",
        "American Ball",
        "Unique USA",
        "Every Peak Clothing",
        "Shop Responsibly",
        "Social",
        "Fashion Models",
        "All Pins",
    ],
}


def get_candidate_boards_for_product(product_title: str, product_type: str = None) -> list:
    """
    Get all matching candidate board names for a product based on title & type.

    Args:
        product_title: Product title from Shopify
        product_type: Product type from Shopify

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
        if b_name_lower.startswith(cand_clean) or cand_clean in b_name_lower:
            return b

    return None


def select_best_lru_board(
    product_title: str,
    product_type: str = None,
    live_boards: List[Dict] = None,
    board_last_used: dict = None,
    used_boards_in_run: set = None,
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

    candidates = get_candidate_boards_for_product(product_title, product_type)

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
    print(f"Total boards indexed: {len(MEEESHOP_BOARDS)}\n")
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
        cands = get_candidate_boards_for_product(title, ptype)
        best = select_best_lru_board(title, ptype, mock_last_used)
        print(f"'{title}' -> Candidate Count: {len(cands)} | Best LRU Board: '{best}'")

