"""
image_optimizer.py — Optimize product images for Pinterest with overlays
Adds: background, product title, CTA text, keywords as overlay
Creates Pinterest-optimized images (1000x1500px recommended)
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import requests
from io import BytesIO

logger = logging.getLogger(__name__)


class ImageOptimizer:
    """Optimize product images for Pinterest with text overlays"""

    # Pinterest recommended sizes
    PINTEREST_WIDTH = 1000
    PINTEREST_HEIGHT = 1500
    ASPECT_RATIO = PINTEREST_HEIGHT / PINTEREST_WIDTH  # 1.5:1

    # Colors for women's fashion
    OVERLAY_COLORS = {
        "dark": (20, 20, 20),  # Dark gray/black
        "white": (255, 255, 255),
        "accent_rose": (219, 112, 147),  # Pale Violet Red
        "accent_teal": (0, 128, 128),  # Teal
        "accent_gold": (184, 134, 11),  # Dark Goldenrod
    }

    def __init__(self):
        self.fonts = self._load_fonts()

    def _load_fonts(self) -> Dict[str, Optional[ImageFont.FreeTypeFont]]:
        """Load available system fonts (medium sizes)"""
        fonts = {"title": None, "cta": None, "keyword": None}
        font_paths = [
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

        try:
            for path in font_paths:
                p = Path(path)
                if p.exists():
                    try:
                        fonts["title"] = ImageFont.truetype(str(p), 44)
                        fonts["cta"] = ImageFont.truetype(str(p), 32)
                        fonts["keyword"] = ImageFont.truetype(str(p), 24)
                        logger.info(f"✓ Fonts loaded from {path}")
                        return fonts
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Could not load fonts: {e}")

        return fonts

    def download_image(self, image_url: str) -> Optional[Image.Image]:
        """Download image from URL"""
        try:
            resp = requests.get(image_url, timeout=10)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content))
            logger.info(f"✓ Downloaded image: {img.size}")
            return img
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            return None

    def add_background(self, img: Image.Image, accent_color: Tuple[int, int, int] = OVERLAY_COLORS["accent_rose"]) -> Image.Image:
        """Add background with large product image (minimal background space)"""
        try:
            # Create Pinterest aspect ratio canvas
            new_width = self.PINTEREST_WIDTH
            new_height = self.PINTEREST_HEIGHT

            # Make product image large - resize to ~90% of canvas width
            max_product_width = int(new_width * 0.9)
            aspect = img.height / img.width
            new_product_height = int(max_product_width * aspect)

            # If product height exceeds canvas, scale down by height instead
            if new_product_height > int(new_height * 0.95):
                new_product_height = int(new_height * 0.95)
                max_product_width = int(new_product_height / aspect)

            img = img.resize((max_product_width, new_product_height), Image.Resampling.LANCZOS)

            # Create light background (minimal space around product)
            bg = Image.new("RGB", (new_width, new_height), color=(245, 245, 245))

            # Center product image on canvas
            offset_x = (new_width - img.width) // 2
            offset_y = (new_height - img.height) // 2
            if img.mode == "RGBA":
                bg.paste(img, (offset_x, offset_y), img)
            else:
                bg.paste(img, (offset_x, offset_y))

            logger.info(f"✓ Background added with large product: {bg.size}")
            return bg
        except Exception as e:
            logger.error(f"Failed to add background: {e}")
            return img

    def _get_dominant_color(self, img: Image.Image) -> Tuple[int, int, int]:
        """Get dominant color from image to use for contrast"""
        try:
            # Resize image for faster processing
            small = img.resize((50, 50))
            pixels = small.getdata()
            colors = {}
            for pixel in pixels:
                rgb = pixel[:3] if len(pixel) >= 3 else pixel
                colors[rgb] = colors.get(rgb, 0) + 1
            dominant = max(colors, key=colors.get)
            return dominant
        except Exception:
            return (128, 128, 128)

    def _get_contrast_color(self, rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Get contrasting color (white or dark) based on brightness"""
        # Calculate luminance
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return self.OVERLAY_COLORS["white"] if luminance < 0.5 else self.OVERLAY_COLORS["dark"]

    def add_text_overlay(
        self,
        img: Image.Image,
        title: str,
        cta: str = "SHOP NOW",
        keywords: Optional[str] = None,
        accent_color: Tuple[int, int, int] = OVERLAY_COLORS["accent_rose"],
    ) -> Image.Image:
        """Add centered text overlays with contrast colors"""
        try:
            draw = ImageDraw.Draw(img, "RGBA")

            title_font = self.fonts.get("title")
            cta_font = self.fonts.get("cta")
            keyword_font = self.fonts.get("keyword")

            # Truncate title
            title = title[:50] if len(title) > 50 else title
            cta = cta.upper()[:30]

            # Get dominant color and contrast color for overlays
            dominant = self._get_dominant_color(img)
            contrast = self._get_contrast_color(dominant)

            # Center overlay area (middle 40% of image for text)
            overlay_height = int(img.height * 0.4)
            overlay_top = (img.height - overlay_height) // 2
            overlay_bottom = overlay_top + overlay_height
            overlay_width = int(img.width * 0.85)
            overlay_left = (img.width - overlay_width) // 2
            overlay_right = overlay_left + overlay_width

            # Semi-transparent background for center overlay
            draw.rectangle(
                [(overlay_left, overlay_top), (overlay_right, overlay_bottom)],
                fill=(*self.OVERLAY_COLORS["dark"], 180),
            )

            # Draw title (center)
            if title_font:
                title_bbox = draw.textbbox((0, 0), title, font=title_font)
                title_width = title_bbox[2] - title_bbox[0]
                title_x = (img.width - title_width) // 2
                title_y = overlay_top + (overlay_height // 3)
                draw.text((title_x, title_y), title, fill=self.OVERLAY_COLORS["white"], font=title_font)

            # Draw CTA (center, below title, in accent color)
            if cta_font:
                cta_bbox = draw.textbbox((0, 0), cta, font=cta_font)
                cta_width = cta_bbox[2] - cta_bbox[0]
                cta_x = (img.width - cta_width) // 2
                cta_y = overlay_top + (overlay_height * 2 // 3) - 20
                draw.text((cta_x, cta_y), cta, fill=accent_color, font=cta_font)

            # Draw keywords (bottom center, smaller)
            if keywords and keyword_font:
                keywords_text = keywords[:60]
                kw_bbox = draw.textbbox((0, 0), keywords_text, font=keyword_font)
                kw_width = kw_bbox[2] - kw_bbox[0]
                kw_x = (img.width - kw_width) // 2
                kw_y = overlay_bottom - 40
                draw.text((kw_x, kw_y), keywords_text, fill=self.OVERLAY_COLORS["white"], font=keyword_font)

            logger.info(f"✓ Centered text overlays added")
            return img

        except Exception as e:
            logger.error(f"Failed to add text overlay: {e}")
            return img

    def enhance_image(self, img: Image.Image) -> Image.Image:
        """Enhance image: brightness, contrast, saturation"""
        try:
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.1)

            # Enhance brightness
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.05)

            # Enhance color saturation
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.15)

            logger.info(f"✓ Image enhanced")
            return img
        except Exception as e:
            logger.error(f"Failed to enhance image: {e}")
            return img

    def optimize_for_pinterest(
        self,
        image_url: str,
        product_data: Dict[str, Any],
        accent_color: str = "rose",
    ) -> Optional[Path]:
        """Complete optimization pipeline: download -> background -> enhance -> text -> save"""

        try:
            logger.info(f"🎨 Optimizing image for Pinterest...")

            # Download image
            img = self.download_image(image_url)
            if not img:
                logger.error("Could not download image")
                return None

            # Convert to RGB if needed
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Add background
            accent = self.OVERLAY_COLORS.get(f"accent_{accent_color}", self.OVERLAY_COLORS["accent_rose"])
            img = self.add_background(img, accent)

            # Enhance
            img = self.enhance_image(img)

            # Extract info for overlays
            title = product_data.get("title", "")[:40]
            product_type = product_data.get("product_type", "")
            keywords = f"#{product_type}" if product_type else "#Fashion"

            # Add text overlays
            img = self.add_text_overlay(img, title, cta="SHOP NOW", keywords=keywords, accent_color=accent)

            # Save optimized image
            output_path = Path(__file__).parent / ".pinterest_optimized_image.jpg"
            img.save(output_path, quality=95, optimize=True)

            logger.info(f"✓ Optimized image saved: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to optimize image: {e}")
            return None


def main():
    """Test image optimizer"""
    import os
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    # Test with a sample product
    optimizer = ImageOptimizer()

    sample_image_url = "https://cdn.shopify.com/s/files/1/0605/3992/8747/files/21227_2_2e4bed96-5e45-42e5-8f73-c33c10c02d00.jpg"
    sample_product = {
        "title": "3/4 Puff Slv Texture Vneck Button Down Midi Dress",
        "product_type": "Dress",
        "price": "$89.99",
    }

    output = optimizer.optimize_for_pinterest(sample_image_url, sample_product, accent_color="rose")
    if output:
        logger.info(f"✅ Optimization complete: {output}")
    else:
        logger.error("❌ Optimization failed")


if __name__ == "__main__":
    main()
