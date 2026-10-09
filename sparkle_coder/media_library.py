"""User-requested image sourcing and original non-AI SVG graphic creation."""
from html import escape
from pathlib import PurePosixPath
from urllib.parse import urlsplit
import re

from .files import UserFiles
from .internet import search_public_assets, download_public_asset

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
_ALLOWED = frozenset({'soft', 'bold', 'night'})


def _color(value, fallback):
    return value if isinstance(value,str) and _HEX.fullmatch(value) else fallback


def import_commons_image(workspace, query, url):
    """Revalidate metadata at source rather than trusting browser-supplied license."""
    if not isinstance(url, str) or len(url)>2048:
        raise ValueError('Select an image from the search results.')
    # Commons search returns raster download URLs on these Wikimedia hosts.
    # Reject obviously unrelated hosts *before* querying the network while
    # holding the project lock. The downstream downloader still validates
    # public DNS, redirects, bytes, size and media signature.
    try:
        parsed=urlsplit(url)
        trusted=(parsed.scheme=='https' and parsed.hostname in
                 ('upload.wikimedia.org','commons.wikimedia.org') and
                 not parsed.username and not parsed.password and
                 parsed.port in (None,443) and not parsed.fragment)
    except ValueError:
        trusted=False
    if not trusted:
        raise ValueError('Search results changed. Search again and choose the Wikimedia image you want.')
    result=search_public_assets(query,8)
    selected=next((r for r in result['results'] if r['url']==url),None)
    if not selected:
        raise ValueError('Search results changed. Search again and choose the image you want.')
    if selected.get('license') in ('Check source page','',None):
        raise ValueError('This image has no verified license label. Choose another source.')
    asset=download_public_asset(url)
    extension={
        'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','image/gif':'.gif'
    }[asset['content_type']]
    name=re.sub(r'[^a-z0-9]+','-',selected['title'].rsplit('.',1)[0].lower()).strip('-')[:55] or 'image'
    files=UserFiles(workspace.root)
    requested=f'assets/{name}{extension}'
    destination=files.available(requested)
    destination_path=files.path(destination)
    destination_path.parent.mkdir(parents=True,exist_ok=True)
    with destination_path.open('xb') as stream:
        stream.write(asset['data'])
    note=(
        'Image source: '+selected['source_page']+'\n'
        'Creator: '+(selected.get('creator') or 'See source page')+'\n'
        'License label: '+selected['license']+'\n'
        'Downloaded URL: '+asset['url']+'\n'
        'Always check the original source page and its license requirements before publishing.\n'
    )
    # Each image has its own attribution note; never silently overwrite credits.
    attribution=files.available(destination+'.source.txt')
    try:
        with files.path(attribution).open('x', encoding='utf-8') as stream:
            stream.write(note)
    except (OSError,ValueError):
        # An image without its required source/licensing record must not be
        # presented as successfully imported.
        destination_path.unlink(missing_ok=True)
        raise
    return {'path':destination,'source_note':attribution,'source_page':selected['source_page'],
            'creator':selected.get('creator',''),'license':selected['license'],
            'bytes':asset['bytes']}


def create_svg_graphic(workspace, title, style='soft', primary='#376f58', secondary='#e6eedc'):
    if not isinstance(title,str) or not 1<=len(title.strip())<=80:
        raise ValueError('Give the illustration a title (1–80 characters).')
    if style not in _ALLOWED:
        raise ValueError('Choose soft, bold or night illustration.')
    primary=_color(primary,'#376f58')
    secondary=_color(secondary,'#e6eedc')
    title=title.strip()
    # Original simple SVG, not a text-to-image AI or photo generator.
    safe=escape(title,quote=True)
    background={'soft':'#f7f6f1','bold':'#f5f4f0','night':'#101d1b'}[style]
    opacity={'soft':'0.42','bold':'0.72','night':'0.65'}[style]
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 720" role="img" aria-label="{safe}">
<title>{safe}</title>
<defs><linearGradient id="wash" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="{primary}"/><stop offset="100%" stop-color="{secondary}"/>
</linearGradient><clipPath id="frame"><rect width="1200" height="720" rx="24"/></clipPath></defs>
<g clip-path="url(#frame)"><rect width="1200" height="720" fill="{background}"/>
<circle cx="970" cy="130" r="435" fill="url(#wash)" opacity="{opacity}"/>
<circle cx="265" cy="675" r="410" fill="{secondary}" opacity="0.75"/>
<path d="M-40 600C225 235 420 330 630 150S1040 40 1270 330V800H-40Z"
fill="{primary}" opacity="0.35"/>
<path d="M-20 710C275 435 490 510 700 335S1000 275 1240 505V800H-20Z"
fill="{primary}" opacity="0.60"/>
<circle cx="760" cy="410" r="104" fill="{secondary}" opacity="0.85"/></g></svg>'''
    files=UserFiles(workspace.root)
    slug=re.sub(r'[^a-z0-9]+','-',title.lower()).strip('-')[:40] or 'graphic'
    destination=files.available('assets/'+slug+'.svg')
    path=files.path(destination);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as output:output.write(svg.encode('utf-8'))
    return {'path':destination,'bytes':path.stat().st_size,'kind':'original_vector_graphic',
            'message':'Created an original SVG graphic, not an AI-generated photograph. The file is editable.'}
