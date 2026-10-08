"""Selective expert routing across software-product domains."""
import re
from .registry import builtin_registry
from ..engineering import DOMAINS

def _rx(pattern): return re.compile(r"\b(?:"+pattern+r")\b", re.I)

# Product/domain signals
_SITE=_rx(r"website|web\s?page|landing\s?page|homepage|portfolio|storefront|marketing\s+site|static\s+site")
_PHOTO=_rx(r"photography|photographer|photo\s+studio|portrait|wedding\s+photography|gallery")
_SAAS_MARKETING=_rx(r"saas\s+landing|software\s+landing|product\s+landing")
_RESTAURANT=_rx(r"restaurant|cafe|coffee\s+shop|bakery|bistro|hotel|hospitality")
_ECOM=_rx(r"e-?commerce|online\s+store|storefront|product\s+catalog|fashion\s+shop")
_AGENCY=_rx(r"agency|creative\s+studio|design\s+studio|marketing\s+studio|consultancy")
_REAL_ESTATE=_rx(r"real\s+estate|realtor|property\s+listing|homes\s+for\s+sale")
_PERSONAL=_rx(r"personal\s+portfolio|developer\s+portfolio|designer\s+portfolio|artist\s+portfolio|resume\s+website")

_LLM=_rx(r"llm|large\s+language\s+model|language\s+model|gpt|chatbot|text\s+generation|model\s+inference")
_AGENT=_rx(r"ai\s+agent|agentic|coding\s+agent|autonomous\s+agent|tool[- ]using\s+agent|multi[- ]agent")
_RAG=_rx(r"rag|retrieval[- ]augmented|knowledge\s+base|document\s+qa|semantic\s+retrieval")
_ML=_rx(r"machine\s+learning|ml|ml\s+model|training\s+pipeline|classification|regression\s+model|forecasting")
_DATA=_rx(r"data\s+pipeline|etl|elt|data\s+warehouse|data\s+lake|streaming\s+data|analytics\s+pipeline")
_VECTOR=_rx(r"vector\s+database|vector\s+search|embedding|embeddings|semantic\s+search")
_MULTIMODAL=_rx(r"multimodal|vision[- ]language|image\s+and\s+text|audio\s+model|speech\s+model")
_CV=_rx(r"computer\s+vision|object\s+detection|segmentation|ocr|image\s+classification|tracking")

_SAAS=_rx(r"saas|multi[- ]tenant\s+app|subscription\s+software|b2b\s+platform")
_MOBILE=_rx(r"mobile\s+app|android|ios|iphone\s+app|flutter|react\s+native|swiftui|jetpack\s+compose")
_DESKTOP=_rx(r"desktop\s+(?:app|application)|electron|tauri|windows\s+(?:app|application)|macos\s+(?:app|application)|linux\s+desktop")
_ROBOTICS=_rx(r"robot|robotics|ros|ros2|autonomous\s+vehicle|drone|manipulator|slam")
_EMBEDDED=_rx(r"embedded|firmware|microcontroller|arduino|esp32|stm32|iot|sensor\s+node")
_CONTROL=_rx(r"pid\s+control|control\s+system|motor\s+control|trajectory\s+control|feedback\s+control")
_GAME=_rx(r"game|unity|unreal|godot|gameplay|simulation\s+engine")

_DISTRIBUTED=_rx(r"distributed\s+system|microservices|consensus|distributed\s+cache|service\s+mesh")
_EVENT=_rx(r"event[- ]driven|event\s+bus|kafka|rabbitmq|pubsub|message\s+queue|consumer|producer")
_REALTIME=_rx(r"realtime|real[- ]time|websocket|server[- ]sent\s+events|sse|live\s+updates")
_CLOUD=_rx(r"cloud\s+architecture|aws|azure|gcp|cloudflare|kubernetes|serverless|lambda")
_OBSERVABILITY=_rx(r"observability|logging|metrics|tracing|opentelemetry|monitoring|alerting")
_RELIABILITY=_rx(r"sre|reliability|high\s+availability|failover|disaster\s+recovery|uptime|resilience")
_CICD=_rx(r"ci/cd|continuous\s+integration|continuous\s+deployment|github\s+actions|gitlab\s+ci|build\s+pipeline")

_PAYMENTS=_rx(r"payment|payments|billing|subscription|checkout|invoice|credits|wallet|stripe|upi")
_AUTH=_rx(r"auth|authentication|authorization|login|password|oauth|oidc|session|identity|signup|sign[- ]in")
_CLI=_rx(r"cli|command[- ]line|terminal\s+tool|command\s+line\s+tool")
_SDK=_rx(r"sdk|library|package|client\s+library|developer\s+library")
_INTEGRATION=_rx(r"integrate|integration|third[- ]party\s+api|external(?:\s+\w+){0,2}\s+api|webhook")
_SEARCH=_rx(r"search|recommendation|recommender|ranking|personalization")

# Language/stack signals
_PYTHON=_rx(r"python|django|flask|fastapi|pytest|poetry")
_JS=_rx(r"javascript|typescript|node(?:\.js)?|react|vue|svelte|next(?:\.js)?|vite|npm|pnpm|yarn")
_SYSTEMS=_rx(r"c\+\+|cpp|rust|embedded\s+c|cmake|cargo")
_GO=_rx(r"golang|go\s+(?:service|api|cli|sdk|package|program)|gin|fiber")
_JVM=_rx(r"java|kotlin|spring|spring\s+boot|ktor|gradle")
_DOTNET=re.compile(r"(?:\bC#|\bcsharp\b|(?<!\w)\.net\b|\bdotnet\b|\basp\.net\b|\bblazor\b)",re.I)

# Task/risk signals
_DEBUG=_rx(r"debug|bug|broken|fix|error|exception|traceback|failing|failure|not\s+working")
_TEST=_rx(r"test|tests|testing|regression|pytest|unittest|vitest|jest|playwright")
_BACKEND=_rx(r"backend|api|server|endpoint|rest|graphql|worker")
_DATABASE=_rx(r"database|sql|sqlite|postgres|postgresql|mysql|d1|schema|migration|query|index")
_SECURITY=_rx(r"security|secure|vulnerability|permission|secret|credential|csrf|xss|account\s+isolation")
_PERF=_rx(r"performance|slow|latency|optimi[sz]e|speed|memory\s+usage|token\s+usage|throughput")
_REFACTOR=_rx(r"refactor|cleanup|clean\s+up|simplify|restructure|technical\s+debt")
_DEPLOY=_rx(r"deploy|deployment|hosting|production|tunnel|dns|docker|systemd")
_REVIEW=_rx(r"code\s+review|review\s+the\s+code|audit\s+the\s+code|inspect\s+the\s+implementation")
_FRONTEND_APP=_rx(r"frontend|web\s+app|react|vue|svelte|component|client\s+state|browser\s+ui")
_NO_EXTERNAL=_rx(r"offline|no\s+internet|without\s+internet|local\s+assets\s+only|do\s+not\s+browse|don't\s+browse|no\s+web")
_LUXURY=_rx(r"luxury|premium|high[- ]end|editorial|minimal\s+luxury|boutique")
_MOTION=_rx(r"animation|animated|motion|interactive|microinteraction")
_BOOKING=_rx(r"book|booking|appointment|inquiry|enquiry|contact\s+form|reservation")
_MULTI=_rx(r"multi[- ]page|about\s+page|contact\s+page|gallery\s+page|services\s+page")

def select_skills(goal, *, task_profile="standard", limit=12, domains=()):
    text=" ".join(str(goal or "").split())
    chosen=[]
    def add(*names):
        known=builtin_registry()
        for name in names:
            if name in known and name not in chosen: chosen.append(name)

    # Shipping quality is a cross-product requirement, not a web-only concern.
    if re.search(r"\b(?:build|create|develop|design|implement|make|ship|finish|complete)\b", text, re.I):
        add("delivery_excellence")

    # Product-first expertise bundles.
    if _AGENT.search(text):
        add("agent_systems","llm_engineering","prompt_context_engineering","ai_evaluation",
            "backend_api_mastery","testing_mastery","security_mastery","reliability_sre")
    if _RAG.search(text):
        add("rag_mastery","vector_search","llm_engineering","prompt_context_engineering",
            "ai_evaluation","data_engineering","security_mastery","testing_mastery")
    elif _LLM.search(text):
        add("llm_engineering","prompt_context_engineering","ai_evaluation","testing_mastery")
    if _MULTIMODAL.search(text): add("multimodal_ai","llm_engineering","ai_evaluation")
    if _CV.search(text): add("computer_vision","ml_engineering","data_engineering","ai_evaluation","testing_mastery")
    if _ML.search(text): add("ml_engineering","data_engineering","testing_mastery")
    if _DATA.search(text): add("data_engineering","database_mastery","testing_mastery")
    if _VECTOR.search(text): add("vector_search","data_engineering")

    if _ROBOTICS.search(text):
        add("robotics_systems","control_systems","embedded_iot","realtime_systems",
            "systems_programming","reliability_sre","testing_mastery")
    else:
        if _CONTROL.search(text): add("control_systems","realtime_systems","testing_mastery")
        if _EMBEDDED.search(text): add("embedded_iot","systems_programming","testing_mastery")
    if _GAME.search(text): add("game_simulation","performance_engineering","testing_mastery")

    if _SAAS.search(text):
        add("saas_architecture","multi_tenant_systems","auth_identity","product_architecture",
            "backend_api_mastery","database_mastery","security_mastery","testing_mastery")
    if _MOBILE.search(text):
        add("mobile_app_mastery","product_architecture","product_ux","testing_mastery","security_mastery")
    if _DESKTOP.search(text):
        add("desktop_app_mastery","product_architecture","product_ux","testing_mastery")

    if _DISTRIBUTED.search(text): add("distributed_systems","reliability_sre","observability_mastery","testing_mastery")
    if _EVENT.search(text): add("event_driven_systems","distributed_systems","observability_mastery")
    if _REALTIME.search(text): add("realtime_systems","reliability_sre","testing_mastery")
    if _CLOUD.search(text): add("cloud_architecture","deployment_mastery","reliability_sre","observability_mastery")
    if _CICD.search(text): add("devops_ci_cd","deployment_mastery","testing_mastery")
    if _OBSERVABILITY.search(text): add("observability_mastery")
    if _RELIABILITY.search(text): add("reliability_sre","observability_mastery")

    if _PAYMENTS.search(text): add("payments_billing","database_mastery","backend_api_mastery","testing_mastery")
    if _AUTH.search(text): add("auth_identity","security_mastery","testing_mastery")
    if _CLI.search(text): add("cli_tooling","testing_mastery")
    if _SDK.search(text): add("sdk_library_design","testing_mastery")
    if _INTEGRATION.search(text): add("api_integration_mastery","testing_mastery","reliability_sre")
    if _SEARCH.search(text): add("search_recommendation","testing_mastery")

    # Stack/language expertise.
    if _PYTHON.search(text): add("python_mastery")
    if _JS.search(text): add("javascript_typescript_mastery")
    if _SYSTEMS.search(text): add("systems_programming")
    if _GO.search(text): add("go_services")
    if _JVM.search(text): add("jvm_kotlin_mastery")
    if _DOTNET.search(text): add("dotnet_mastery")

    # Cross-cutting engineering task expertise.
    if _DEBUG.search(text): add("debugging_mastery","testing_mastery")
    if _BACKEND.search(text): add("backend_api_mastery","testing_mastery")
    if _DATABASE.search(text): add("database_mastery","testing_mastery")
    if _SECURITY.search(text): add("security_mastery","testing_mastery")
    if _PERF.search(text): add("performance_engineering")
    if _REFACTOR.search(text): add("refactoring_mastery","testing_mastery")
    if _DEPLOY.search(text): add("deployment_mastery")
    if _REVIEW.search(text): add("code_review_mastery")
    if _FRONTEND_APP.search(text): add("frontend_architecture","product_ux")
    if _TEST.search(text): add("testing_mastery")

    # Visual marketing/portfolio sites remain a distinct product class.
    web_task=bool(task_profile=="simple_web" or _SITE.search(text))
    if web_task:
        web=[]
        def wadd(*names):
            known=builtin_registry()
            for name in names:
                if name in known and name not in web:web.append(name)
        domain=None;image_heavy=False
        for pattern,name,images in ((_PHOTO,"photography_portfolio",True),(_RESTAURANT,"restaurant_hospitality",True),
                                    (_ECOM,"ecommerce_storefront",True),(_AGENCY,"agency_portfolio",True),
                                    (_REAL_ESTATE,"real_estate",True),(_PERSONAL,"personal_portfolio",True),
                                    (_SAAS,"saas_landing",False)):
            if pattern.search(text):domain=name;image_heavy=images;break
        if domain=="photography_portfolio":
            wadd("photography_portfolio","composition_mastery","typography_mastery","image_art_direction","portfolio_curation")
            if not _NO_EXTERNAL.search(text):wadd("asset_sourcing")
            wadd("responsive_web","conversion_journey","content_integrity","visual_qa")
        elif domain:
            wadd(domain,"composition_mastery","typography_mastery")
            if image_heavy and not _NO_EXTERNAL.search(text):wadd("image_art_direction","asset_sourcing")
            wadd("conversion_journey","content_integrity","responsive_web","visual_qa")
        else:
            wadd("static_web","visual_design","composition_mastery","typography_mastery",
                 "content_integrity","responsive_web","accessibility_mastery","visual_qa")
        if _LUXURY.search(text):wadd("luxury_branding")
        if _MOTION.search(text):wadd("interaction_polish")
        if _BOOKING.search(text):wadd("forms_booking")
        if _MULTI.search(text):wadd("information_architecture")
        # Marketing/site art direction leads; engineering specialists fill remaining slots.
        chosen=web+[name for name in chosen if name not in web]

    # General product work gets architecture expertise if no stronger domain bundle filled the task.
    if not chosen and re.search(r"\b(?:build|create|develop|design|implement)\b",text,re.I):
        add("product_architecture","testing_mastery")

    # Supplement prompt-selected expertise with evidence from the actual project.
    # Keep explicit user intent first and preserve the specialized web route.
    if not web_task and domains:
        domain_skills = {identity: skills for identity, _, _, _, skills, _ in DOMAINS}
        for identity in domains:
            add(*domain_skills.get(identity, ()))

    return chosen[:max(0,int(limit))]
