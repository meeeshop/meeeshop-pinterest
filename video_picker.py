"""
video_picker.py — Intelligent video selection from multiple sources
Sources: meeeshop-youtube repo + YouTube channel + local videos
Uses AI keys from meeeshop-youtube/.env for content analysis
"""

import os
import json
import logging
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)


class EnvLoader:
    """Load environment variables from meeeshop-youtube/.env"""

    @staticmethod
    def load_youtube_env() -> Dict[str, str]:
        """Load .env from meeeshop-youtube repo"""
        youtube_repo = Path(__file__).parent.parent / "meeeshop-youtube"
        env_file = youtube_repo / ".env"

        env_vars = {}

        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"')
                    if k and v:
                        env_vars[k] = v
                        # Also set in os.environ for other modules
                        os.environ.setdefault(k, v)

            logger.info(f"✓ Loaded {len(env_vars)} vars from meeeshop-youtube/.env")
            return env_vars

        logger.warning("meeeshop-youtube/.env not found")
        return {}

    @staticmethod
    def get_api_keys() -> Dict[str, str]:
        """Get AI API keys from meeeshop-youtube/.env"""
        env_vars = EnvLoader.load_youtube_env()
        return {
            "GEMINI_API_KEY": env_vars.get("GEMINI_API_KEY", ""),
            "GROQ_API_KEY": env_vars.get("GROQ_API_KEY", ""),
            "OPENROUTER_API_KEY": env_vars.get("OPENROUTER_API_KEY", ""),
            "YOUTUBE_CLIENT_ID": env_vars.get("YOUTUBE_CLIENT_ID", ""),
            "YOUTUBE_CLIENT_SECRET": env_vars.get("YOUTUBE_CLIENT_SECRET", ""),
            "YOUTUBE_REFRESH_TOKEN": env_vars.get("YOUTUBE_REFRESH_TOKEN", ""),
        }


class LocalVideoPicker:
    """Pick videos from meeeshop-youtube repo"""

    SEARCH_PATHS = [
        "videos",
        "output",
        "shorts",
        "generated",
        "rendered",
        "exports",
    ]

    @staticmethod
    def find_videos() -> List[Dict[str, Any]]:
        """Find all videos in meeeshop-youtube repo"""
        youtube_repo = Path(__file__).parent.parent / "meeeshop-youtube"

        if not youtube_repo.exists():
            logger.warning(f"meeeshop-youtube repo not found at {youtube_repo}")
            return []

        videos = []

        # Search in common directories
        for subdir in LocalVideoPicker.SEARCH_PATHS:
            video_dir = youtube_repo / subdir
            if video_dir.exists():
                for video_file in video_dir.glob("*"):
                    if video_file.is_file() and video_file.suffix.lower() in [
                        ".mp4",
                        ".webm",
                        ".mov",
                        ".avi",
                        ".mkv",
                    ]:
                        videos.append({
                            "type": "local",
                            "path": str(video_file),
                            "filename": video_file.name,
                            "size": video_file.stat().st_size,
                            "modified": video_file.stat().st_mtime,
                            "directory": subdir,
                        })

        logger.info(f"Found {len(videos)} local videos in meeeshop-youtube")
        return sorted(videos, key=lambda x: x["modified"], reverse=True)

    @staticmethod
    def pick_random_video() -> Optional[Dict[str, Any]]:
        """Pick random video from local repo"""
        videos = LocalVideoPicker.find_videos()
        if videos:
            video = random.choice(videos)
            logger.info(f"Selected video: {video['filename']}")
            return video
        logger.warning("No local videos found")
        return None

    @staticmethod
    def pick_latest_videos(limit: int = 5) -> List[Dict[str, Any]]:
        """Pick latest N videos (for scheduling multiple posts)"""
        videos = LocalVideoPicker.find_videos()
        return videos[:limit]


class YouTubeChannelPicker:
    """Pick videos from YouTube channel"""

    def __init__(self, channel_id: str, api_key: str):
        self.channel_id = channel_id
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"

    def get_latest_videos(self, max_results: int = 10, days_old: int = 30) -> List[Dict[str, Any]]:
        """Get latest videos from channel"""
        try:
            # First get uploads playlist ID
            channel_url = f"{self.base_url}/channels"
            channel_params = {
                "part": "contentDetails",
                "id": self.channel_id,
                "key": self.api_key,
            }

            resp = requests.get(channel_url, params=channel_params, timeout=10)
            resp.raise_for_status()

            upload_playlist_id = resp.json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

            # Get videos from uploads playlist
            playlist_url = f"{self.base_url}/playlistItems"
            playlist_params = {
                "part": "snippet",
                "playlistId": upload_playlist_id,
                "maxResults": min(max_results, 50),
                "key": self.api_key,
            }

            resp = requests.get(playlist_url, params=playlist_params, timeout=10)
            resp.raise_for_status()

            videos = []
            cutoff_date = datetime.now() - timedelta(days=days_old)

            for item in resp.json().get("items", []):
                snippet = item["snippet"]
                published = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))

                if published.replace(tzinfo=None) > cutoff_date:
                    videos.append({
                        "type": "youtube",
                        "video_id": snippet["resourceId"]["videoId"],
                        "title": snippet["title"],
                        "description": snippet["description"],
                        "thumbnail": snippet["thumbnails"]["high"]["url"],
                        "published_at": snippet["publishedAt"],
                        "url": f"https://www.youtube.com/watch?v={snippet['resourceId']['videoId']}",
                    })

            logger.info(f"Found {len(videos)} YouTube videos from last {days_old} days")
            return videos

        except Exception as e:
            logger.error(f"Failed to fetch YouTube videos: {e}")
            return []

    @staticmethod
    def pick_random_from_channel(channel_id: str, api_key: str) -> Optional[Dict[str, Any]]:
        """Pick random video from YouTube channel"""
        picker = YouTubeChannelPicker(channel_id, api_key)
        videos = picker.get_latest_videos(max_results=20)
        if videos:
            video = random.choice(videos)
            logger.info(f"Selected YouTube video: {video['title']}")
            return video
        return None


class VideoPicker:
    """Main video picker - tries multiple sources"""

    def __init__(self, use_youtube: bool = True):
        self.use_youtube = use_youtube
        self.api_keys = EnvLoader.load_youtube_env()

    def pick_video(self) -> Optional[Dict[str, Any]]:
        """
        Pick video in order of preference:
        1. Local repo (most recent)
        2. YouTube channel (if enabled)
        3. Random local video
        """
        # Try local repo first (fastest, no API calls)
        logger.info("Checking for videos in meeeshop-youtube repo...")
        local_video = LocalVideoPicker.pick_random_video()
        if local_video:
            return local_video

        # Try YouTube channel (if enabled and credentials available)
        if self.use_youtube:
            logger.info("Checking YouTube channel...")
            channel_id = self._get_channel_id()
            api_key = self.api_keys.get("GEMINI_API_KEY") or self.api_keys.get("OPENROUTER_API_KEY")

            if channel_id and api_key:
                try:
                    yt_video = YouTubeChannelPicker.pick_random_from_channel(channel_id, api_key)
                    if yt_video:
                        return yt_video
                except Exception as e:
                    logger.warning(f"YouTube fetch failed: {e}")

        logger.warning("No videos found from any source")
        return None

    def pick_videos_for_week(self, count: int = 7) -> List[Dict[str, Any]]:
        """Pick multiple videos for weekly scheduling"""
        videos = []

        # Get local videos
        local_videos = LocalVideoPicker.pick_latest_videos(limit=count)
        videos.extend(local_videos)

        # If not enough, try YouTube
        if len(videos) < count and self.use_youtube:
            channel_id = self._get_channel_id()
            api_key = self.api_keys.get("GEMINI_API_KEY")

            if channel_id and api_key:
                try:
                    yt_picker = YouTubeChannelPicker(channel_id, api_key)
                    yt_videos = yt_picker.get_latest_videos(max_results=count - len(videos))
                    videos.extend(yt_videos)
                except Exception:
                    pass

        logger.info(f"Selected {len(videos)} videos for scheduling")
        return videos[:count]

    def _get_channel_id(self) -> Optional[str]:
        """Extract channel ID from meeeshop-youtube or use default"""
        # Could be stored in YouTube repo or in env
        channel_id = self.api_keys.get("YOUTUBE_CHANNEL_ID")
        if channel_id:
            return channel_id

        # Try to extract from YouTube metadata
        youtube_repo = Path(__file__).parent.parent / "meeeshop-youtube"
        metadata_file = youtube_repo / "metadata.json"

        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                return metadata.get("channel_id")
            except Exception:
                pass

        logger.warning("Could not determine YouTube channel ID")
        return None

    def get_video_info(self, video: Dict[str, Any]) -> Dict[str, Any]:
        """Get standardized info about video"""
        if video["type"] == "local":
            return {
                "source": "local",
                "path": video["path"],
                "title": video["filename"],
                "is_downloadable": True,
            }
        else:  # youtube
            return {
                "source": "youtube",
                "url": video["url"],
                "title": video["title"],
                "thumbnail": video["thumbnail"],
                "is_downloadable": False,  # Need to download first
            }


def main():
    """Test video picker"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n🎬 Video Picker — Multi-Source\n")

    picker = VideoPicker(use_youtube=True)

    # Find local videos
    print("📁 Local Videos:")
    local_videos = LocalVideoPicker.find_videos()
    for v in local_videos[:3]:
        print(f"  • {v['filename']} ({v['directory']}/)")

    # Pick single video
    print("\n🎯 Random Video Selection:")
    video = picker.pick_video()
    if video:
        info = picker.get_video_info(video)
        print(f"  Source: {info['source']}")
        print(f"  Title: {info['title']}")
        if "path" in info:
            print(f"  Path: {info['path']}")
        if "url" in info:
            print(f"  URL: {info['url']}")

    # Pick week of videos
    print("\n📅 Weekly Schedule:")
    weekly = picker.pick_videos_for_week(count=3)
    for i, v in enumerate(weekly, 1):
        info = picker.get_video_info(v)
        print(f"  Day {i}: {info['title']} ({info['source']})")

    # Show API keys loaded
    print("\n🔑 Loaded API Keys:")
    keys = EnvLoader.get_api_keys()
    for key, value in keys.items():
        if value:
            masked = value[:20] + "..." if len(value) > 20 else value
            print(f"  ✓ {key}: {masked}")
        else:
            print(f"  ✗ {key}: (not set)")


if __name__ == "__main__":
    main()
