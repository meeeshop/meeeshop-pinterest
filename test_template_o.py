"""
test_template_o.py — Test script to verify Template O (Quad Quad Collage + Trust Badge)
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from image_overlay import create_pin_image, add_text_overlay

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_template_o")

def test_rendering():
    test_img = Path(__file__).parent / "test_product.jpg"
    if not test_img.exists():
        from create_test_image import create_test_product_image
        create_test_product_image(str(test_img))

    out_path = Path(__file__).parent / "test_template_o_output.jpg"
    
    result = create_pin_image(
        product_image_path=str(test_img),
        title="Chic Floral Print Spaghetti Strap Summer Maxi Dress",
        category="Trending: Dresses",
        price="49.99",
        cta="Shop Now at us.MeeeShop.com",
        output_path=str(out_path),
        template_index=14,  # Template O
        board_name="Summer Dresses & Outfits",
        image_style="hero"
    )

    if result and Path(result).exists():
        logger.info(f"✅ Template O generated successfully: {result} (Size: {Path(result).stat().st_size} bytes)")
    else:
        logger.error("❌ Failed to render Template O")

if __name__ == "__main__":
    test_rendering()
