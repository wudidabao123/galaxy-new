"""Web tools — search, fetch, download."""

from __future__ import annotations

import re as _re
import html as _html_lib
import ssl as _ssl
import time as _time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse, parse_qs
from urllib.request import Request, urlopen

# ── SSL settings ──────────────────────────────────────
# In some corporate/development networks, SSL verification may fail due to
# proxies or MITM appliances. Set GALAXY_SSL_VERIFY=false in .env to bypass.
import os as _os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
_SSL_VERIFY = _os.environ.get("GALAXY_SSL_VERIFY", "true").lower() in ("true", "1", "yes")
_SSL_CTX = None if _SSL_VERIFY else _ssl.create_default_context()
if not _SSL_VERIFY:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = _ssl.CERT_NONE


def _urlopen(req, timeout=20):
    """Wrapper around urlopen with optional SSL bypass."""
    kwargs = {"timeout": timeout}
    if _SSL_CTX is not None:
        kwargs["context"] = _SSL_CTX
    return urlopen(req, **kwargs)


def _clip_output(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"


def _strip_html(text: str, max_chars: int = 4000) -> str:
    text = _re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = _re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html_lib.unescape(text)
    text = _re.sub(r"\s+", " ", text).strip()
    return _clip_output(text, max_chars)


# ── Retry helper ─────────────────────────────────────

def _retry_with_backoff(fn, max_retries: int = 3, base_delay: float = 1.0):
    """Call fn() with exponential backoff: 1s, 2s, 4s."""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                _time.sleep(delay)
    raise last_err  # type: ignore[misc]


# ── Fetch URL ─────────────────────────────────────────

def tool_fetch_url(url: str, max_chars: int = 12000) -> str:
    """Fetch a URL and return text content. Use for lightweight web/API lookups."""
    try:
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"}:
            return "Error: only http/https URLs are allowed"

        def _do_fetch():
            req = Request(url, headers={"User-Agent": "Galaxy-Agent/2.0"})
            with _urlopen(req, timeout=20) as resp:
                content_type = resp.headers.get("content-type", "")
                raw = resp.read(2_000_000)
            text = raw.decode("utf-8", errors="replace")
            return _clip_output(f"content-type={content_type}\n\n{text}", max(1000, min(int(max_chars), 80000)))

        return _retry_with_backoff(_do_fetch, max_retries=3, base_delay=1.0)
    except Exception as e:
        return f"Error: {e}"


# ── Web Search ────────────────────────────────────────

def tool_web_search(query: str, max_results: int = 6, fetch_pages: bool = True,
                    max_chars_per_page: int = 2500) -> str:
    """Search the web with DuckDuckGo/Bing HTML results. Optionally fetch result pages.
    Use for current info or broad web research."""
    try:
        limit = max(1, min(int(max_results), 10))
        links: list[tuple[str, str]] = []
        errors: list[str] = []

        def add_link(url: str, title: str) -> None:
            url = _html_lib.unescape(url)
            title = _strip_html(title, 300)
            if "duckduckgo.com/l/?" in url:
                parsed = urlparse(url)
                uddg = parse_qs(parsed.query).get("uddg", [""])[0]
                url = unquote(uddg) if uddg else url
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http"):
                return
            if any(prev == url for prev, _ in links):
                return
            links.append((url, title))

        # DuckDuckGo — with retry
        def _ddg_search():
            search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            req = Request(search_url, headers={"User-Agent": "Mozilla/5.0 Galaxy-Agent/2.0"})
            with _urlopen(req, timeout=25) as resp:
                return resp.read(1_500_000).decode("utf-8", errors="replace")

        try:
            html_text = _retry_with_backoff(_ddg_search, max_retries=3, base_delay=1.0)
            for match in _re.finditer(
                r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                html_text, _re.I | _re.S,
            ):
                if len(links) >= limit:
                    break
                add_link(match.group(1), match.group(2))
        except Exception as e:
            errors.append(f"DuckDuckGo failed: {e}")

        # Fallback: Bing — with retry
        if not links:
            def _bing_search():
                bing_url = f"https://www.bing.com/search?q={quote_plus(query)}"
                req = Request(bing_url, headers={"User-Agent": "Mozilla/5.0 Galaxy-Agent/2.0"})
                with _urlopen(req, timeout=25) as resp:
                    return resp.read(1_500_000).decode("utf-8", errors="replace")

            try:
                html_text = _retry_with_backoff(_bing_search, max_retries=3, base_delay=1.0)
                for match in _re.finditer(
                    r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                    html_text, _re.I | _re.S,
                ):
                    if len(links) >= limit:
                        break
                    add_link(match.group(1), match.group(2))
            except Exception as e:
                errors.append(f"Bing failed: {e}")

        if not links:
            return "Error: no search results found\n" + "\n".join(errors)

        lines = [f"Search results for: {query}", ""]
        for idx, (url, title) in enumerate(links[:limit], 1):
            lines.append(f"{idx}. **{title}**")
            lines.append(f"   <{url}>")
            if fetch_pages and len(links) <= 4:
                def _fetch_page():
                    req = Request(url, headers={"User-Agent": "Galaxy-Agent/2.0"})
                    with _urlopen(req, timeout=15) as resp:
                        return resp.read(500_000).decode("utf-8", errors="replace")
                try:
                    page = _retry_with_backoff(_fetch_page, max_retries=2, base_delay=0.5)
                    stripped = _strip_html(page, max(500, min(int(max_chars_per_page), 8000)))
                    lines.append(f"   > {stripped[:int(max_chars_per_page)]}")
                except Exception:
                    lines.append("   > (could not fetch page)")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Extract Links ─────────────────────────────────────

def tool_extract_links_from_url(url: str, max_links: int = 50) -> str:
    """Extract links, images, and documents from a web page."""
    try:
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"}:
            return "Error: only http/https URLs are allowed"
        req = Request(url, headers={"User-Agent": "Galaxy-Agent/2.0"})
        with _urlopen(req, timeout=25) as resp:
            html_text = resp.read(2_000_000).decode("utf-8", errors="replace")

        links: list[str] = []
        images: list[str] = []
        docs: list[str] = []

        for match in _re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, _re.I | _re.S):
            href = match.group(1)
            if href.startswith("//"):
                href = "https:" + href
            if href.startswith("http"):
                links.append(href)

        for match in _re.finditer(r'<img[^>]+src="([^"]+)"', html_text, _re.I):
            src = match.group(1)
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http"):
                images.append(src)

        for ext in [".pdf", ".docx", ".xlsx", ".zip", ".pptx"]:
            docs.extend([l for l in links if l.lower().endswith(ext)])

        limit = max(1, min(int(max_links), 200))
        lines = [
            f"Links from: {url}",
            "",
            "## Links",
        ]
        for l in links[:limit]:
            lines.append(f"- {l}")
        if images:
            lines.append("\n## Images")
            for img in images[:limit]:
                lines.append(f"- {img}")
        if docs:
            lines.append("\n## Documents")
            for d in docs[:limit]:
                lines.append(f"- {d}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── Download File ─────────────────────────────────────

def tool_download_file(url: str, filename: str = "") -> str:
    """Download a file from a URL. Saves to generated/downloads/."""
    from skills.builtin.file_ops import _get_workspace_root

    try:
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"}:
            return "Error: only http/https URLs are allowed"
        req = Request(url, headers={"User-Agent": "Galaxy-Agent/2.0"})
        with _urlopen(req, timeout=60) as resp:
            data = resp.read(50_000_000)

        root = _get_workspace_root()
        dl_dir = root / "generated" / "downloads"
        dl_dir.mkdir(parents=True, exist_ok=True)

        name = filename or Path(parsed.path).name or "downloaded_file"
        dest = dl_dir / name
        dest.write_bytes(data)
        return f"Downloaded {len(data)} bytes to {dest}"
    except Exception as e:
        return f"Error: {e}"


# ── Download Image ────────────────────────────────────

def tool_download_image(url: str, filename: str = "") -> str:
    """Download an image from a URL. Saves to generated/images/."""
    from skills.builtin.file_ops import _get_workspace_root

    try:
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"}:
            return "Error: only http/https URLs are allowed"
        req = Request(url, headers={"User-Agent": "Galaxy-Agent/2.0"})
        with _urlopen(req, timeout=60) as resp:
            data = resp.read(20_000_000)

        # Determine extension from content type
        ct = resp.headers.get("content-type", "")
        ext_map = {
            "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
            "image/webp": ".webp", "image/bmp": ".bmp",
        }
        ext = ext_map.get(ct.split(";")[0].strip(), ".png")

        root = _get_workspace_root()
        img_dir = root / "generated" / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

        name = filename or Path(parsed.path).name or f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        if not any(name.lower().endswith(e) for e in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]):
            name += ext
        dest = img_dir / name
        dest.write_bytes(data)
        return f"Downloaded {len(data)} bytes image to {dest}"
    except Exception as e:
        return f"Error: {e}"


# ── Current Datetime ──────────────────────────────────

def tool_current_datetime() -> str:
    """Return current date, time, weekday, and timezone info."""
    now = datetime.now()
    tz_name = now.astimezone().tzname() if hasattr(now, 'astimezone') else "local"
    return (
        f"Date: {now.strftime('%Y-%m-%d')}\n"
        f"Time: {now.strftime('%H:%M:%S')}\n"
        f"Weekday: {now.strftime('%A')}\n"
        f"ISO: {now.isoformat(timespec='seconds')}\n"
        f"Timezone: {tz_name}"
    )
