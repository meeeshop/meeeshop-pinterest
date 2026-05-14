"""
Image overlay functionality for Pinterest pins.
Adds product title, CTA, and pricing as overlays on product images.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def add_text_overlay(
    image_path: str,
    title: str,
    cta: str = "Shop Now",
    price: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Add text overlay (title + CTA) to product image.

    Args:
        image_path: Path to original product image
        title: Product title to overlay
        cta: Call-to-action text (default: "Shop Now")
        price: Optional price to display
        output_path: Where to save overlay image (default: temp_overlay.jpg)

    Returns:
        Path to overlay image or None if failed
    """
    try:
        if not Path(image_path).exists():
            logger.error(f"Image not found: {image_path}")
            return None

        # Open image
        img = Image.open(image_path).convert("RGB")
        width, height = img.size

        # Create overlay (semi-transparent dark layer at bottom for text)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Add dark gradient at bottom for text readability
        overlay_height = int(height * 0.35)  # 35% of image height
        for y in range(height - overlay_height, height):
            alpha = int(200 * (y - (height - overlay_height)) / overlay_height)
            overlay_draw.rectangle(
                [(0, y), (width, y + 1)],
                fill=(0, 0, 0, alpha),
            )

        # Merge overlay with image
        img_with_overlay = Image.alpha_composite(
            img.convert("RGBA"), overlay
        ).convert("RGB")

        # Draw text on image
        draw = ImageDraw.Draw(img_with_overlay)

        # Load font (use default if system fonts not available)
        try:
            title_font = ImageFont.truetype("arial.ttf", int(height * 0.08))
            cta_font = ImageFont.truetype("arial.ttf", int(height * 0.06))
            price_font = ImageFont.truetype("arial.ttf", int(height * 0.05))
        except Exception:
            title_font = ImageFont.load_default()
            cta_font = ImageFont.load_default()
            price_font = ImageFont.load_default()

        # Calculate text positions
        margin = int(width * 0.05)
        title_y = height - overlay_height + margin
        cta_y = height - int(overlay_height * 0.6)
        price_y = height - int(overlay_height * 0.2) if price else None

        # Draw title (truncate if too long)
        max_title_len = 60
        if len(title) > max_title_len:
            title = title[: max_title_len - 3] + "..."

        draw.text(
            (margin, title_y),
            title,
            fill=(255, 255, 255),
            font=title_font,
        )

        # Draw CTA
        draw.text(
            (margin, cta_y),
            cta,
            fill=(255, 182, 193),  # Light pink for contrast
            font=cta_font,
        )

        # Draw price if provided
        if price and price_y:
            draw.text(
                (margin, price_y),
                f"${price}",
                fill=(255, 255, 255),
                font=price_font,
            )

        # Save overlay image
        if not output_path:
            output_path = str(Path(image_path).parent / "pin_with_overlay.jpg")

        img_with_overlay.save(output_path, quality=95)
        logger.info(f"Created overlay image: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to create image overlay: {e}")
        return None


def create_video_pin_thumbnail(
    title: str,
    description: str,
    image_width: int = 1200,
    image_height: int = 1500,
    output_path: str = "video_thumbnail.jpg",
) -> Optional[str]:
    """
    Create a thumbnail for video pins with title and description overlay.

    Args:
        title: Video title
        description: Video description
        image_width: Thumbnail width (default Pinterest pin width)
        image_height: Thumbnail height (default Pinterest pin height)
        output_path: Where to save thumbnail

    Returns:
        Path to thumbnail or None if failed
    """
    try:
        # Create gradient background (fashion-oriented colors)
        img = Image.new("RGB", (image_width, image_height), (240, 240, 245))
        draw = ImageDraw.Draw(img)

        # Add gradient overlay
        for y in range(image_height):
            # Gradient from light purple to light pink
            r = int(240 + (255 - 240) * (y / image_height))
            g = int(240 + (192 - 240) * (y / image_height))
            b = int(245 + (203 - 245) * (y / image_height))
            draw.line([(0, y), (image_width, y)], fill=(r, g, b))

        # Add "VIDEO" badge
        try:
            badge_font = ImageFont.truetype("arial.ttf", int(image_width * 0.08))
            title_font = ImageFont.truetype("arial.ttf", int(image_width * 0.06))
            desc_font = ImageFont.truetype("arial.ttf", int(image_width * 0.04))
        except Exception:
            badge_font = ImageFont.load_default()
            title_font = ImageFont.load_default()
            desc_font = ImageFont.load_default()

        # Badge at top
        badge_text = "▶ VIDEO"
        draw.text(
            (image_width * 0.05, image_height * 0.1),
            badge_text,
            fill=(255, 50, 100),
            font=badge_font,
        )

        # Title in center
        margin = image_width * 0.08
        title_y = image_height * 0.35
        draw.text(
            (margin, title_y),
            title,
            fill=(255, 255, 255),
            font=title_font,
        )

        # Description below title
        desc_y = title_y + image_width * 0.1
        draw.text(
            (margin, desc_y),
            description[:100],  # Truncate long descriptions
            fill=(200, 200, 200),
            font=desc_font,
        )

        # Save thumbnail
        img.save(output_path, quality=95)
        logger.info(f"Created video thumbnail: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to create video thumbnail: {e}")
        return None
