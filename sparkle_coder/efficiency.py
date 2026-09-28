"""Bound request copies while preserving exact, replayable local task history."""
import copy
import json
import re


PROFILE_VERSION = 2

SIMPLE_TOOL_NAMES = frozenset({
    "inspect_static_site", "inspect_setup", "request_input", "list_files", "read_file",
    "search_files", "write_file", "edit_file", "delete_file", "verify", "update_delivery",
})
WEB_TOOL_NAMES = frozenset({"web_search", "read_web_page"})
_WEB_NEEDED = re.compile(
    r"\b(?:internet|web\s+search|search\s+(?:the\s+)?web|online|latest|current|today|"
    r"documentation|docs|release\s+notes|changelog|official\s+site)\b", re.I
)


def needs_web(goal):
    return bool(_WEB_NEEDED.search(str(goal or "")))

_COMPLEX_TASK = re.compile(
    r"\b(?:fix|debug|bug|refactor|migrat\w*|integrat\w*|deploy|database|backend|api|auth|security|"
    r"production|multi[- ]?file|all\s+(?:bugs|issues|tests)|test\s+and\s+fix|existing\s+project)\b",
    re.I,
)
_MICRO_TASK = re.compile(
    r"\b(?:addition|add\s+two\s+numbers|hello\s+world|simple\s+(?:python\s+)?program|"
    r"basic\s+(?:python\s+)?program|small\s+(?:python\s+)?program|simple\s+calculator)\b",
    re.I,
)
_SIMPLE_WEB = re.compile(
    r"(?:\b(?:simple|basic|small)\b.{0,80}\b(?:landing\s+page|web\s*page|static\s+(?:site|page|website))\b|"
    r"\blanding\s+page\b|\bstatic\s+(?:site|page|website)\b)",
    re.I | re.S,
)


def task_profile(goal, *, has_project_brief=False):
    """Choose a conservative hard budget only for clearly small requests."""
    text = " ".join(str(goal or "").split())
    if not text or len(text) > 400 or has_project_brief or _COMPLEX_TASK.search(text):
        return {"version": PROFILE_VERSION, "name": "standard"}
    if _MICRO_TASK.search(text):
        return {"version": PROFILE_VERSION, "name": "micro", "max_steps": 5, "max_total_tokens": 24000,
                "max_tokens": 3072, "context_chars": 12000}
    if _SIMPLE_WEB.search(text):
        return {"version": PROFILE_VERSION, "name": "simple_web", "max_steps": 6, "max_total_tokens": 40000,
                "max_tokens": 6144, "context_chars": 14000}
    return {"version": PROFILE_VERSION, "name": "standard"}


def preview(text, limit):
    if len(text) <= limit:
        return text
    half = max(100, (limit - 160) // 2)
    return text[:half] + '\n[Result shortened for model context; full output stays in task history. Read a narrower range if needed.]\n' + text[-half:]


def compact_group(group, *, recent=False):
    completed = {m.get('tool_call_id') for m in group if m.get('role') == 'tool'}
    # Never put fake/placeholder source text into historical file-edit arguments. Models can
    # accidentally copy such strings into project files. Old, completed mutations become a
    # plain metadata-only exchange; current source must be obtained with read_file.
    edits = []
    unsafe_saved_body = False
    for message in group:
        for call in message.get('tool_calls', []):
            if call.get('id') not in completed:
                continue
            function = call.get('function', {})
            if function.get('name') not in ('write_file', 'edit_file', 'delete_file'):
                continue
            try:
                arguments = json.loads(function.get('arguments', '{}'))
            except (ValueError, TypeError):
                arguments = {}
            bodies = [arguments.get(field) for field in ('content', 'old_text', 'new_text')
                      if isinstance(arguments.get(field), str)]
            body_size = sum(len(value) for value in bodies)
            unsafe_saved_body = unsafe_saved_body or any(
                'Historical edit body omitted from this request' in value
                or 'Earlier completed file changes (metadata only)' in value for value in bodies)
            edits.append(f"{function.get('name')} {arguments.get('path', '(unknown path)')}"
                         + (f" ({body_size} source characters)" if body_size else ""))
    if edits and (not recent or unsafe_saved_body):
        return [{"role": "assistant", "content":
                 "Earlier completed file changes (metadata only): " + "; ".join(edits[:12])
                 + ". Source bodies are intentionally absent from model context; use read_file for current text."}]
    result = copy.deepcopy(group)
    for message in result:
        if message.get('role') == 'tool':
            text = message.get('content', '')
            limit = 6000 if recent else 1800
            if not isinstance(text, str) or len(text) <= limit:
                continue
            try:
                data = json.loads(text)
            except (ValueError, TypeError):
                data = None
            if isinstance(data, dict):
                for key in ('content', 'output', 'diff'):
                    if isinstance(data.get(key), str):
                        data[key] = preview(data[key], limit)
                data['context_note'] = 'Large output shortened for model context; full result is saved.'
                text = json.dumps(data, ensure_ascii=False)
            message['content'] = preview(text, limit + 700)
    return result
