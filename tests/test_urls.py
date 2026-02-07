"""Unit tests for scraper/urls.py URL utility functions."""

import pytest

from api.urls import (
    ASSET_EXTENSIONS,
    clean_url,
    is_asset_url,
    normalize_path,
    normalize_url,
)


class TestIsAssetUrl:
    """Tests for is_asset_url function."""

    def test_pdf_files(self):
        assert is_asset_url("https://docs.example.com/guide.pdf") is True
        assert is_asset_url("https://example.com/path/to/document.PDF") is True

    def test_image_files(self):
        assert is_asset_url("https://example.com/logo.png") is True
        assert is_asset_url("https://example.com/banner.jpg") is True
        assert is_asset_url("https://example.com/icon.svg") is True
        assert is_asset_url("https://example.com/photo.JPEG") is True

    def test_archive_files(self):
        assert is_asset_url("https://example.com/release.zip") is True
        assert is_asset_url("https://example.com/data.tar.gz") is True
        assert is_asset_url("https://example.com/backup.7z") is True

    def test_media_files(self):
        assert is_asset_url("https://example.com/video.mp4") is True
        assert is_asset_url("https://example.com/audio.mp3") is True

    def test_feed_files(self):
        assert is_asset_url("https://example.com/feed.xml") is True
        assert is_asset_url("https://example.com/rss.rss") is True

    def test_regular_doc_urls(self):
        assert is_asset_url("https://docs.example.com/getting-started") is False
        assert is_asset_url("https://docs.example.com/api/v1/users") is False
        assert is_asset_url("https://example.com/") is False

    def test_html_urls(self):
        assert is_asset_url("https://example.com/page.html") is False
        assert is_asset_url("https://example.com/index.htm") is False

    def test_url_encoded_paths(self):
        assert is_asset_url("https://example.com/path%2Fto%2Ffile.pdf") is True
        assert is_asset_url("https://example.com/my%20document.pdf") is True

    def test_url_with_query_params(self):
        # Extension detection should work with query params
        assert is_asset_url("https://example.com/file.pdf?v=1") is True
        assert is_asset_url("https://example.com/page?format=pdf") is False

    def test_web_asset_files(self):
        assert is_asset_url("https://example.com/styles.css") is True
        assert is_asset_url("https://example.com/_astro/ec.4c0k7.css") is True
        assert is_asset_url("https://example.com/app.js") is True
        assert is_asset_url("https://example.com/font.woff2") is True
        assert is_asset_url("https://example.com/bundle.js.map") is True

    def test_all_extensions_covered(self):
        """Verify the extension set is comprehensive."""
        expected_extensions = {
            ".pdf", ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z",
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
            ".mp4", ".mp3", ".wav", ".webm", ".mov",
            ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".exe", ".dmg", ".pkg", ".deb", ".rpm",
            ".xml", ".rss", ".atom",
            ".css", ".js", ".mjs", ".ts", ".jsx", ".tsx",
            ".woff", ".woff2", ".ttf", ".otf", ".eot",
            ".map",
        }
        assert ASSET_EXTENSIONS == expected_extensions


class TestCleanUrl:
    """Tests for clean_url function."""

    def test_removes_query_params(self):
        assert clean_url("https://example.com/page?foo=bar") == "https://example.com/page"
        assert clean_url("https://example.com/page?a=1&b=2") == "https://example.com/page"

    def test_removes_fragments(self):
        assert clean_url("https://example.com/page#section") == "https://example.com/page"
        assert clean_url("https://example.com/page#") == "https://example.com/page"

    def test_removes_both_query_and_fragment(self):
        assert clean_url("https://example.com/page?foo=bar#section") == "https://example.com/page"

    def test_removes_trailing_slash(self):
        assert clean_url("https://example.com/page/") == "https://example.com/page"
        assert clean_url("https://example.com/") == "https://example.com"

    def test_clean_url_unchanged(self):
        assert clean_url("https://example.com/page") == "https://example.com/page"


class TestNormalizeUrl:
    """Tests for normalize_url function."""

    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTPS://EXAMPLE.COM/Path") == "https://example.com/Path"
        assert normalize_url("HTTP://Example.Com/page") == "http://example.com/page"

    def test_removes_query_and_fragment(self):
        assert normalize_url("https://example.com/page?foo=bar#section") == "https://example.com/page"

    def test_collapses_duplicate_slashes(self):
        assert normalize_url("https://example.com//page///sub") == "https://example.com/page/sub"

    def test_removes_trailing_slash(self):
        assert normalize_url("https://example.com/page/") == "https://example.com/page"
        assert normalize_url("https://example.com/") == "https://example.com"

    def test_handles_root_url(self):
        assert normalize_url("https://example.com") == "https://example.com"
        assert normalize_url("https://example.com/") == "https://example.com"

    def test_preserves_path_case(self):
        # Path case should be preserved (URLs are case-sensitive in path)
        assert normalize_url("https://example.com/API/v1") == "https://example.com/API/v1"

    def test_strips_whitespace(self):
        assert normalize_url("  https://example.com/page  ") == "https://example.com/page"

    def test_defaults_to_https(self):
        # URLs without scheme should default to https
        assert normalize_url("//example.com/page") == "https://example.com/page"


class TestNormalizePath:
    """Tests for normalize_path function."""

    def test_empty_path(self):
        assert normalize_path("") == ""
        assert normalize_path(None) == ""  # type: ignore

    def test_root_path(self):
        assert normalize_path("/") == ""

    def test_adds_leading_slash(self):
        assert normalize_path("page") == "/page"
        assert normalize_path("api/v1") == "/api/v1"

    def test_removes_trailing_slash(self):
        assert normalize_path("/page/") == "/page"
        assert normalize_path("/api/v1/") == "/api/v1"

    def test_collapses_duplicate_slashes(self):
        assert normalize_path("//page") == "/page"
        assert normalize_path("/page//sub") == "/page/sub"
        assert normalize_path("///api///v1///") == "/api/v1"

    def test_normal_path_unchanged(self):
        assert normalize_path("/page") == "/page"
        assert normalize_path("/api/v1/users") == "/api/v1/users"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
