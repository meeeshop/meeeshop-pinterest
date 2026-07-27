#!/usr/bin/env python3
"""
board_mapping.py — Board name mappings for MeeeShop Pinterest account
Extracted from actual board list - high-traffic boards prioritized
"""

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

# HIGH_TRAFFIC_BOARDS (prioritized for new products)
HIGH_TRAFFIC_BOARDS = ["Trends", "New", "Best selling products", "New Trendy Woman...", "Poetcore Aesthetics", "Vamp Romantic Styles", "Off-Duty Athlete Looks"]

# Priority boards rotated into every run's pool to ensure consistent reach
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

# Product category to board mapping
CATEGORY_TO_BOARDS = {
    "dress": [
        "Dresses",
        "Cocktail Dresses",
        "Dressy Outfits",
        "Casual",
        "Trends",  # High traffic
        "New",  # High traffic
    ],
    "top": [
        "Blouses",
        "Camis & Tanks",
        "Shirts & Tops",
        "Puff Sleeves Tops",
        "Trends",  # High traffic
        "New",  # High traffic
    ],
    "jeans": [
        "Jeans",
        "Fitted Jeans",
        "Straight Leg Jeans",
        "Trends",  # High traffic
        "New",  # High traffic
    ],
    "jacket": [
        "Coats & Jackets",
        "Sweaters",
        "Womens shacket",
        "Trends",  # High traffic
    ],
    "pants": [
        "Pants & Leggings",
        "Casual",
        "Trends",  # High traffic
        "New",  # High traffic
    ],
    "skirt": [
        "Skirts",
        "Dressy Outfits",
        "Trends",  # High traffic
        "New",  # High traffic
    ],
    "sweater": [
        "Sweaters",
        "Sweaters & Sweater...",
        "Chic & Cozy Anim...",
        "Trends",  # High traffic
        "New",  # High traffic
    ],
    "cardigan": [
        "Womens Cardigans",
        "Sweaters",
        "Trends",  # High traffic
    ],
    "bag": [
        "Bags",
        "Handbag #handsips",
        "Trendy Backpacks",
        "Trends",  # High traffic
    ],
    "shoe": [
        "Boat Shoes",
        "Ankle Strap Flats",
        "Footwear",
        "Off-Duty Athlete Looks",  # High traffic
        "Trends",  # High traffic
    ],
    "accessory": [
        "Beauty",
        "Handbag #handsips",
        "Gimme Gummy Playful Nostalgia",  # High traffic
        "Trends",  # High traffic
    ],
    "jumpsuit": [
        "Rompers_Jumpsuits &...",
        "Trends",  # High traffic
        "New",  # High traffic
    ],
    "dark": [
        "Vamp Romantic Styles",
        "Moody Blues & Vintage Pinks",
        "Trends",
    ],
    "aesthetic": [
        "Poetcore Aesthetics",
        "Trends",
    ],
    "default": ["Trends", "New", "Best selling products", "Poetcore Aesthetics"],  # Prioritize high-traffic
}


def get_board_for_product(product_title: str, product_type: str = None) -> str:
    """
    Determine the best Pinterest board for a product based on its title/type
    Prioritizes high-traffic boards (Trends, New)

    Args:
        product_title: Product title from Shopify
        product_type: Product type from Shopify

    Returns:
        Board name to post to
    """
    title_lower = product_title.lower()
    type_lower = (product_type or "").lower()

    # Check for keywords in title or type
    search_text = f"{title_lower} {type_lower}"

    for category, boards in CATEGORY_TO_BOARDS.items():
        if category in search_text:
            # Return the first available board for this category
            for board in boards:
                if board in MEEESHOP_BOARDS:
                    return board

    # Default to high-traffic boards
    return CATEGORY_TO_BOARDS["default"][0]


def validate_board(board_name: str) -> str:
    """
    Validate and return a board name from the list
    If not found, return a high-traffic default board

    Args:
        board_name: Board name to validate

    Returns:
        Valid board name from MEEESHOP_BOARDS
    """
    if board_name in MEEESHOP_BOARDS:
        return board_name

    # If not found, return default (high-traffic board)
    return CATEGORY_TO_BOARDS["default"][0]


if __name__ == "__main__":
    print(f"Total boards: {len(MEEESHOP_BOARDS)}\n")
    print(f"High-traffic boards: {HIGH_TRAFFIC_BOARDS}\n")
    print("Sample mappings:")
    samples = [
        "Puff Sleeve Dress",
        "Blue Jeans",
        "Leather Jacket",
        "Gold Necklace",
        "Canvas Backpack",
        "3/4 Puff Slv Texture Vneck Button Down Midi Dress",
    ]
    for sample in samples:
        board = get_board_for_product(sample)
        print(f"  '{sample}' -> {board}")
