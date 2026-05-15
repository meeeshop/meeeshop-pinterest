"""
Pinterest OAuth 2.0 client using the official v5 API.
Uses refresh_token for long-lived access — no cookies, no session scraping.
"""

import base64
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PINTEREST_API_BASE = "https://api.pinterest.com/v5"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"


class PinterestOAuthClient:
    """Thin Pinterest v5 API client using OAuth 2.0 refresh token flow."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ):
        self.client_id = client_id or os.environ["PINTEREST_CLIENT_ID"]
        self.client_secret = client_secret or os.environ["PINTEREST_CLIENT_SECRET"]
        self.refresh_token = refresh_token or os.environ["PINTEREST_REFRESH_TOKEN"]
        self._access_token: Optional[str] = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _basic_auth_header(self) -> str:
        creds = f"{self.client_id}:{self.client_secret}"
        return "Basic " + base64.b64encode(creds.encode()).decode()

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._access_token:
            return self._access_token
        self._access_token = self._refresh_access_token()
        return self._access_token

    def _refresh_access_token(self) -> str:
        resp = requests.post(
            TOKEN_URL,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "scope": "boards:read boards:write pins:read pins:write user_accounts:read",
            },
            timeout=15,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        logger.info("Pinterest access token refreshed via OAuth")
        return token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_access_token()}"}

    # ------------------------------------------------------------------
    # Boards
    # ------------------------------------------------------------------

    def get_boards(self) -> list:
        """Return list of {id, name} for all user boards."""
        boards = []
        bookmark = None
        while True:
            params = {"page_size": 25}
            if bookmark:
                params["bookmark"] = bookmark
            resp = requests.get(
                f"{PINTEREST_API_BASE}/boards",
                headers=self._auth_headers(),
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("items", []):
                boards.append({"id": item["id"], "name": item["name"]})
            bookmark = data.get("bookmark")
            if not bookmark:
                break
        logger.info(f"Fetched {len(boards)} Pinterest boards")
        return boards

    # ------------------------------------------------------------------
    # Video upload (Postiz-pattern: register → upload → poll → pin)
    # ------------------------------------------------------------------

    def upload_video(self, mp4_path: str, max_poll_secs: int = 300) -> Optional[str]:
        """
        Upload an MP4 to Pinterest media storage.
        Returns media_id on success, None on failure.
        Mirrors the flow in Postiz pinterest.provider.ts lines 188-256.
        """
        from pathlib import Path

        headers_json = {**self._auth_headers(), "Content-Type": "application/json"}

        # Step 1: Register upload
        try:
            resp = requests.post(
                f"{PINTEREST_API_BASE}/media",
                json={"media_type": "video"},
                headers=headers_json,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            media_id = data["media_id"]
            upload_url = data["upload_url"]
            upload_parameters = data.get("upload_parameters", {})
            logger.info(f"Pinterest media registered — media_id: {media_id}")
        except Exception as e:
            logger.error(f"Pinterest media register failed: {e}")
            return None

        # Step 2: Upload bytes (S3 multipart or PUT)
        try:
            video_bytes = Path(mp4_path).read_bytes()
            if upload_parameters:
                files = {k: (None, v) for k, v in upload_parameters.items()}
                files["file"] = ("video.mp4", video_bytes, "video/mp4")
                upload_resp = requests.post(upload_url, files=files, timeout=300)
            else:
                upload_resp = requests.put(
                    upload_url,
                    data=video_bytes,
                    headers={"Content-Type": "video/mp4"},
                    timeout=300,
                )
            if upload_resp.status_code not in (200, 204):
                logger.error(f"Video upload HTTP {upload_resp.status_code}: {upload_resp.text[:200]}")
                return None
            logger.info("Video bytes uploaded successfully")
        except Exception as e:
            logger.error(f"Video upload error: {e}")
            return None

        # Step 3: Poll for processing (Postiz polls every 30s)
        poll_interval = 30
        max_attempts = max_poll_secs // poll_interval
        for attempt in range(max_attempts):
            time.sleep(poll_interval)
            try:
                poll_resp = requests.get(
                    f"{PINTEREST_API_BASE}/media/{media_id}",
                    headers=self._auth_headers(),
                    timeout=10,
                )
                poll_resp.raise_for_status()
                status = poll_resp.json().get("status", "")
                logger.info(f"Video processing: {status} (attempt {attempt + 1}/{max_attempts})")
                if status == "succeeded":
                    return media_id
                if status == "failed":
                    logger.error("Pinterest video processing failed")
                    return None
            except Exception as e:
                logger.warning(f"Poll error: {e}")

        logger.error(f"Video processing timed out after {max_poll_secs}s")
        return None

    # ------------------------------------------------------------------
    # Pin creation
    # ------------------------------------------------------------------

    def create_video_pin(
        self,
        board_id: str,
        media_id: str,
        cover_image_url: str,
        title: str,
        description: str,
        link: str,
        alt_text: str = "",
    ) -> Optional[str]:
        """Create a video pin. cover_image_url is required by Pinterest v5 API."""
        payload = {
            "board_id": board_id,
            "title": title[:100],
            "description": description[:500],
            "link": link,
            "media_source": {
                "source_type": "video_id",
                "media_id": media_id,
                "cover_image_url": cover_image_url,
            },
        }
        if alt_text:
            payload["alt_text"] = alt_text[:500]

        try:
            resp = requests.post(
                f"{PINTEREST_API_BASE}/pins",
                json=payload,
                headers={**self._auth_headers(), "Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            pin_id = resp.json().get("id")
            logger.info(f"Video pin created — pin_id: {pin_id}")
            return pin_id
        except Exception as e:
            body = getattr(getattr(e, "response", None), "text", "")[:300]
            logger.error(f"Failed to create video pin: {e} — {body}")
            return None
