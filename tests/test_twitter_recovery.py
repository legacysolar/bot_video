import base64
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
import jetbot_v2 as app


class CookieConfigurationTests(unittest.TestCase):
    def test_both_x_base64_variable_names_are_supported(self):
        payload = "# Netscape HTTP Cookie File\n"
        encoded = base64.b64encode(payload.encode()).decode()
        for key in ("COOKIES_X_B64", "COOKIES_TWITTER_B64"):
            with self.subTest(key=key), mock.patch.dict(os.environ, {key: encoded}, clear=True):
                self.assertEqual(app._cookie_payload("twitter"), payload)

    def test_plain_x_alias_is_supported(self):
        with mock.patch.dict(os.environ, {"COOKIES_X": "cookie-content"}, clear=True):
            self.assertEqual(app._cookie_payload("twitter"), "cookie-content")

    def test_invalid_base64_does_not_hide_valid_alias_or_log_values(self):
        payload = "# Netscape HTTP Cookie File\n"
        values = {
            "COOKIES_X_B64": "invalid-secret-%%%",
            "COOKIES_TWITTER_B64": base64.b64encode(payload.encode()).decode(),
        }
        with mock.patch.dict(os.environ, values, clear=True), mock.patch("builtins.print") as log:
            self.assertEqual(app._cookie_payload("twitter"), payload)
        self.assertNotIn("invalid-secret-%%%", str(log.call_args_list))

    def test_render_secret_file_is_copied_to_writable_temporary_jar(self):
        payload = "# Netscape HTTP Cookie File\n"
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "cookies_x.txt"
            source.write_text(payload)
            with mock.patch.dict(os.environ, {"COOKIES_X_FILE": str(source)}, clear=True):
                target = app._temporary_cookiefile("twitter")
            try:
                self.assertNotEqual(target, str(source))
                self.assertEqual(Path(target).read_text(), payload)
                app._safe_unlink(target)
                self.assertEqual(source.read_text(), payload)
            finally:
                app._safe_unlink(target)

    def test_default_render_secret_mount_is_checked(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(Path, "is_file", return_value=True) as exists, \
             mock.patch.object(Path, "read_text", return_value="cookie-content"):
            self.assertEqual(app._cookie_payload("twitter"), "cookie-content")
        self.assertTrue(exists.called)


class TwitterPublicRecoveryTests(unittest.TestCase):
    URL = "https://x.com/example/status/123/video/1?s=46"

    def setUp(self):
        self.opts = {
            "outtmpl": "/tmp/video.%(ext)s",
            "format": "best[ext=mp4]/best",
            "cookiefile": "/tmp/account.cookies.txt",
            "http_headers": {"User-Agent": "test", "Cookie": "secret-cookie"},
            "extractor_args": {"youtube": {"player_client": ["mweb"]}},
        }

    def downloaders(self, error, fallback_result=None, fallback_error=None):
        primary = mock.MagicMock()
        primary.extract_info.side_effect = error
        fallback = mock.MagicMock()
        fallback.extract_info.return_value = fallback_result
        fallback.extract_info.side_effect = fallback_error
        factory = mock.MagicMock(side_effect=[primary, fallback])
        primary.__enter__.return_value = primary
        fallback.__enter__.return_value = fallback
        return factory

    def test_login_failure_tries_public_endpoint_without_account_credentials(self):
        error = app.yt_dlp.utils.DownloadError("Login required. Use --cookies for authentication")
        expected = {"id": "123", "title": "public video"}
        factory = self.downloaders(error, fallback_result=expected)
        original = copy.deepcopy(self.opts)
        with mock.patch.object(app.yt_dlp, "YoutubeDL", factory):
            self.assertEqual(app._extract_general_media(self.URL, self.opts, "twitter"), expected)
        retry = factory.call_args_list[1].args[0]
        self.assertNotIn("cookiefile", retry)
        self.assertNotIn("Cookie", retry["http_headers"])
        self.assertEqual(retry["extractor_args"]["twitter"]["api"], ["syndication"])
        self.assertEqual(retry["format"], original["format"])
        self.assertEqual(retry["outtmpl"], original["outtmpl"])
        self.assertEqual(self.opts, original)

    def test_guest_token_failure_also_tries_public_endpoint(self):
        factory = self.downloaders(app.yt_dlp.utils.DownloadError("Could not retrieve guest token"), {"id": "123"})
        with mock.patch.object(app.yt_dlp, "YoutubeDL", factory):
            self.assertEqual(app._extract_general_media(self.URL, self.opts, "twitter")["id"], "123")
        self.assertEqual(factory.call_count, 2)

    def test_private_and_unrelated_errors_are_not_retried(self):
        for message in ("Private video requires login", "No space left on device"):
            error = app.yt_dlp.utils.DownloadError(message)
            factory = self.downloaders(error)
            with self.subTest(message=message), mock.patch.object(app.yt_dlp, "YoutubeDL", factory):
                with self.assertRaises(app.yt_dlp.utils.DownloadError):
                    app._extract_general_media(self.URL, self.opts, "twitter")
            self.assertEqual(factory.call_count, 1)

    def test_other_platforms_are_not_retried_with_x_endpoint(self):
        factory = self.downloaders(app.yt_dlp.utils.DownloadError("Login required"))
        with mock.patch.object(app.yt_dlp, "YoutubeDL", factory):
            with self.assertRaises(app.yt_dlp.utils.DownloadError):
                app._extract_general_media("https://instagram.com/reel/test", self.opts, "instagram")
        self.assertEqual(factory.call_count, 1)

    def test_public_failure_preserves_original_actionable_error(self):
        error = app.yt_dlp.utils.DownloadError("Login required")
        factory = self.downloaders(error, fallback_error=app.yt_dlp.utils.DownloadError("empty JSON"))
        with mock.patch.object(app.yt_dlp, "YoutubeDL", factory):
            with self.assertRaises(app.yt_dlp.utils.DownloadError) as caught:
                app._extract_general_media(self.URL, self.opts, "twitter")
        self.assertIs(caught.exception, error)


if __name__ == "__main__":
    unittest.main()
