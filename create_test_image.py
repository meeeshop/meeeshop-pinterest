"""
Create an optimized test product image with overlay text and CTA.
Uses PIL to generate Pinterest-optimized product images.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os

def create_test_product_image(
    output_path: str = "test_product.jpg",
    width: int = 1000,
    height: int = 1500,
    product_title: str = "Elegant Women's Fashion",
    cta_text: str = "Shop Now"
):
    """
    Create a test product image with overlay text and CTA button.
    Optimized for Pinterest (1000x1500px = ideal ratio).

    Args:
        output_path: Where to save the image
        width: Image width in pixels (default 1000)
        height: Image height in pixels (default 1500)
        product_title: Product name for overlay
        cta_text: Call-to-action button text
    """

    # Create base image with gradient background (appealing for fashion)
    img = Image.new('RGB', (width, height), color=(245, 245, 245))  # Light gray
    draw = ImageDraw.Draw(img, 'RGBA')

    # Add gradient-like background
    for y in range(height):
        # Create a subtle gradient from light gray to white
        r = int(245 - (y / height) * 20)
        g = int(245 - (y / height) * 20)
        b = int(245 - (y / height) * 10)
        draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))

    # Add a semi-transparent product showcase box in the center
    box_width = width - 100
    box_height = int(height * 0.6)
    box_x = (width - box_width) // 2
    box_y = int(height * 0.1)

    # Light background for product area
    draw.rectangle(
        [(box_x, box_y), (box_x + box_width, box_y + box_height)],
        fill=(255, 255, 255, 220),  # Semi-transparent white
        outline=(200, 200, 200),
        width=2
    )

    # Add product icon/placeholder
    icon_size = int(box_height * 0.5)
    icon_x = (width - icon_size) // 2
    icon_y = box_y + int((box_height - icon_size) * 0.3)

    # Draw a simple fashion item silhouette (dress)
    draw.ellipse(
        [(icon_x, icon_y), (icon_x + icon_size, icon_y + int(icon_size * 0.3))],
        fill=(100, 150, 200)  # Blue color for fashion
    )
    draw.rectangle(
        [(icon_x + int(icon_size * 0.15), icon_y + int(icon_size * 0.25)),
         (icon_x + int(icon_size * 0.85), icon_y + int(icon_size * 0.9))],
        fill=(100, 150, 200)
    )

    # Add product title text
    try:
        # Try to use a larger font
        title_font = ImageFont.truetype("arial.ttf", 48)
        cta_font = ImageFont.truetype("arial.ttf", 36)
    except:
        # Fallback to default font
        title_font = ImageFont.load_default()
        cta_font = ImageFont.load_default()

    # Title positioning
    title_y = box_y + box_height + 50
    title_bbox = draw.textbbox((0, 0), product_title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (width - title_width) // 2

    draw.text(
        (title_x, title_y),
        product_title,
        fill=(40, 40, 40),  # Dark gray text
        font=title_font
    )

    # Add CTA button
    button_y = title_y + 80
    button_width = 300
    button_height = 60
    button_x = (width - button_width) // 2

    # Button background
    draw.rectangle(
        [(button_x, button_y), (button_x + button_width, button_y + button_height)],
        fill=(200, 50, 100),  # Fashion pink/red
        outline=(150, 40, 80),
        width=3
    )

    # Button text
    cta_bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
    cta_width = cta_bbox[2] - cta_bbox[0]
    cta_height = cta_bbox[3] - cta_bbox[1]
    cta_x = button_x + (button_width - cta_width) // 2
    cta_y = button_y + (button_height - cta_height) // 2

    draw.text(
        (cta_x, cta_y),
        cta_text,
        fill=(255, 255, 255),  # White text
        font=cta_font
    )

    # Add corner badge (e.g., "New" or "Sale")
    badge_size = 80
    draw.ellipse(
        [(width - badge_size - 20, 20), (width - 20, badge_size + 20)],
        fill=(255, 215, 0)  # Gold
    )

    try:
        badge_font = ImageFont.truetype("arial.ttf", 20)
    except:
        badge_font = ImageFont.load_default()

    draw.text(
        (width - badge_size + 5, 35),
        "NEW",
        fill=(40, 40, 40),
        font=badge_font
    )

    # Save image
    img.save(output_path, quality=85, optimize=True)
    print(f"[OK] Created test product image: {output_path}")
    print(f"  Dimensions: {width}x{height}px (Pinterest optimal)")
    print(f"  Product: {product_title}")
    print(f"  File size: {os.path.getsize(output_path) / 1024:.1f}KB")

    return output_path


if __name__ == "__main__":
    # Create test product image
    create_test_product_image(
        output_path="test_product.jpg",
        product_title="Elegant Women's Fashion",
        cta_text="Shop Now"
    )
