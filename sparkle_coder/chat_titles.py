"""Deterministic, no-model-cost conversation titles for saved coding tasks."""
import re


def chat_title(goal: str) -> str:
    text = re.sub(r'https?://\S+', ' ', str(goal or ''))
    text = re.sub(r'[`*_#\[\]{}<>]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.split(r'(?<=[.!?])\s+|\s*[;\n]\s*', text, maxsplit=1)[0]
    text = re.sub(r'^(?:hey|hi|please|can you|could you|would you|i want you to|i need you to|i want to|help me(?: to)?|let\s+us)\s+', '', text, flags=re.I)
    text = re.sub(r'^(?:make|create|build|develop|generate|write|add|implement|design|please build|explain|tell me about|what are|what is|how to|help with|fix|debug|update|modify|improve|review|inspect|check|test|analyze)\s+', '', text, flags=re.I)
    text = re.sub(r'^(?:me\s+)?(?:a|an|the|this|some)\s+', '', text, flags=re.I)
    words = text.split()
    if not words:
        return 'New conversation'
    text = ' '.join(words[:8]).strip(' \t.,:;!?-')[:62].rstrip(' -.,:;')
    return text[0].upper() + text[1:] if text else 'New conversation'
