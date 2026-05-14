"""
Image overlay functionality for Pinterest pins with algorithm-friendly optimization.
Adds product title, CTA, and pricing as overlays on product images.
Optimizes for Pinterest's content recommendation system.
"""

import logging
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logger = logging.getLogger(__name__)

# Pinterest recommended image specs
PINTEREST_SPECS = {
    "width": 1200,
    "height": 1500,
    "aspect_ratio": 0.8,  # 4:5 is optimal for feed
    "min_width": 600,
    "min_height": 750,
    "quality": 95,
    "format": "JPG",
}


def optimize_image_for_pinterest(image_path: str, output_path: Optional[str] = None) -> Optional[str]:
    """
    Optimize image dimensions and quality per Pinterest recommendations.

    Pinterest algorithm favors:
    - 4:5 aspect ratio (1200x1500px ideal)
    - High quality JPG (95+ quality)
    - Well-lit, clear product images
    - Minimal watermarks
    - Central subject focus

    Args:
        image_path: Path to original image
        output_path: Where to save optimized image

    Returns:
        Path to optimized image or None if failed
    """
    try:
        if not Path(image_path).exists():
            logger.error(f"Image not found: {image_path}")
            return None

        img = Image.open(image_path).convert("RGB")
        orig_width, orig_height = img.size
        logger.info(f"Original image: {orig_width}x{orig_height}")

        # Calculate new dimensions maintaining aspect ratio or fitting to Pinterest ideal
        target_width = PINTEREST_SPECS["width"]
        target_height = PINTEREST_SPECS["height"]
        target_ratio = target_width / target_height

        current_ratio = orig_width / orig_height

        if current_ratio > target_ratio:
            # Image is too wide, fit to height
            new_height = target_height
            new_width = int(new_height * current_ratio)
        else:
            # Image is too tall, fit to width
            new_width = target_width
            new_height = int(new_width / current_ratio)

        # Resize with high-quality resampling
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Create canvas with Pinterest ideal dimensions (white background for padding)
        canvas = Image.new("RGB", (target_width, target_height), (255, 255, 255))

        # Center image on canvas
        x_offset = (target_width - new_width) // 2
        y_offset = (target_height - new_height) // 2

        canvas.paste(img, (x_offset, y_offset))

        # Apply slight sharpening for algorithm preference
        enhancer = ImageEnhance.Sharpness(canvas)
        canvas = enhancer.enhance(1.2)  # 20% sharpness boost

        # Slightly enhance color/contrast for visual appeal
        contrast_enhancer = ImageEnhance.Contrast(canvas)
        canvas = contrast_enhancer.enhance(1.1)  # 10% contrast boost

        # Save with high quality
        if not output_path:
            output_path = str(Path(image_path).parent / "pin_optimized.jpg")

        canvas.save(output_path, format="JPEG", quality=PINTEREST_SPECS["quality"], optimize=True)
        logger.info(f"Optimized image: {target_width}x{target_height} → {output_path}")

        return output_path

    except Exception as e:
        logger.error(f"Failed to optimize image: {e}")
        return None


def add_text_overlay(
    image_path: str,
    title: str,
    cta: str = "Shop Now",
    price: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Add text overlay (title + CTA) to product image.

    Text placement optimized for Pinterest:
    - Bottom 35% of image for overlay
    - High contrast white text
    - Readable font sizes
    - Clear call-to-action

    Args:
        image_path: Path to original product image
        title: Product title to overlay
        cta: Call-to-action text (default: "Shop Now")
        price: Optional price to display
        output_path: Where to save overlay image

    Returns:
        Path to overlay image or None if failed
    """
    try:
        if not Path(image_path).exists():
            logger.error(f"Image not found: {image_path}")
            return None

        # First optimize image for Pinterest
        img_path = optimize_image_for_pinterest(image_path)
        if not img_path:
            logger.warning("Image optimization failed, using original")
            img_path = image_path

        img = Image.open(img_path).convert("RGB")
        width, height = img.size

        # Create overlay (semi-transparent dark layer at bottom for text)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Add dark gradient at bottom for text readability
        # Gradient prevents text from overlapping product details
        overlay_height = int(height * 0.35)
        for y in range(height - overlay_height, height):
            # Gradient from transparent to opaque
            alpha = int(220 * (y - (height - overlay_height)) / overlay_height)
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

        # Load font - Pinterest prefers sans-serif bold fonts
        try:
            # Try to load bold Arial for better visibility
            title_font_size = max(int(height * 0.08), 32)  # Min 32pt
            cta_font_size = max(int(height * 0.06), 24)  # Min 24pt
            price_font_size = max(int(height * 0.05), 18)  # Min 18pt

            title_font = ImageFont.truetype("arial.ttf", title_font_size)
            cta_font = ImageFont.truetype("arial.ttf", cta_font_size)
            price_font = ImageFont.truetype("arial.ttf", price_font_size)
        except Exception:
            title_font = ImageFont.load_default()
            cta_font = ImageFont.load_default()
            price_font = ImageFont.load_default()

        # Calculate text positions
        margin = int(width * 0.05)
        title_y = height - overlay_height + int(margin * 1.5)
        cta_y = height - int(overlay_height * 0.6)
        price_y = height - int(overlay_height * 0.2) if price else None

        # Draw title (truncate if too long to prevent overflow)
        # Pinterest recommends short, punchy titles
        max_title_len = 50
        if len(title) > max_title_len:
            title = title[: max_title_len - 3] + "..."

        # Use bright white for maximum contrast
        draw.text(
            (margin, title_y),
            title,
            fill=(255, 255, 255),
            font=title_font,
        )

        # Draw CTA in accent color (pinkish for fashion)
        # Pinterest algorithm favors clear CTAs
        draw.text(
            (margin, cta_y),
            cta.upper(),  # Uppercase for emphasis
            fill=(255, 100, 120),  # Soft red/pink
            font=cta_font,
        )

        # Draw price if provided
        if price and price_y:
            draw.text(
                (margin, price_y),
                f"${price}",
                fill=(255, 215, 0),  # Gold color for value emphasis
                font=price_font,
            )

        # Save overlay image with high quality
        if not output_path:
            output_path = str(Path(image_path).parent / "pin_with_overlay.jpg")

        img_with_overlay.save(
            output_path,
            format="JPEG",
            quality=PINTEREST_SPECS["quality"],
            optimize=True
        )
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

    Video pins need:
    - Clear "VIDEO" badge to stand out in feed
    - Product details visible
    - Strong CTA
    - 4:5 aspect ratio

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
        # Gradient attracts algorithm attention vs solid background
        img = Image.new("RGB", (image_width, image_height), (245, 240, 250))
        draw = ImageDraw.Draw(img)

        # Add elegant gradient from lavender to pink
        for y in range(image_height):
            # Gradient intensity based on vertical position
            progress = y / image_height
            r = int(245 - 20 * progress)  # 245 → 225
            g = int(240 - 40 * progress)  # 240 → 200
            b = int(250 - 50 * progress)  # 250 → 200
            draw.line([(0, y), (image_width, y)], fill=(r, g, b))

        # Load fonts
        try:
            badge_font = ImageFont.truetype("arial.ttf", max(int(image_width * 0.10), 40))
            title_font = ImageFont.truetype("arial.ttf", max(int(image_width * 0.07), 32))
            desc_font = ImageFont.truetype("arial.ttf", max(int(image_width * 0.045), 20))
        except Exception:
            badge_font = ImageFont.load_default()
            title_font = ImageFont.load_default()
            desc_font = ImageFont.load_default()

        # Add prominent "VIDEO" badge at top
        # Video pins get higher engagement when clearly marked
        badge_text = "▶ VIDEO"
        badge_x = image_width * 0.05
        badge_y = image_height * 0.08

        # Draw badge with semi-transparent background for readability
        badge_bg = Image.new("RGBA", img.size, (0, 0, 0, 0))
        badge_draw = ImageDraw.Draw(badge_bg)
        badge_draw.rectangle(
            [(badge_x - 20, badge_y - 20), (badge_x + 200, badge_y + 60)],
            fill=(255, 0, 0, 180),
        )
        img = Image.alpha_composite(img.convert("RGBA"), badge_bg).convert("RGB")
        draw = ImageDraw.Draw(img)

        draw.text(
            (badge_x, badge_y),
            badge_text,
            fill=(255, 255, 255),  # White on red
            font=badge_font,
        )

        # Title in center with emphasis
        margin = image_width * 0.08
        title_y = image_height * 0.35
        draw.text(
            (margin, title_y),
            title[:60],  # Limit title length
            fill=(255, 255, 255),
            font=title_font,
        )

        # Description below title
        desc_y = title_y + image_width * 0.12
        # Truncate and format description
        desc_text = description[:80] if description else "Watch now"
        draw.text(
            (margin, desc_y),
            desc_text,
            fill=(220, 220, 220),
            font=desc_font,
        )

        # Save with Pinterest specs
        img.save(output_path, format="JPEG", quality=PINTEREST_SPECS["quality"], optimize=True)
        logger.info(f"Created video thumbnail: {output_path}")

        return output_path

    except Exception as e:
        logger.error(f"Failed to create video thumbnail: {e}")
        return None
