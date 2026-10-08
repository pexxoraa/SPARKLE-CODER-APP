"""Bounded, inert previews of static project HTML and same-project assets.

Preview HTML is never a trusted app page: the browser must load it in a
sandboxed iframe WITHOUT allow-same-origin or allow-scripts. No dev server,
command execution, authenticated URL or external fetch is involved.
"""
import base64
from html import escape
from pathlib import PurePosixPath
import mimetypes
import re
from urllib.parse import unquote, urlsplit

from .files import UserFiles

MAX_HTML = 500_000
MAX_ASSETS = 48
MAX_BUNDLE = 3_000_000
MAX_RESOURCE = 1_200_000
ASSET_MIME = {
    '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp',
    '.svg': 'image/svg+xml', '.woff': 'font/woff', '.woff2': 'font/woff2',
}
_CSS_URL = re.compile(r'url\(\s*([\'"]?)(.*?)\1\s*\)', re.I)
_HTML_ATTR = re.compile(r'(<(?:img|source|link)\b[^>]*?\b(?:src|href)\s*=\s*)([\'"])(.*?)\2', re.I | re.S)
_SCRIPT = re.compile(r'<script\b[^>]*>.*?</script\s*>', re.I | re.S)
_IFRAME = re.compile(r'<(?:iframe|object|embed)\b[^>]*>(?:.*?</(?:iframe|object|embed)\s*>)?', re.I | re.S)
_REFRESH = re.compile(r'<meta\b(?=[^>]*http-equiv\s*=\s*[\'"]?refresh\b)[^>]*>', re.I)
_BASE = re.compile(r'<base\b[^>]*>', re.I)
_SRCSET = re.compile(r'\s+(?:srcset|imagesrcset)\s*=\s*(?:[\'"][^\'"]*[\'"]|[^\s>]+)', re.I)


def _reference(entry, value):
    if not isinstance(value, str) or not value.strip() or len(value)>512:
        return None
    ref=value.strip()
    parsed=urlsplit(ref)
    if parsed.scheme or parsed.netloc or ref.startswith(('#', '//', 'data:')):
        return None
    if parsed.query or parsed.fragment:
        # Static query strings are not distinct project files.
        ref=parsed.path
    if not ref or '%' in ref:
        # Reject encoded path traversal and ambiguous URL decoding.
        return None
    pieces=([] if ref.startswith('/') else list(PurePosixPath(entry).parent.parts)) + list(PurePosixPath(ref.lstrip('/')).parts)
    clean=[]
    for part in pieces:
        if part in ('', '.'):continue
        if part=='..':
            if not clean:return None
            clean.pop()
        else:clean.append(part)
    return '/'.join(clean)


def preview_site(files: UserFiles, entry='index.html'):
    """Return one static snapshot. The UI enforces iframe sandbox=''."""
    if not isinstance(entry, str) or len(entry)>240 or not entry.lower().endswith(('.html','.htm')):
        raise ValueError('Select an HTML file to preview. For framework projects, build the site first.')
    entry_path=files.path(entry)
    if files.protected(PurePosixPath(entry).parts) or not entry_path.is_file():
        raise ValueError('HTML entry not found. Build index.html or dist/index.html first.')
    if entry_path.stat().st_size>MAX_HTML:
        raise ValueError('The HTML entry exceeds the safe preview size (500 KB).')
    try:
        html=entry_path.read_text('utf-8')
    except UnicodeError as exc:
        raise ValueError('Preview HTML must be UTF-8.') from exc

    used=set()
    total=0
    warnings=[]
    def warn(note):
        if note not in warnings and len(warnings)<12:warnings.append(note)

    def data_url(base, ref, css_depth=0):
        nonlocal total
        path=_reference(base,ref)
        if not path:return None
        ext=PurePosixPath(path).suffix.lower()
        if ext not in ASSET_MIME:return None
        if files.protected(PurePosixPath(path).parts):
            warn('Protected project files cannot be included in previews.')
            return None
        try:
            absolute=files.path(path)
            if not absolute.is_file() or absolute.stat().st_size>MAX_RESOURCE:
                warn('A local asset is missing or larger than 1.2 MB: '+path[:100])
                return None
            content=absolute.read_bytes()
        except (ValueError,OSError):
            warn('Could not read project asset: '+path[:100])
            return None
        if path not in used:
            if len(used)>=MAX_ASSETS or total+len(content)>MAX_BUNDLE:
                warn('Preview reached its 48-asset / 3 MB limit. Some images or styles may be missing.')
                return None
            used.add(path);total+=len(content)
        if ext=='.css':
            if css_depth>=3:
                warn('Nested stylesheet imports are not included beyond 3 levels.')
                return None
            try:text=content.decode('utf-8')
            except UnicodeError:return None
            text=replace_css(text,path,css_depth+1)
            return 'data:text/css;base64,'+base64.b64encode(text.encode('utf-8')).decode('ascii')
        mime=ASSET_MIME[ext]
        # SVGs are displayed only as images; the iframe itself cannot run script.
        return 'data:'+mime+';base64,'+base64.b64encode(content).decode('ascii')

    def replace_css(css,base,depth=0):
        def repl(m):
            target=m.group(2).strip()
            replacement=data_url(base,target,depth)
            if not replacement:
                if not target.startswith('data:'):warn('External or unsupported CSS asset was blocked.')
                return 'url("")' if not target.startswith('data:') else 'url("")'
            return 'url("'+replacement+'")'
        css=_CSS_URL.sub(repl,css)
        # Remote imports are blocked, and local imports require the same safe
        # file-resolution limit as other style resources.
        css=re.sub(r'@import\s+[^;]+;', '',css,flags=re.I)
        return css

    # External links and scripts are not run by the preview. Images and styles
    # referenced by relative path are embedded as bounded data: URLs.
    html=_SCRIPT.sub('',html)
    html=_IFRAME.sub('',html)
    html=_BASE.sub('',html)
    html=_REFRESH.sub('',html)
    html=_SRCSET.sub('',html)
    def replace_asset(m):
        tag=m.group(1)
        full=tag.lower()
        original=m.group(3)
        if full.startswith('<link'):
            tag_text=html[m.start():html.find('>',m.start())+1].lower()
            if 'stylesheet' not in tag_text:return m.group(0)
        replacement=data_url(entry,original)
        if replacement:return tag+m.group(2)+escape(replacement,quote=True)+m.group(2)
        warn('An external or unsupported asset was not included: '+original[:100])
        return tag+m.group(2)+''+m.group(2)
    html=_HTML_ATTR.sub(replace_asset,html)
    # Rewrite inline CSS background references, without touching data URLs.
    def inline_stylesheet(match):
        css=replace_css(match.group(1),entry)
        data='data:text/css;base64,'+base64.b64encode(css.encode('utf-8')).decode('ascii')
        return '<link rel="stylesheet" href="'+data+'">'
    html=re.sub(r'<style\b[^>]*>(.*?)</style\s*>',
                inline_stylesheet,html,flags=re.I|re.S)
    # Prevent relative links from navigating the sandbox to app routes or
    # remote sites. Users can choose other static HTML entries in the UI.
    html=re.sub(r'(<a\b[^>]*?)\s+href\s*=\s*([\'"])[^\'"]*\2',
                r'\1',html,flags=re.I)
    csp="default-src 'none'; style-src data:; img-src data:; font-src data:; script-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'"
    shield='<meta http-equiv="Content-Security-Policy" content="'+escape(csp,quote=True)+'"><meta name="referrer" content="no-referrer">'
    if re.search(r'<head\b[^>]*>',html,re.I):
        html=re.sub(r'<head\b[^>]*>',lambda m:m.group(0)+shield,html,count=1,flags=re.I)
    else:
        html='<head>'+shield+'</head>'+html
    return {'entry':entry,'html':html,'assets':len(used),
            'warnings':warnings+['Static snapshot: JavaScript, forms, links and external network requests are disabled. Select a different HTML entry to view other pages; dynamic apps need a running server.']}
