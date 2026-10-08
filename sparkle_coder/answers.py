"""User-facing reply formatting. Preserve raw model history and exact tool data."""
import re


_EXPLICIT_FORMAT = re.compile(
    r"\b(?:in|as|using|with|formatted as|format as|return|output|respond in|give me)\s+"
    r"(?:a\s+|an\s+|the\s+)?(?:markdown|md|json|yaml|xml|html|csv|latex|"
    r"code\s+(?:block|fence|snippet|example)|table|mermaid|diff)\b"
    r"|\b(?:show|write|provide|give|generate)\s+(?:me\s+)?"
    r"(?:a\s+|an\s+|the\s+)?(?:code(?:\s+(?:example|snippet|block))?|"
    r"(?:python|javascript|typescript|java|rust|go|bash|shell|sql|html|css)\s+"
    r"(?:code|function|script|program|example)|markdown\s+table)\b",
    re.IGNORECASE,
)
_MD_SEPARATOR = re.compile(r"^:?-{3,}:?$")


def explicit_format_requested(user_request: str) -> bool:
    """Do not discard intentionally requested Markdown, code or structured output."""
    return bool(_EXPLICIT_FORMAT.search(str(user_request or "")))


def plain_discussion_text(text: str) -> str:
    """Turn decorative Markdown into readable plain text without changing code content."""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    output = []
    fenced = False
    for raw in value.split("\n"):
        stripped = raw.strip()
        if re.match(r"^\s{0,3}(`{3,}|~{3,})", raw):
            fenced = not fenced
            continue
        if fenced:
            output.append(raw.rstrip())
            continue
        line = raw
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s{0,3}>\s?", "", line)
        line = re.sub(r"^\s*[-*+]\s+\[([ xX])\]\s+", lambda m: "Done: " if m[1].lower() == "x" else "To do: ", line)
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*(\d+)[.)]\s+", lambda m: "Step " + m[1] + ": ", line)
        if re.fullmatch(r"\s*(?:[-_*]\s*){3,}", line):
            continue
        line = re.sub(r"!\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1 (\2)", line)
        # Inline code is content, not emphasis: protect identifiers such as
        # `__init__` and `_private_` from underscore decoration cleanup.
        inline = []
        def protect(match):
            inline.append(match[1])
            return "\x01" + str(len(inline) - 1) + "\x02"
        line = re.sub(r"`([^`\n]+)`", protect, line)
        line = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", line)
        line = re.sub(r"(?<!\w)__([^_\n]+)__(?!\w)", r"\1", line)
        line = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", line)
        line = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", line)
        line = re.sub(r"\x01(\d+)\x02", lambda m: inline[int(m[1])], line)
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and all(_MD_SEPARATOR.fullmatch(cell) for cell in cells):
                continue
            line = " — ".join(cell for cell in cells if cell)
        output.append(line.rstrip())
    # Remove only adjacent repeated paragraphs: do not discard deliberately
    # repeated log lines, code, references or independent observations.
    paragraphs = re.split(r"\n\s*\n", "\n".join(output))
    unique = []
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if not unique or paragraph.casefold() != unique[-1].casefold():
            unique.append(paragraph)
    return "\n\n".join(unique).strip()


def display_reply(text: str, user_request: str = "") -> str:
    return str(text or "") if explicit_format_requested(user_request) else plain_discussion_text(text)
