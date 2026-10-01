# Visual QA Mastery
Before completion on any creative/static web task, run `inspect_visual_site`. Treat a failing deterministic gate as unfinished work, not a suggestion. The audit covers linked pages, broken local references, placeholder imagery, responsive intent, typography defaults, stale dates, unfinished secondary pages, photography image prominence, and other beginner-pattern failures.

For image-led work, inspect the rendered desktop and mobile captures, plus the important secondary visual page when available. Ask: does the first viewport communicate hierarchy immediately? Is there one clear focal point? Do typography, whitespace and image crops feel art-directed? Does mobile preserve the idea rather than just stack blocks? Does every secondary page look like the same designed product?

Reject completion when there are blocking findings such as placeholder/dummy imagery, missing local scripts/styles/images, no real photography on a photography homepage, insufficient portfolio imagery, default creative-site typography, fake placeholder identities, non-working forms presented as functional, or visually untreated linked pages.

Warnings still require judgment. Generic copy, equal-card repetition, hotlinked imagery and unverifiable claims should normally be fixed for a polished creative site unless the project/user explicitly justifies them.

Use `render_page` for a focused re-check after edits. Make at most two evidence-driven polish passes: fix the highest-impact composition/type/image issues first, then verify. Do not declare success because the HTML is valid while the rendered result still looks generic.
