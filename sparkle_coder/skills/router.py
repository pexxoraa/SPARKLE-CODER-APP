"""Deterministic, low-token skill routing."""
import re
from .registry import builtin_registry

_WEB=re.compile(r"\b(?:website|web\s?page|web\s?app|landing\s?page|homepage|portfolio|html|css|frontend|storefront|react|vue|svelte)\b",re.I)
_STATIC=re.compile(r"\b(?:static|landing\s?page|website|homepage|portfolio|storefront)\b",re.I)
_PHOTO=re.compile(r"\b(?:photo(?:graphy|grapher|studio)?|photographer|portrait|wedding|camera|gallery)\b",re.I)
_SAAS=re.compile(r"\b(?:saas|software|app|platform|developer tool|productivity)\b",re.I)
_RESTAURANT=re.compile(r"\b(?:restaurant|cafe|coffee shop|bakery|bistro|bar|hotel|hospitality)\b",re.I)
_ECOM=re.compile(r"\b(?:e-?commerce|online store|storefront|shop|product catalog|fashion store)\b",re.I)
_AGENCY=re.compile(r"\b(?:agency|creative studio|design studio|marketing studio|consultancy)\b",re.I)
_REAL_ESTATE=re.compile(r"\b(?:real estate|realtor|property|properties|homes for sale)\b",re.I)
_PERSONAL=re.compile(r"\b(?:personal portfolio|developer portfolio|designer portfolio|artist portfolio|resume website|cv website)\b",re.I)
_NO_EXTERNAL=re.compile(r"\b(?:offline|no internet|without internet|local assets only|do not browse|don't browse|no web)\b",re.I)
_LUXURY=re.compile(r"\b(?:luxury|premium|high[- ]end|editorial|minimal luxury|boutique)\b",re.I)
_MOTION=re.compile(r"\b(?:animation|animated|motion|interactive|microinteraction|micro-interaction)\b",re.I)
_BOOKING=re.compile(r"\b(?:book|booking|appointment|inquiry|enquiry|contact form|reservation)\b",re.I)
_MULTI=re.compile(r"\b(?:multi[- ]page|about page|contact page|gallery page|services page)\b",re.I)

_DEBUG=re.compile(r"\b(?:debug|bug|broken|fix|error|exception|traceback|failing|failure|doesn'?t work|not working)\b",re.I)
_TEST=re.compile(r"\b(?:test|tests|testing|regression|pytest|unittest|vitest|jest|playwright)\b",re.I)
_PYTHON=re.compile(r"\b(?:python|django|flask|fastapi|pytest|pip|poetry)\b",re.I)
_JS=re.compile(r"\b(?:javascript|typescript|node(?:\.js)?|react|vue|svelte|next(?:\.js)?|vite|npm|pnpm|yarn)\b",re.I)
_BACKEND=re.compile(r"\b(?:backend|api|server|endpoint|rest|graphql|webhook|worker)\b",re.I)
_DATABASE=re.compile(r"\b(?:database|sql|sqlite|postgres|postgresql|mysql|d1|schema|migration|query|index)\b",re.I)
_SECURITY=re.compile(r"\b(?:security|auth|authentication|authorization|csrf|xss|permission|secret|credential|session|account isolation)\b",re.I)
_PERF=re.compile(r"\b(?:performance|slow|latency|optimi[sz]e|speed|memory usage|token usage|too many tokens)\b",re.I)
_REFACTOR=re.compile(r"\b(?:refactor|cleanup|clean up|simplify|restructure|technical debt)\b",re.I)
_DEPLOY=re.compile(r"\b(?:deploy|deployment|cloudflare|docker|systemd|hosting|production|tunnel|dns|ci/cd|github actions)\b",re.I)
_REVIEW=re.compile(r"\b(?:code review|review the code|audit the code|inspect the implementation)\b",re.I)
_FRONTEND_APP=re.compile(r"\b(?:frontend|web app|react|vue|svelte|component|client state|browser ui)\b",re.I)

def select_skills(goal, *, task_profile="standard", limit=10):
    text=" ".join(str(goal or "").split());chosen=[]
    def add(name):
        if name in builtin_registry() and name not in chosen:chosen.append(name)

    # Engineering expertise is independent of visual-web routing.
    if _DEBUG.search(text):add("debugging_mastery")
    if _PYTHON.search(text):add("python_mastery")
    if _JS.search(text):add("javascript_typescript_mastery")
    if _BACKEND.search(text):add("backend_api_mastery")
    if _DATABASE.search(text):add("database_mastery")
    if _SECURITY.search(text):add("security_mastery")
    if _PERF.search(text):add("performance_engineering")
    if _REFACTOR.search(text):add("refactoring_mastery")
    if _DEPLOY.search(text):add("deployment_mastery")
    if _REVIEW.search(text):add("code_review_mastery")
    if _FRONTEND_APP.search(text):add("frontend_architecture")
    if _TEST.search(text) or any(x in chosen for x in ("debugging_mastery","backend_api_mastery","database_mastery","security_mastery","refactoring_mastery")):
        add("testing_mastery")

    web_task=bool(task_profile=="simple_web" or _WEB.search(text) or _STATIC.search(text))
    if not web_task:return chosen[:max(0,limit)]

    domain=None;image_heavy=False
    for pattern,name,images in ((_PHOTO,"photography_portfolio",True),(_RESTAURANT,"restaurant_hospitality",True),
                                (_ECOM,"ecommerce_storefront",True),(_AGENCY,"agency_portfolio",True),
                                (_REAL_ESTATE,"real_estate",True),(_PERSONAL,"personal_portfolio",True),
                                (_SAAS,"saas_landing",False)):
        if pattern.search(text):domain=name;image_heavy=images;break

    web=[]
    def wadd(name):
        if name in builtin_registry() and name not in web:web.append(name)
    if domain=="photography_portfolio":
        for name in ("photography_portfolio","composition_mastery","typography_mastery","image_art_direction",
                     "portfolio_curation"):wadd(name)
        if not _NO_EXTERNAL.search(text):wadd("asset_sourcing")
        for name in ("responsive_web","conversion_journey","content_integrity","visual_qa"):wadd(name)
    elif domain:
        wadd(domain);wadd("composition_mastery");wadd("typography_mastery")
        if image_heavy and not _NO_EXTERNAL.search(text):wadd("image_art_direction");wadd("asset_sourcing")
        wadd("conversion_journey");wadd("content_integrity");wadd("responsive_web");wadd("visual_qa")
    else:
        for name in ("static_web","visual_design","composition_mastery","typography_mastery",
                     "content_integrity","responsive_web","accessibility_mastery","visual_qa"):wadd(name)

    if _LUXURY.search(text):wadd("luxury_branding")
    if _MOTION.search(text):wadd("interaction_polish")
    if _BOOKING.search(text):wadd("forms_booking")
    if _MULTI.search(text):wadd("information_architecture")
    if _FRONTEND_APP.search(text):wadd("frontend_architecture")

    # Marketing/domain pages lead with art direction; engineering-oriented frontends lead with engineering expertise.
    creative_first=bool(domain or task_profile=="simple_web" or _STATIC.search(text))
    combined=(web+[name for name in chosen if name not in web]) if creative_first else (chosen+[name for name in web if name not in chosen])
    return combined[:max(0,limit)]
