"""Bounded public-Web retrieval for the coding agent.

Shell commands remain network-isolated. These helpers intentionally send no cookies,
credentials, referer, or project data beyond the explicit search query / URL.
"""

import base64
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, quote_plus, urlencode, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

USER_AGENT = "SPARKLE-CODER/0.8.0"
MAX_DOWNLOAD = 512_000
_SECRET_TEXT = re.compile(
    r"(?i)\b(?:api[_ -]?key|access[_ -]?token|secret|password|authorization|bearer)\b\s*[:=]\s*\S+"
)
_SECRET_PARAMS = frozenset({"api_key","apikey","key","access_token","token","secret",
                           "password","authorization","auth","signature","sig"})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_NoRedirect())


def _public_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Web URL is invalid.")
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public http(s) URLs without credentials are allowed.")
    if any(key.lower() in _SECRET_PARAMS for key in parse_qs(parsed.query, keep_blank_values=True)):
        raise ValueError("URLs containing credential-like query parameters are blocked.")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Only standard web ports 80 and 443 are allowed.")
    host = parsed.hostname.rstrip(".")
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError("Local/private network addresses are blocked.")
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(host, parsed.port or
                     (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("Web host could not be resolved.") from exc
    if not addresses:
        raise ValueError("Web host could not be resolved.")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("Local/private network addresses are blocked.")
    return url


def _fetch(url, *, max_bytes=MAX_DOWNLOAD, timeout=10):
    current = _public_url(url)
    for _ in range(5):
        request = Request(current, headers={"User-Agent": USER_AGENT,
            "Accept": "text/html,text/plain,application/xhtml+xml;q=0.9,*/*;q=0.1",
            "Accept-Encoding": "identity"})
        try:
            response = _OPENER.open(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                current = _public_url(urljoin(current, exc.headers["Location"]))
                continue
            raise ValueError(f"Web request returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ValueError("Web request failed or timed out.") from exc
        with response:
            final = _public_url(response.geturl())
            content_type = response.headers.get_content_type().lower()
            if content_type not in ("text/html", "text/plain", "application/xhtml+xml"):
                raise ValueError("Web page is not readable text/HTML.")
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("Web page is too large to read safely.")
            charset = response.headers.get_content_charset() or "utf-8"
        return final, data.decode(charset, errors="replace"), content_type
    raise ValueError("Too many web redirects.")


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.title_depth = 0
        self.title = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip += 1
        if tag == "title":
            self.title_depth += 1
        if tag in {"p", "div", "section", "article", "main", "li", "h1", "h2", "h3", "h4", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "canvas"} and self.skip:
            self.skip -= 1
        if tag == "title" and self.title_depth:
            self.title_depth -= 1

    def handle_data(self, data):
        if self.skip:
            return
        if self.title_depth:
            self.title.append(data)
        self.parts.append(data)

    def result(self):
        text = unescape(" ".join(self.parts))
        text = "\n".join(" ".join(line.split()) for line in text.splitlines())
        text = "\n".join(line for line in text.splitlines() if line)
        return " ".join(self.title).strip(), text


class _SearchParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.current = None
        self.capture_title = False
        self.capture_snippet = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self.current = {"url": attrs.get("href", ""), "title": "", "snippet": ""}
            self.results.append(self.current)
            self.capture_title = True
        elif self.current is not None and ("result__snippet" in classes or "result-snippet" in classes):
            self.capture_snippet = True

    def handle_endtag(self, tag):
        if tag == "a":
            self.capture_title = False
        if tag in {"a", "div"}:
            self.capture_snippet = False

    def handle_data(self, data):
        if self.current is None:
            return
        if self.capture_title:
            self.current["title"] += data
        elif self.capture_snippet:
            self.current["snippet"] += data


class _BingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.in_result = 0
        self.in_h2 = 0
        self.current = None
        self.capture_title = False
        self.capture_snippet = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "li" and "b_algo" in classes:
            self.in_result += 1
            self.current = None
        elif self.in_result and tag == "h2":
            self.in_h2 += 1
        elif self.in_result and self.in_h2 and tag == "a" and self.current is None:
            self.current = {"url": attrs.get("href", ""), "title": "", "snippet": ""}
            self.results.append(self.current)
            self.capture_title = True
        elif self.in_result and self.current is not None and tag == "p":
            self.capture_snippet = True

    def handle_endtag(self, tag):
        if tag == "a":
            self.capture_title = False
        elif tag == "p":
            self.capture_snippet = False
        elif tag == "h2" and self.in_h2:
            self.in_h2 -= 1
        elif tag == "li" and self.in_result:
            self.in_result -= 1
            self.current = None
            self.capture_title = False
            self.capture_snippet = False

    def handle_data(self, data):
        if self.current is None:
            return
        if self.capture_title:
            self.current["title"] += data
        elif self.capture_snippet:
            self.current["snippet"] += data


def _bing_target(href):
    href = unescape(href or "")
    parsed = urlsplit(href)
    if parsed.hostname and parsed.hostname.lower().endswith("bing.com") and parsed.path.startswith("/ck/"):
        token = (parse_qs(parsed.query).get("u") or [""])[0]
        if token.startswith("a1"):
            token = token[2:]
        if token:
            try:
                token += "=" * ((4 - len(token) % 4) % 4)
                decoded = base64.urlsafe_b64decode(token.encode()).decode("utf-8")
                if urlsplit(decoded).scheme in ("http", "https"):
                    return decoded
            except (ValueError, UnicodeDecodeError):
                pass
    return href


def _search_target(href):
    href = unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlsplit(href)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            href = unquote(target[0])
    return href


def _clean_results(items, limit, target):
    results, seen = [], set()
    for item in items:
        try:
            url = _public_url(target(item.get("url")))
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": " ".join(item.get("title", "").split())[:300],
                        "url": url, "snippet": " ".join(item.get("snippet", "").split())[:700]})
        if len(results) >= limit:
            break
    return results


def web_search(query, limit=5):
    query = " ".join(str(query or "").split())
    if not query or len(query) > 500:
        raise ValueError("Search query must contain 1–500 characters.")
    if _SECRET_TEXT.search(query):
        raise ValueError("Search query appears to contain a credential or secret.")
    limit = max(1, min(8, int(limit)))
    try:
        _, html, _ = _fetch("https://html.duckduckgo.com/html/?q=" + quote_plus(query), max_bytes=350_000)
        parser = _SearchParser()
        parser.feed(html)
        results = _clean_results(parser.results, limit, _search_target)
        if results:
            return {"query": query, "provider": "duckduckgo", "results": results}
    except ValueError:
        pass
    try:
        _, html, _ = _fetch("https://www.bing.com/search?q=" + quote_plus(query), max_bytes=350_000)
        parser = _BingParser()
        parser.feed(html)
        results = _clean_results(parser.results, limit, _bing_target)
        if results:
            return {"query": query, "provider": "bing", "results": results}
    except ValueError:
        pass
    raise ValueError("Web search providers returned no readable results.")


def read_web_page(url, max_chars=12000):
    max_chars = max(1000, min(20000, int(max_chars)))
    final, body, content_type = _fetch(url)
    if content_type == "text/plain":
        title, text = "", body
    else:
        parser = _TextParser()
        parser.feed(body)
        title, text = parser.result()
    truncated = len(text) > max_chars
    return {"url": final, "title": title[:300], "text": text[:max_chars], "truncated": truncated}

ASSET_TYPES = {
    'image/jpeg': ('.jpg','.jpeg'),
    'image/png': ('.png',),
    'image/webp': ('.webp',),
    'image/gif': ('.gif',),
}
ASSET_MAX_DOWNLOAD = 5_000_000

def download_public_asset(url, max_bytes=ASSET_MAX_DOWNLOAD):
    """Download one bounded public raster image without cookies, auth, or redirects to private hosts."""
    current=_public_url(url); maximum=max(1,min(ASSET_MAX_DOWNLOAD,int(max_bytes)))
    for _ in range(5):
        request=Request(current,headers={'User-Agent':USER_AGENT,'Accept':'image/avif,image/webp,image/png,image/jpeg,image/gif;q=0.8,*/*;q=0.1','Accept-Encoding':'identity'})
        try: response=_OPENER.open(request,timeout=15)
        except HTTPError as exc:
            if exc.code in (301,302,303,307,308) and exc.headers.get('Location'):
                current=_public_url(urljoin(current,exc.headers['Location']));continue
            raise ValueError(f'Asset request returned HTTP {exc.code}.') from exc
        except (URLError,TimeoutError,OSError) as exc: raise ValueError('Asset request failed or timed out.') from exc
        with response:
            final=_public_url(response.geturl());content_type=response.headers.get_content_type().lower()
            if content_type not in ASSET_TYPES: raise ValueError('Only JPEG, PNG, WebP and GIF image assets are supported.')
            data=response.read(maximum+1)
            if len(data)>maximum: raise ValueError('Image asset is too large to download safely.')
        signatures={'image/jpeg':data[:3]==b'\xff\xd8\xff','image/png':data[:8]==b'\x89PNG\r\n\x1a\n','image/gif':data[:6] in (b'GIF87a',b'GIF89a'),'image/webp':len(data)>=12 and data[:4]==b'RIFF' and data[8:12]==b'WEBP'}
        if not signatures.get(content_type): raise ValueError('Image bytes do not match the declared content type.')
        return {'url':final,'content_type':content_type,'data':data,'bytes':len(data),'extensions':ASSET_TYPES[content_type]}
    raise ValueError('Too many asset redirects.')


def _plain_metadata(value):
    if not isinstance(value,str): return ''
    return re.sub(r'<[^>]+>',' ',unescape(value)).replace('&nbsp;',' ').strip()

def search_public_assets(query, limit=6):
    """Search Wikimedia Commons image files with source/license metadata and direct bounded download URLs."""
    query=' '.join(str(query or '').split())
    if not query or len(query)>300: raise ValueError('Asset search query must contain 1–300 characters.')
    if _SECRET_TEXT.search(query): raise ValueError('Asset search query appears to contain a credential or secret.')
    limit=max(1,min(8,int(limit)))
    params=urlencode({'action':'query','generator':'search','gsrsearch':query,'gsrnamespace':'6','gsrlimit':str(limit),
                      'prop':'imageinfo','iiprop':'url|size|extmetadata','iiurlwidth':'1600','format':'json','formatversion':'2'})
    current=_public_url('https://commons.wikimedia.org/w/api.php?'+params)
    request=Request(current,headers={'User-Agent':USER_AGENT,'Accept':'application/json','Accept-Encoding':'identity'})
    try: response=_OPENER.open(request,timeout=12)
    except (HTTPError,URLError,TimeoutError,OSError) as exc: raise ValueError('Public asset search failed or timed out.') from exc
    with response:
        if response.headers.get_content_type().lower() not in ('application/json','text/json'):
            raise ValueError('Public asset search returned an unreadable response.')
        data=response.read(1_000_001)
        if len(data)>1_000_000: raise ValueError('Public asset search response was too large.')
    try: payload=json.loads(data.decode('utf-8'))
    except (ValueError,UnicodeDecodeError) as exc: raise ValueError('Public asset search returned invalid JSON.') from exc
    items=[]
    for page in payload.get('query',{}).get('pages',[]) if isinstance(payload,dict) else []:
        info=(page.get('imageinfo') or [{}])[0]; meta=info.get('extmetadata') or {}; url=info.get('thumburl') or info.get('url')
        try: url=_public_url(url)
        except ValueError: continue
        title=str(page.get('title','')).removeprefix('File:')[:300]
        license_name=_plain_metadata((meta.get('LicenseShortName') or {}).get('value'))[:120]
        creator=_plain_metadata((meta.get('Artist') or {}).get('value'))[:240]
        description=_plain_metadata((meta.get('ImageDescription') or {}).get('value'))[:400]
        source='https://commons.wikimedia.org/wiki/'+quote(str(page.get('title','')).replace(' ','_'),safe=':_()-')
        items.append({'title':title,'url':url,'source_page':source,'license':license_name or 'Check source page','creator':creator,'description':description,
                      'width':info.get('thumbwidth') or info.get('width'),'height':info.get('thumbheight') or info.get('height')})
        if len(items)>=limit: break
    if not items: raise ValueError('No reusable public image candidates were returned for this search.')
    return {'query':query,'provider':'wikimedia_commons','results':items}
