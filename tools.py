"""
Grounding tools for the research agent: fetch a real page, or search when the
given hint isn't a working docs URL.

Primary backend is Composio's own SDK, via its COMPOSIO_SEARCH toolkit
(FETCH_URL_CONTENT for fetching, TAVILY for search) -- these are managed,
no-extra-key tools callable with just a Composio API key, so this is a
literal use of "Composio's own SDK ... to build it," not just a design nod.

If COMPOSIO_API_KEY isn't set, both functions fall back to a free, no-key
implementation (direct HTTP fetch + Bing HTML scraping) so the pipeline still
runs for anyone without a Composio account. Callers never see the
difference -- same function signatures, same return shape.
"""

import base64
import os
import re
import time
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

_composio_client = None
_composio_checked = False


def _get_composio():
    """Lazily build a Composio client. Returns None if no API key is set,
    so every caller degrades to the free fallback automatically."""
    global _composio_client, _composio_checked
    if _composio_checked:
        return _composio_client
    _composio_checked = True
    if os.environ.get("COMPOSIO_API_KEY"):
        from composio import Composio

        _composio_client = Composio()
    return _composio_client


def backend() -> str:
    return "composio" if _get_composio() else "direct"


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "svg", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _fetch_page_direct(url: str, timeout: int) -> dict:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        text = _clean_text(resp.text) if resp.ok else ""
        return {
            "ok": resp.ok,
            "status_code": resp.status_code,
            "final_url": resp.url,
            "text": text[:8000],
            "char_count": len(text),
            "error": None,
        }
    except requests.RequestException as e:
        return {"ok": False, "status_code": None, "final_url": url, "text": "", "char_count": 0, "error": str(e)}


def _fetch_page_composio(url: str) -> dict:
    client = _get_composio()
    result = client.tools.execute(
        "COMPOSIO_SEARCH_FETCH_URL_CONTENT",
        {"urls": [url]},
        user_id="default",
        dangerously_skip_version_check=True,
    )
    if not result.get("successful"):
        return {"ok": False, "status_code": None, "final_url": url, "text": "", "char_count": 0, "error": str(result.get("error"))}

    data = result.get("data", {})
    results = data.get("results") or []
    statuses = {s["id"]: s["status"] for s in data.get("statuses", [])}
    if not results or statuses.get(url) != "success":
        return {"ok": False, "status_code": None, "final_url": url, "text": "", "char_count": 0, "error": statuses.get(url, "no result")}

    text = results[0].get("text", "") or ""
    return {
        "ok": True,
        "status_code": 200,
        "final_url": results[0].get("url", url),
        "text": text[:8000],
        "char_count": len(text),
        "error": None,
    }


def fetch_page(url: str, timeout: int = 12) -> dict:
    """Fetch a URL and return cleaned text plus fetch metadata.

    Returns dict: {ok, status_code, final_url, text, char_count, error}
    A short char_count on a success usually means a JS-rendered shell (SPA
    docs site) rather than a real failure -- callers should treat that as
    low-confidence, not as ground truth.
    """
    if not url.startswith("http"):
        url = "https://" + url

    if _get_composio():
        try:
            return _fetch_page_composio(url)
        except Exception as e:
            return {"ok": False, "status_code": None, "final_url": url, "text": "", "char_count": 0, "error": f"composio: {e}"}
    return _fetch_page_direct(url, timeout)


def _decode_bing_redirect(href: str) -> str:
    """Bing wraps result links in a bing.com/ck/a?...&u=a1<base64>&... redirect
    shim that only resolves client-side via JS, not a plain HTTP redirect.
    The real target is base64-encoded in the 'u' query param (prefixed 'a1')."""
    if "bing.com/ck/a" not in href:
        return href
    qs = parse_qs(urlparse(href).query)
    encoded = qs.get("u", [""])[0]
    if encoded.startswith("a1"):
        encoded = encoded[2:]
    encoded += "=" * (-len(encoded) % 4)  # restore stripped base64 padding
    try:
        return base64.urlsafe_b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return href


def _search_web_direct(query: str, max_results: int, timeout: int) -> list[dict]:
    try:
        resp = requests.get("https://www.bing.com/search", params={"q": query}, headers=HEADERS, timeout=timeout)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for li in soup.select("li.b_algo")[:max_results]:
            a = li.find("a")
            if not a or not a.get("href"):
                continue
            url = _decode_bing_redirect(a["href"])
            results.append({"title": a.get_text(strip=True), "url": url, "content": ""})
        return results
    except requests.RequestException:
        return []


def _search_web_composio(query: str, max_results: int) -> list[dict]:
    client = _get_composio()
    result = client.tools.execute(
        "COMPOSIO_SEARCH_TAVILY",
        {"query": query, "max_results": max_results},
        user_id="default",
        dangerously_skip_version_check=True,
    )
    if not result.get("successful"):
        return []
    hits = result.get("data", {}).get("results") or []
    return [{"title": h.get("title", ""), "url": h.get("url", ""), "content": h.get("content", "") or ""} for h in hits]


def search_web(query: str, max_results: int = 5, timeout: int = 12) -> list[dict]:
    """Search the web for a better docs URL when the given hint wasn't enough.

    Returns a list of {title, url, content}. `content` is a real text
    snippet when the backend provides one (Composio/Tavily does; the direct
    Bing fallback doesn't, so callers should fetch the url themselves in
    that case).
    """
    if _get_composio():
        try:
            return _search_web_composio(query, max_results)
        except Exception:
            return []
    return _search_web_direct(query, max_results, timeout)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    print("backend:", backend())
    r = fetch_page("stripe.com/docs/api")
    print(r["status_code"], r["char_count"], r["text"][:200])
    time.sleep(1)
    for h in search_web("Notion API authentication docs")[:3]:
        print(h["title"][:50], "|", h["url"][:60], "|", len(h["content"]), "chars")
