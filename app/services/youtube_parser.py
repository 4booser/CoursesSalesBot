import html
import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx


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


class YoutubeCourseParser:
    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    async def parse(self, text: str) -> ParsedYoutubeCourse:
        video_id = extract_youtube_video_id(text)
        if video_id is None:
            raise YoutubeParseError("YouTube link not found")

        url = canonical_youtube_url(video_id)
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 CoursesSalesBot/1.0"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        metadata = self._extract_metadata(response.text)
        title = metadata.get("title") or f"YouTube video {video_id}"
        description = metadata.get("description")
        thumbnail_url = metadata.get("thumbnail_url") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        return ParsedYoutubeCourse(
            video_id=video_id,
            url=url,
            title=title[:128],
            description=description[:2000] if description else None,
            thumbnail_url=thumbnail_url[:512] if thumbnail_url else None,
        )

    def _extract_metadata(self, page: str) -> dict[str, str | None]:
        player_response = self._extract_json_object(page, "ytInitialPlayerResponse")
        video_details = player_response.get("videoDetails", {}) if player_response else {}
        microformat = player_response.get("microformat", {}).get("playerMicroformatRenderer", {}) if player_response else {}

        title = video_details.get("title") or microformat.get("title", {}).get("simpleText")
        short_description = video_details.get("shortDescription") or microformat.get("description", {}).get("simpleText")
        thumbnail_url = self._extract_thumbnail(video_details) or self._extract_thumbnail(microformat)

        if not title:
            title = self._extract_meta(page, "og:title") or self._extract_title(page)
        if not short_description:
            short_description = self._extract_meta(page, "description") or self._extract_meta(page, "og:description")
        if not thumbnail_url:
            thumbnail_url = self._extract_meta(page, "og:image")

        return {
            "title": self._clean_text(title),
            "description": self._clean_text(short_description),
            "thumbnail_url": thumbnail_url,
        }

    def _extract_json_object(self, page: str, variable_name: str) -> dict | None:
        marker = f"{variable_name} = "
        start = page.find(marker)
        if start == -1:
            return None

        start = page.find("{", start)
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(page)):
            char = page[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(page[start : index + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def _extract_meta(self, page: str, name: str) -> str | None:
        patterns = [
            rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)["\']',
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, page, flags=re.IGNORECASE)
            if match:
                return html.unescape(match.group(1))
        return None

    def _extract_title(self, page: str) -> str | None:
        match = re.search(r"<title>(.*?)</title>", page, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        return html.unescape(re.sub(r"\s+", " ", match.group(1))).replace(" - YouTube", "").strip()

    def _extract_thumbnail(self, data: dict) -> str | None:
        thumbnails = data.get("thumbnail", {}).get("thumbnails", [])
        if not thumbnails:
            return None
        return thumbnails[-1].get("url")

    def _clean_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = html.unescape(value).strip()
        return cleaned or None
