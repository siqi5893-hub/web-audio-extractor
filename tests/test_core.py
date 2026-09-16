import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_audio_extractor.core import (
    AudioExtractor,
    UrlPolicy,
    parse_172mix_page,
)


class UrlPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = UrlPolicy(resolver=lambda _host: {"93.184.216.34"})

    def test_accepts_arbitrary_public_https_sites(self):
        self.assertEqual(
            self.policy.validate("https://m.172mix.com/play/217861"),
            "https://m.172mix.com/play/217861",
        )
        self.assertEqual(
            self.policy.validate("https://media.example.org/watch/42"),
            "https://media.example.org/watch/42",
        )

    def test_rejects_ip_credentials_ports_and_http(self):
        for url in (
            "https://127.0.0.1/audio.mp3",
            "https://user:pass@172mix.com/play/1",
            "https://172mix.com:8443/play/1",
            "http://m.172mix.com/play/1",
        ):
            with self.assertRaises(ValueError):
                self.policy.validate(url)

    def test_rejects_hostnames_resolving_to_private_or_reserved_addresses(self):
        policy = UrlPolicy(resolver=lambda _host: {"192.168.2.1", "93.184.216.34"})
        with self.assertRaises(ValueError):
            policy.validate("https://media.example.org/watch/42")

    def test_optional_allowlist_still_uses_domain_boundaries(self):
        policy = UrlPolicy({"example.org"}, resolver=lambda _host: {"93.184.216.34"})
        self.assertEqual(
            policy.validate("https://cdn.example.org/audio"),
            "https://cdn.example.org/audio",
        )
        with self.assertRaises(ValueError):
            policy.validate("https://example.org.evil.test/audio")


class ParserTests(unittest.TestCase):
    def test_parses_172mix_title_and_media_source(self):
        html = '''
        <title>友哥 - 蓝雨试听,mp3下载 - 172Mix</title>
        <script>var media = {src: "https://mp3.172mix.com/music/test.m4a"}</script>
        '''
        info = parse_172mix_page(html)
        self.assertEqual(info.source_url, "https://mp3.172mix.com/music/test.m4a")
        self.assertEqual(info.title, "友哥 - 蓝雨")

    def test_rejects_page_without_embedded_audio(self):
        with self.assertRaises(ValueError):
            parse_172mix_page("<html><title>nothing</title></html>")


class ExtractorTests(unittest.TestCase):
    def test_generic_command_uses_argument_array_and_mp3_output(self):
        with tempfile.TemporaryDirectory() as directory:
            extractor = AudioExtractor(
                Path(directory), resolver=lambda _host: {"93.184.216.34"}
            )
            command = extractor.build_ytdlp_command(
                "https://videos.example.org/watch/123"
            )
        self.assertEqual(command[0], "yt-dlp")
        self.assertIn("--extract-audio", command)
        self.assertIn("mp3", command)
        self.assertEqual(command[-1], "https://videos.example.org/watch/123")

    @patch("web_audio_extractor.core.subprocess.run")
    @patch("web_audio_extractor.core.shutil.which", return_value="/usr/bin/yt-dlp")
    def test_generic_extraction_returns_new_mp3(self, _which, run):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            def create_file(*_args, **_kwargs):
                (output / "audio_123.mp3").write_bytes(b"mp3")

            run.side_effect = create_file
            extractor = AudioExtractor(
                output, resolver=lambda _host: {"93.184.216.34"}
            )
            result = extractor.extract("https://videos.example.org/watch/123")

        self.assertEqual(result.name, "audio_123.mp3")
        self.assertNotIn("shell", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
