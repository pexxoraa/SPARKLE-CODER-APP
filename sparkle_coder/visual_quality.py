"""Deterministic visual-site quality checks plus bounded headless-browser rendering."""
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import struct
import subprocess

PLACEHOLDER = re.compile(r"(?:via\.placeholder\.com|placehold\.co|placehold\.it|dummyimage\.com|placeholder(?:[./_-]|$))", re.I)
GENERIC_COPY = re.compile(r"\b(?:capture your moments|welcome to our website|we bring your vision to life)\b", re.I)
COPYRIGHT_YEAR = re.compile(r"(?:©|&copy;|copyright)\s*(20\d{2})", re.I)

class SiteParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.images=[]; self.styles=[]; self.h1=0; self.classes=[]
    def handle_starttag(self, tag, attrs):
        data=dict(attrs)
        if tag=='img': self.images.append(data)
        if tag=='link' and str(data.get('rel','')).lower()=='stylesheet' and data.get('href'): self.styles.append(data['href'])
        if tag=='h1': self.h1+=1
        if data.get('class'): self.classes.extend(str(data['class']).split())

def _local_ref(value):
    return bool(value) and not re.match(r"^(?:[a-z]+:)?//|^data:|^#", value, re.I)

def _site_source(workspace, entry):
    html,_=workspace.read(entry); parser=SiteParser(); parser.feed(html); css=re.findall(r'<style[^>]*>(.*?)</style>',html,re.I|re.S)
    for href in parser.styles:
        if not _local_ref(href): continue
        try: css.append(workspace.read(str((Path(entry).parent/Path(href.split('?',1)[0].lstrip('/'))).as_posix()))[0])
        except (OSError,ValueError): pass
    return html,"\n".join(css),parser

def inspect_visual_quality(workspace, entry='index.html', domain=''):
    html,css,parser=_site_source(workspace,entry); source=html+'\n'+css; findings=[]
    def add(code,message,severity='blocking'): findings.append({'code':code,'severity':severity,'message':message})
    if PLACEHOLDER.search(source): add('placeholder-assets','Replace placeholder/dummy imagery with real project assets or an honest asset-ready layout.')
    if parser.h1!=1: add('heading-hierarchy',f'Use one clear primary h1; found {parser.h1}.')
    if '@media' not in css and 'clamp(' not in css: add('responsive-intent','No responsive breakpoint or fluid responsive sizing was found.')
    missing_alt=sum(1 for image in parser.images if not str(image.get('alt','')).strip())
    if missing_alt: add('image-alt',f'{missing_alt} image(s) have empty or missing alt text.','warning')
    photo=domain=='photography' or re.search(r'photograph|photo studio|photographer|portrait|wedding',source,re.I)
    real_images=[i for i in parser.images if i.get('src') and not PLACEHOLDER.search(str(i.get('src')))]
    backgrounds=re.findall(r'background(?:-image)?\s*:[^;{}]*url\(([^)]+)\)',css,re.I)
    real_visuals=len(real_images)+sum(not PLACEHOLDER.search(x) for x in backgrounds)
    if photo and real_visuals<3: add('photography-imagery',f'Photography presentation has only {real_visuals} non-placeholder image asset(s); imagery must lead the experience.')
    if photo and GENERIC_COPY.search(html): add('generic-creative-copy','Replace generic photography slogan/copy with a specific positioning statement.','warning')
    if re.search(r'font-family\s*:\s*(?:Arial|Helvetica|sans-serif)\s*;',css,re.I): add('default-typography','Typography relies on a default Arial/Helvetica/sans-serif declaration; choose an intentional type system.','warning')
    current=datetime.now(timezone.utc).year
    stale=[int(y) for y in COPYRIGHT_YEAR.findall(html) if int(y)<current]
    if stale: add('stale-date',f'Copyright year is stale ({min(stale)}); avoid hard-coding an outdated year.')
    cardish=sum(1 for name in parser.classes if re.search(r'(?:^|[-_])card$',name,re.I))
    if cardish>=6: add('template-repetition',f'Found {cardish} card-class instances; review whether repeated equal cards are creating a generic template rhythm.','warning')
    blocking=[f for f in findings if f['severity']=='blocking']
    lines=['Visual quality gate: '+('PASS' if not blocking else 'NEEDS WORK')]
    lines += [f"- {f['severity'].upper()} {f['code']}: {f['message']}" for f in findings] or ['- No deterministic visual-quality defects found.']
    return {'ok':not blocking,'exit_code':0 if not blocking else 1,'entry':entry,'domain':'photography' if photo else domain or 'general','findings':findings,'output':'\n'.join(lines)}

def find_browser():
    for name in ('chromium','chromium-browser','google-chrome','google-chrome-stable','chrome'):
        path=shutil.which(name)
        if path:return path
    for path in (r'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',r'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'):
        if Path(path).is_file():return path
    return None

def _png_size(path):
    data=path.read_bytes()[:24]
    if len(data)>=24 and data[:8]==b'\x89PNG\r\n\x1a\n': return struct.unpack('>II',data[16:24])
    return None

def render_page(workspace, session_directory, entry='index.html', viewport='desktop'):
    source=workspace.path(entry)
    if not source.is_file(): raise ValueError('Render entry file not found.')
    sizes={'desktop':(1440,1000),'mobile':(390,844)}
    if viewport not in sizes: raise ValueError('Viewport must be desktop or mobile.')
    browser=find_browser()
    if not browser:return {'ok':False,'available':False,'viewport':viewport,'error':'Chromium/Chrome is not installed; deterministic visual checks can still run.'}
    out=Path(session_directory)/'renders';out.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=out/f'{Path(entry).stem}-{viewport}.png'; width,height=sizes[viewport]
    command=[browser,'--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--disable-default-apps',f'--window-size={width},{height}',f'--screenshot={target}',source.resolve().as_uri()]
    result=subprocess.run(command,cwd=workspace.root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    if result.returncode!=0 or not target.is_file():return {'ok':False,'available':True,'viewport':viewport,'error':('Browser render failed. '+result.stdout[-1200:]).strip()}
    actual=_png_size(target)
    return {'ok':True,'available':True,'viewport':viewport,'requested_size':[width,height],'image_size':list(actual) if actual else None,'screenshot':str(target)}
