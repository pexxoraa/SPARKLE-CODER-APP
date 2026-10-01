"""Deterministic, low-token skill routing."""
import re
from .registry import builtin_registry
_WEB=re.compile(r"\b(?:website|web\s?page|landing\s?page|homepage|portfolio|html|css|frontend|storefront)\b",re.I)
_STATIC=re.compile(r"\b(?:static|landing\s?page|website|homepage|portfolio|storefront)\b",re.I)
_PHOTO=re.compile(r"\b(?:photo(?:graphy|grapher|studio)?|photographer|portrait|wedding|camera|gallery)\b",re.I)
_SAAS=re.compile(r"\b(?:saas|software|app|platform|developer tool|productivity)\b",re.I)
_RESTAURANT=re.compile(r"\b(?:restaurant|cafe|coffee shop|bakery|bistro|bar|hotel|hospitality)\b",re.I)
_ECOM=re.compile(r"\b(?:e-?commerce|online store|storefront|shop|product catalog|fashion store)\b",re.I)
_AGENCY=re.compile(r"\b(?:agency|creative studio|design studio|marketing studio|consultancy)\b",re.I)
_REAL_ESTATE=re.compile(r"\b(?:real estate|realtor|property|properties|homes for sale)\b",re.I)
_PERSONAL=re.compile(r"\b(?:personal portfolio|developer portfolio|designer portfolio|artist portfolio|resume website|cv website)\b",re.I)
_NO_EXTERNAL=re.compile(r"\b(?:offline|no internet|without internet|local assets only|do not browse|don't browse|no web)\b",re.I)

def select_skills(goal, *, task_profile="standard", limit=6):
    text=" ".join(str(goal or "").split()); chosen=[]
    def add(name):
        if name in builtin_registry() and name not in chosen: chosen.append(name)
    if not (task_profile=="simple_web" or _WEB.search(text) or _STATIC.search(text)): return chosen
    domain=None; image_heavy=False
    for pattern,name,images in ((_PHOTO,"photography_portfolio",True),(_RESTAURANT,"restaurant_hospitality",True),
                                (_ECOM,"ecommerce_storefront",True),(_AGENCY,"agency_portfolio",True),
                                (_REAL_ESTATE,"real_estate",True),(_PERSONAL,"personal_portfolio",True),
                                (_SAAS,"saas_landing",False)):
        if pattern.search(text): domain=name;image_heavy=images;break
    if domain:
        add("visual_design");add(domain)
        if image_heavy and not _NO_EXTERNAL.search(text): add("asset_sourcing")
        add("typography_image_strategy");add("responsive_web");add("visual_qa")
    else:
        add("static_web");add("visual_design");add("typography_image_strategy")
        add("frontend_quality_baseline");add("responsive_web");add("visual_qa")
    return chosen[:max(0,limit)]
