"""
youtube_video_downloader.py — Download YouTube videos for Pinterest posting
Uses yt-dlp for reliable video downloads with automatic format selection
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class YouTubeVideoDownloader:
    """Download YouTube videos for Pinterest (max 15 mins, <50MB)"""

    DOWNLOAD_DIR = Path(__file__).parent / ".youtube_downloads"
    MAX_VIDEO_LENGTH = 900  # 15 minutes in seconds
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

    def __init__(self):
        self.DOWNLOAD_DIR.mkdir(exist_ok=True)

    def download_video(self, youtube_url: str) -> Optional[Path]:
        """Download YouTube video optimized for Pinterest"""
        try:
            logger.info(f"📥 Downloading YouTube video: {youtube_url}")

            # Output template
            output_file = self.DOWNLOAD_DIR / "%(title)s.%(ext)s"

            # yt-dlp command: download best format <50MB, <15min
            cmd = [
                "yt-dlp",
                "-f", "best[filesize<50M]",  # Best quality under 50MB
                "-S", "duration:short",  # Prefer shorter videos
                "--max-downloads", "1",
                "-o", str(output_file),
                youtube_url,
            ]

            # Check if video is under 15 minutes
            info_cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                youtube_url,
            ]

            try:
                import json
                result = subprocess.run(
                    info_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    duration = info.get("duration", 0)
                    if duration > self.MAX_VIDEO_LENGTH:
                        logger.warning(f"⚠ Video is {duration}s, exceeds 15min limit")
                        return None
                    logger.info(f"✓ Video duration: {duration}s (OK for Pinterest)")
            except Exception as e:
                logger.warning(f"Could not check video duration: {e}")

            # Download video
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                # Find downloaded file
                downloaded_files = list(self.DOWNLOAD_DIR.glob("*"))
                if downloaded_files:
                    latest_file = max(downloaded_files, key=lambda p: p.stat().st_mtime)
                    logger.info(f"✓ Video downloaded: {latest_file}")
                    logger.info(f"  Size: {latest_file.stat().st_size / 1024 / 1024:.1f}MB")
                    return latest_file
            else:
                logger.error(f"Download failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Failed to download video: {e}")
            return None

    def cleanup_old_downloads(self, keep_recent: int = 3):
        """Remove old downloaded videos to save space"""
        try:
            files = sorted(
                self.DOWNLOAD_DIR.glob("*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            for old_file in files[keep_recent:]:
                old_file.unlink()
                logger.info(f"Cleaned up: {old_file.name}")
        except Exception as e:
            logger.warning(f"Could not cleanup old downloads: {e}")


def main():
    """Test YouTube downloader"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    downloader = YouTubeVideoDownloader()

    # Test URL
    test_url = "https://www.youtube.com/watch?v=BNoc_sfDpb0"

    video_path = downloader.download_video(test_url)
    if video_path:
        logger.info(f"✅ Download successful: {video_path}")
    else:
        logger.error("❌ Download failed")


if __name__ == "__main__":
    main()
