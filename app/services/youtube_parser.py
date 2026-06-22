import asyncio
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


@dataclass(frozen=True)
class ParsedYoutubeCourse:
    video_id: str
    url: str
    title: str
    description: str | None
    thumbnail_url: str | None


def extract_youtube_video_id(text: str) -> str | None:
    for raw_url in re.findall(r"https?://[^\s<>()]+", text):
        url = raw_url.rstrip(".,;!?)\"]}")
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host not in YOUTUBE_HOSTS:
            continue

        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
        elif parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
            video_id = parsed.path.strip("/").split("/")[1]
        else:
            continue

        if re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
            return video_id

    return None


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


class YoutubeParseError(Exception):
    pass


class YoutubeLinkNotFoundError(YoutubeParseError):
    pass


class YoutubeCourseParser:
    """Extracts YouTube course metadata through yt-dlp.

    This works for public and unlisted videos that are available by URL. Truly private
    videos require a valid YouTube cookies file from an account that has access.
    """

    def __init__(self, cookies_file: str | None = None):
        self.cookies_file = cookies_file

    async def parse(self, text: str) -> ParsedYoutubeCourse:
        video_id = extract_youtube_video_id(text)
        if video_id is None:
            raise YoutubeLinkNotFoundError("YouTube link not found")

        url = canonical_youtube_url(video_id)
        info = await asyncio.to_thread(self._extract_info, url)
        title = self._clean_text(info.get("title"))
        if not title:
            raise YoutubeParseError("YouTube title not found")

        description = self._clean_text(info.get("description"))
        thumbnail_url = self._select_thumbnail(info)

        return ParsedYoutubeCourse(
            video_id=video_id,
            url=info.get("webpage_url") or url,
            title=title[:128],
            description=description[:2000] if description else None,
            thumbnail_url=thumbnail_url[:512] if thumbnail_url else None,
        )

    def _extract_info(self, url: str) -> dict:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
            "noplaylist": True,
        }
        if self.cookies_file:
            options["cookiefile"] = self.cookies_file

        try:
            with YoutubeDL(options) as youtube_dl:
                return youtube_dl.extract_info(url, download=False)
        except DownloadError as error:
            raise YoutubeParseError(str(error)) from error

    def _select_thumbnail(self, info: dict) -> str | None:
        thumbnails = info.get("thumbnails") or []
        if thumbnails:
            sorted_thumbnails = sorted(
                thumbnails,
                key=lambda item: (item.get("width") or 0) * (item.get("height") or 0),
            )
            url = sorted_thumbnails[-1].get("url")
            if url:
                return url

        return info.get("thumbnail")

    def _clean_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
