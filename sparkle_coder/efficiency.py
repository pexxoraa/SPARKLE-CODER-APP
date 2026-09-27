"""Bound request copies while preserving exact, replayable local task history."""
import copy
import json
import re


SIMPLE_TOOL_NAMES = frozenset({
    "inspect_static_site", "inspect_setup", "request_input", "list_files", "read_file",
    "search_files", "write_file", "edit_file", "delete_file", "verify", "update_delivery",
})

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
    r"(?:\b(?:simple|basic|small)\b.{0,80}\b(?:landing\s+page|web\s*page|static\s+(?:site|page))\b|"
    r"\blanding\s+page\b)",
    re.I | re.S,
)


def task_profile(goal, *, has_project_brief=False):
    """Choose a conservative hard budget only for clearly small requests."""
    text = " ".join(str(goal or "").split())
    if not text or len(text) > 400 or has_project_brief or _COMPLEX_TASK.search(text):
        return {"name": "standard"}
    if _MICRO_TASK.search(text):
        return {"name": "micro", "max_steps": 5, "max_total_tokens": 24000,
                "max_tokens": 3072, "context_chars": 12000}
    if _SIMPLE_WEB.search(text):
        return {"name": "simple_web", "max_steps": 6, "max_total_tokens": 40000,
                "max_tokens": 6144, "context_chars": 14000}
    return {"name": "standard"}


def preview(text, limit):
    if len(text) <= limit:
        return text
    half = max(100, (limit - 160) // 2)
    return text[:half] + '\n[Result shortened for model context; full output stays in task history. Read a narrower range if needed.]\n' + text[-half:]


def compact_group(group, *, recent=False):
    result = copy.deepcopy(group)
    completed = {m.get('tool_call_id') for m in group if m.get('role') == 'tool'}
    for message in result:
        for call in message.get('tool_calls', []):
            if call.get('id') not in completed:
                continue
            function = call.get('function', {})
            fields = (() if recent else
                      {'write_file': ('content',), 'edit_file': ('old_text', 'new_text')}.get(function.get('name'), ()))
            if not fields:
                continue
            try:
                arguments = json.loads(function['arguments'])
            except (ValueError, TypeError):
                continue
            for field in fields:
                value = arguments.get(field)
                if isinstance(value, str) and len(value) > 600:
                    arguments[field] = ('[Historical edit body omitted from this request. The tool result records its outcome. '
                                        f'The original {len(value)} characters remain in saved history; read the current file before editing.]')
            function['arguments'] = json.dumps(arguments, ensure_ascii=False)
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
