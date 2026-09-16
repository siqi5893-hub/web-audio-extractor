from __future__ import annotations

import html as html_module
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_DOMAINS: set[str] = set()


def resolve_addresses(host: str) -> set[str]:
    return {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}


class UrlPolicy:
    def __init__(self, allowed_domains: set[str] | None = None, resolver=resolve_addresses):
        self.allowed_domains = {
            item.lower().strip(". ") for item in (allowed_domains or set()) if item
        }
        self.resolver = resolver

    def validate(self, raw_url: str) -> str:
        url = raw_url.strip()
        if not url or len(url) > 2048:
            raise ValueError("链接为空或过长")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError("仅支持不含账号信息的 HTTPS 链接")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or self._looks_like_ip(host):
            raise ValueError("不接受 IP 地址链接")
        if parsed.port not in (None, 443):
            raise ValueError("不接受自定义端口")
        if self.allowed_domains and not any(
            host == domain or host.endswith("." + domain) for domain in self.allowed_domains
        ):
            raise ValueError("该域名不在允许列表中")
        try:
            addresses = self.resolver(host)
        except OSError as exc:
            raise ValueError("域名解析失败") from exc
        if not addresses or any(not ipaddress.ip_address(item).is_global for item in addresses):
            raise ValueError("域名解析到了非公网地址")
        return url

    @staticmethod
    def _looks_like_ip(host: str) -> bool:
        if ":" in host:
            return True
        return bool(re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host))


@dataclass(frozen=True)
class EmbeddedAudio:
    source_url: str
    title: str


def parse_172mix_page(page: str) -> EmbeddedAudio:
    source = re.search(r'\bsrc\s*:\s*["\'](https://mp3\.172mix\.com/[^"\']+)["\']', page)
    if not source:
        raise ValueError("页面中没有找到可播放音源")
    title_match = re.search(r"<title>(.*?)</title>", page, flags=re.I | re.S)
    title = html_module.unescape(title_match.group(1)).strip() if title_match else "172Mix音频"
    title = re.sub(r"试听,?mp3下载.*$", "", title, flags=re.I).strip(" -")
    return EmbeddedAudio(source.group(1), title or "172Mix音频")


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff .()\[\]-]+", "_", value, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return (cleaned[:120] or "audio") + ".mp3"


class AudioExtractor:
    def __init__(
        self,
        output_dir: Path | str,
        allowed_domains: set[str] | None = None,
        cookies: Path | str | None = None,
        yt_dlp: str = "yt-dlp",
        ffmpeg: str = "ffmpeg",
        timeout: int = 900,
        resolver=resolve_addresses,
    ):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.policy = UrlPolicy(allowed_domains, resolver=resolver)
        self.cookies = Path(cookies).resolve() if cookies else None
        self.yt_dlp = yt_dlp
        self.ffmpeg = ffmpeg
        self.timeout = timeout

    def build_ytdlp_command(self, raw_url: str, cookie_path: Path | None = None) -> list[str]:
        url = self.policy.validate(raw_url)
        command = [
            self.yt_dlp,
            "--no-playlist",
            "--no-progress",
            "--restrict-filenames",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--output",
            str(self.output_dir / "audio_%(id)s.%(ext)s"),
        ]
        selected_cookie = cookie_path or self.cookies
        if selected_cookie:
            if not selected_cookie.is_file():
                raise ValueError("Cookie 文件不存在")
            command.extend(["--cookies", str(selected_cookie)])
        command.append(url)
        return command

    def extract(self, raw_url: str) -> Path:
        url = self.policy.validate(raw_url)
        host = (urlsplit(url).hostname or "").lower()
        if host == "172mix.com" or host.endswith(".172mix.com"):
            return self._extract_172mix(url)
        return self._extract_ytdlp(url)

    def _extract_ytdlp(self, url: str) -> Path:
        if not shutil.which(self.yt_dlp) and not Path(self.yt_dlp).is_file():
            raise RuntimeError("找不到 yt-dlp")
        before = set(self.output_dir.glob("*.mp3"))
        runtime_cookie = None
        try:
            if self.cookies:
                if not self.cookies.is_file():
                    raise ValueError("Cookie 文件不存在")
                with tempfile.NamedTemporaryFile(
                    prefix=".audio-cookies-", suffix=".txt", dir=self.output_dir, delete=False
                ) as temporary:
                    runtime_cookie = Path(temporary.name)
                shutil.copyfile(self.cookies, runtime_cookie)
                runtime_cookie.chmod(0o600)
            subprocess.run(
                self.build_ytdlp_command(url, runtime_cookie),
                check=True,
                timeout=self.timeout,
                cwd=self.output_dir,
                stdin=subprocess.DEVNULL,
            )
        finally:
            if runtime_cookie:
                runtime_cookie.unlink(missing_ok=True)
        created = [path for path in self.output_dir.glob("*.mp3") if path not in before]
        if not created:
            raise RuntimeError("提取完成但没有找到 MP3 文件")
        return max(created, key=lambda path: path.stat().st_mtime_ns)

    def _extract_172mix(self, url: str) -> Path:
        if not shutil.which(self.ffmpeg) and not Path(self.ffmpeg).is_file():
            raise RuntimeError("找不到 FFmpeg")
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            page = response.read(2 * 1024 * 1024 + 1)
        if len(page) > 2 * 1024 * 1024:
            raise RuntimeError("网页响应过大")
        info = parse_172mix_page(page.decode("utf-8", errors="replace"))
        self.policy.validate(info.source_url)
        destination = self.output_dir / safe_filename(info.title)
        with tempfile.NamedTemporaryFile(suffix=".m4a", dir=self.output_dir, delete=False) as temp:
            source_file = Path(temp.name)
        try:
            audio_request = urllib.request.Request(
                info.source_url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": url,
                    "Range": "bytes=0-",
                },
            )
            with urllib.request.urlopen(audio_request, timeout=60) as response, source_file.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            subprocess.run(
                [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(source_file), "-codec:a", "libmp3lame", "-q:a", "0", str(destination), "-y"],
                check=True,
                timeout=self.timeout,
                stdin=subprocess.DEVNULL,
            )
        finally:
            source_file.unlink(missing_ok=True)
        if not destination.is_file():
            raise RuntimeError("转换完成但没有找到 MP3 文件")
        return destination


def extractor_from_env() -> AudioExtractor:
    configured = {
        item.strip().lower()
        for item in os.getenv("ALLOWED_DOMAINS", "").split(",")
        if item.strip()
    }
    return AudioExtractor(
        output_dir=os.getenv("OUTPUT_DIR", "downloads"),
        allowed_domains=configured or None,
        cookies=os.getenv("MEDIA_COOKIES") or None,
    )
