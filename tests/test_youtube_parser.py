import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.youtube_parser import YoutubeCourseParser, extract_youtube_video_id


def test_extract_youtube_video_id_supported_urls() -> None:
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_parse_uses_ytdlp_metadata() -> None:
    parser = YoutubeCourseParser()

    def fake_extract_info(url: str) -> dict:
        assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        return {
            "webpage_url": url,
            "title": "Course title",
            "description": "Course description",
            "thumbnails": [
                {"url": "https://example.com/small.jpg", "width": 120, "height": 90},
                {"url": "https://example.com/large.jpg", "width": 1280, "height": 720},
            ],
        }

    parser._extract_info = fake_extract_info  # type: ignore[method-assign]

    parsed = asyncio.run(parser.parse("https://youtu.be/dQw4w9WgXcQ"))

    assert parsed.video_id == "dQw4w9WgXcQ"
    assert parsed.title == "Course title"
    assert parsed.description == "Course description"
    assert parsed.thumbnail_url == "https://example.com/large.jpg"
