"""Deterministic multi-page visual-site quality checks plus bounded headless-browser rendering."""
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess

PLACEHOLDER = re.compile(r"(?:via\.placeholder\.com|placehold\.co|placehold\.it|dummyimage\.com|placeholder(?:[./_-]|$))", re.I)
GENERIC_COPY = re.compile(r"\b(?:capturing moments,? creating memories|capture your moments|welcome to our website|we bring your vision to life|state-of-the-art|passionate team)\b", re.I)
PLACEHOLDER_IDENTITY = re.compile(r"\b(?:john doe|jane doe|jane smith|bob johnson|lorem ipsum)\b", re.I)
UNVERIFIED_CLAIM = re.compile(r"\b(?:over\s+\d+\s+years|\d+\+\s+years|award[- ]winning|industry[- ]leading)\b", re.I)
COPYRIGHT_YEAR = re.compile(r"(?:©|&copy;|copyright)\s*(20\d{2})", re.I)

class SiteParser(HTMLParser):
    def __init__(self):
        super().__init__();self.images=[];self.styles=[];self.scripts=[];self.links=[];self.h1=0;self.classes=[];self.forms=[]
    def handle_starttag(self, tag, attrs):
        data=dict(attrs)
        if tag=="img": self.images.append(data)
        if tag=="link" and str(data.get("rel","")).lower()=="stylesheet" and data.get("href"): self.styles.append(data["href"])
        if tag=="script" and data.get("src"): self.scripts.append(data["src"])
        if tag=="a" and data.get("href"): self.links.append(data["href"])
        if tag=="form": self.forms.append(data)
        if tag=="h1": self.h1+=1
        if data.get("class"): self.classes.extend(str(data["class"]).split())

def _local_ref(value):
    return bool(value) and not re.match(r"^(?:[a-z]+:)?//|^(?:data:|#|mailto:|tel:|javascript:)",str(value),re.I)

def _resolve(entry,ref):
    clean=str(ref).split("#",1)[0].split("?",1)[0].strip()
    if not clean:return None
    if clean.startswith("/"): clean=clean.lstrip("/")
    else: clean=(PurePosixPath(entry).parent/PurePosixPath(clean)).as_posix()
    parts=[]
    for part in PurePosixPath(clean).parts:
        if part in ("","."):continue
        if part=="..":
            if not parts:return None
            parts.pop()
        else:parts.append(part)
    return "/".join(parts)

def _read_page(workspace,entry):
    html,_=workspace.read(entry);parser=SiteParser();parser.feed(html);css=[]
    for href in parser.styles:
        if not _local_ref(href):continue
        resolved=_resolve(entry,href)
        if not resolved:continue
        try:css.append(workspace.read(resolved)[0])
        except (OSError,ValueError):pass
    inline=re.findall(r"<style[^>]*>(.*?)</style>",html,re.I|re.S)
    return html,"\n".join(inline+css),parser

def _discover_pages(workspace,entry,max_pages=12):
    todo=[entry];seen=[];parsed={}
    while todo and len(seen)<max_pages:
        page=todo.pop(0)
        if page in seen:continue
        try:html,css,parser=_read_page(workspace,page)
        except (OSError,ValueError):continue
        seen.append(page);parsed[page]=(html,css,parser)
        for href in parser.links:
            if not _local_ref(href):continue
            resolved=_resolve(page,href)
            if resolved and resolved.lower().endswith((".html",".htm")) and resolved not in seen and resolved not in todo:
                try:
                    if workspace.path(resolved).is_file():todo.append(resolved)
                except (OSError,ValueError):pass
    return seen,parsed

def _visual_count(parser,css):
    images=[i for i in parser.images if i.get("src") and not PLACEHOLDER.search(str(i.get("src")))]
    backgrounds=re.findall(r"background(?:-image)?\s*:[^;{}]*url\(([^)]+)\)",css,re.I)
    backgrounds=[x for x in backgrounds if not PLACEHOLDER.search(x)]
    return len(images)+len(backgrounds),images

def inspect_visual_quality(workspace, entry="index.html", domain=""):
    pages,parsed=_discover_pages(workspace,entry)
    if entry not in parsed:
        return {"ok":False,"exit_code":1,"entry":entry,"domain":domain or "general","pages":[],"render_entries":[entry],
                "findings":[{"code":"missing-entry","severity":"blocking","message":f"{entry} was not found."}],
                "output":f"Visual quality gate: NEEDS WORK\n- BLOCKING missing-entry: {entry} was not found."}

    findings=[]
    def add(code,message,severity="blocking"):
        if not any(f["code"]==code and f["message"]==message for f in findings):
            findings.append({"code":code,"severity":severity,"message":message})

    all_html="\n".join(parsed[p][0] for p in pages)
    all_css="\n".join(parsed[p][1] for p in pages)
    source=all_html+"\n"+all_css
    photo=domain=="photography" or re.search(r"photograph|photo studio|photographer|portrait|wedding",source,re.I)
    css_classes=set(re.findall(r"\.([a-zA-Z_][\w-]*)",all_css))
    site_visuals=0;home_visuals=0;hotlinks=0;secondary_render=None

    for page in pages:
        html,css,parser=parsed[page];page_source=html+"\n"+css
        if PLACEHOLDER.search(page_source):add("placeholder-assets",f"{page}: placeholder/dummy imagery is not acceptable finished work.")
        if parser.h1!=1:add("heading-hierarchy",f"{page}: use one clear primary h1; found {parser.h1}.")
        missing_alt=sum(1 for image in parser.images if not str(image.get("alt","")).strip())
        if missing_alt:add("image-alt",f"{page}: {missing_alt} image(s) have empty or missing alt text.","warning")
        for kind,refs in (("stylesheet",parser.styles),("script",parser.scripts),("image",[i.get("src") for i in parser.images]),("page",parser.links)):
            for ref in refs:
                if not _local_ref(ref):continue
                resolved=_resolve(page,ref)
                if not resolved:continue
                if kind=="page" and not resolved.lower().endswith((".html",".htm")):continue
                try:exists=workspace.path(resolved).is_file()
                except (OSError,ValueError):exists=False
                if not exists:add("missing-local-resource",f"{page}: referenced {kind} '{ref}' does not exist.")
        visuals,images=_visual_count(parser,css);site_visuals+=visuals
        if page==entry:home_visuals=visuals
        elif visuals and secondary_render is None:secondary_render=page
        hotlinks+=sum(bool(re.match(r"^(?:https?:)?//",str(i.get("src")),re.I)) for i in images)
        stale=[int(y) for y in COPYRIGHT_YEAR.findall(html) if int(y)<datetime.now(timezone.utc).year]
        if stale:add("stale-date",f"{page}: copyright year is stale ({min(stale)}).")
        if PLACEHOLDER_IDENTITY.search(html):add("placeholder-identity",f"{page}: placeholder/fake identity content is present.")
        if GENERIC_COPY.search(html):add("generic-creative-copy",f"{page}: generic AI/stock marketing copy should be replaced with specific positioning.","warning")
        if UNVERIFIED_CLAIM.search(html):add("unverified-claim",f"{page}: contains a factual-sounding experience/award claim that must be grounded in user input.","warning")
        if parser.forms:
            for form in parser.forms:
                if str(form.get("method","get")).lower()=="post" and str(form.get("action","#")).strip() in ("","#"):
                    add("nonfunctional-form",f"{page}: form posts nowhere; do not present it as a working inquiry flow.")
        if page!=entry:
            used={c for c in parser.classes if c}
            if len(used)>=3:
                styled=sum(1 for c in used if c in css_classes)
                if styled/max(1,len(used))<0.35:add("unstyled-secondary-page",f"{page}: most page-specific classes have no matching stylesheet rules; the page appears unfinished.")
        repeats={}
        for c in parser.classes:repeats[c]=repeats.get(c,0)+1
        if photo and any(count>=5 and re.search(r"(?:gallery|card|item|tile)",name,re.I) for name,count in repeats.items()):
            add("uniform-gallery-template",f"{page}: repeated equal gallery/card items create a generic thumbnail-grid rhythm.","warning")

    if "@media" not in all_css and "clamp(" not in all_css:add("responsive-intent","No responsive breakpoint or fluid responsive sizing was found.")
    default_type=bool(re.search(r"font-family\s*:\s*(?:(?:['\"]?(?:Arial|Helvetica)['\"]?)(?:\s*,[^;}]+)?|sans-serif)\s*(?:;|})",all_css,re.I))
    if default_type:add("default-typography","Creative-site typography relies on a default Arial/Helvetica/sans-serif declaration; choose an intentional type system.","blocking" if photo else "warning")
    if photo and home_visuals<1:add("homepage-photography-lead","Photography homepage has no real visual asset; the work must lead the first impression.")
    if photo and site_visuals<3:add("photography-imagery",f"Photography site has only {site_visuals} non-placeholder visual asset(s); a finished portfolio needs a stronger curated image set.")
    if photo and hotlinks:add("external-image-hotlink",f"{hotlinks} photography image(s) are remotely hotlinked; localize approved/reusable assets for reliability.","warning")
    if photo and len(pages)>1 and secondary_render is None:add("secondary-pages-no-imagery","Multi-page photography site has no image-led secondary page; portfolio depth is missing.")
    cardish=sum(1 for _,_,parser in parsed.values() for name in parser.classes if re.search(r"(?:^|[-_])card$",name,re.I))
    if cardish>=6:add("template-repetition",f"Found {cardish} card-class instances; repeated equal cards are creating a generic template rhythm.","warning")

    blocking=[f for f in findings if f["severity"]=="blocking"]
    lines=["Visual quality gate: "+("PASS" if not blocking else "NEEDS WORK"),"- Pages audited: "+", ".join(pages)]
    lines += [f"- {f['severity'].upper()} {f['code']}: {f['message']}" for f in findings] or ["- No deterministic visual-quality defects found."]
    render_entries=[entry]+([secondary_render] if secondary_render and secondary_render!=entry else [])
    return {"ok":not blocking,"exit_code":0 if not blocking else 1,"entry":entry,"domain":"photography" if photo else domain or "general",
            "pages":pages,"render_entries":render_entries[:2],"findings":findings,"output":"\n".join(lines)}

def find_browser():
    for name in ("chromium","chromium-browser","google-chrome","google-chrome-stable","chrome"):
        path=shutil.which(name)
        if path:return path
    for path in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if Path(path).is_file():return path
    return None

def _png_size(path):
    data=path.read_bytes()[:24]
    if len(data)>=24 and data[:8]==b"\x89PNG\r\n\x1a\n": return struct.unpack(">II",data[16:24])
    return None

def render_page(workspace, session_directory, entry="index.html", viewport="desktop"):
    source=workspace.path(entry)
    if not source.is_file(): raise ValueError("Render entry file not found.")
    sizes={"desktop":(1440,1000),"mobile":(390,844)}
    if viewport not in sizes: raise ValueError("Viewport must be desktop or mobile.")
    browser=find_browser()
    if not browser:return {"ok":False,"available":False,"viewport":viewport,"entry":entry,"error":"Chromium/Chrome is not installed; deterministic visual checks can still run."}
    out=Path(session_directory)/"renders";out.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=out/f"{Path(entry).stem}-{viewport}.png";width,height=sizes[viewport]
    command=[browser,"--headless=new","--no-sandbox","--disable-gpu","--disable-dev-shm-usage","--disable-background-networking","--no-first-run","--disable-default-apps",f"--window-size={width},{height}",f"--screenshot={target}",source.resolve().as_uri()]
    result=subprocess.run(command,cwd=workspace.root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    if result.returncode!=0 or not target.is_file():return {"ok":False,"available":True,"viewport":viewport,"entry":entry,"error":("Browser render failed. "+result.stdout[-1200:]).strip()}
    actual=_png_size(target)
    return {"ok":True,"available":True,"viewport":viewport,"entry":entry,"requested_size":[width,height],"image_size":list(actual) if actual else None,"screenshot":str(target)}
