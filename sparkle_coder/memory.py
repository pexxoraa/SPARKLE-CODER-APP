"""Small retrieval-oriented project memory stored outside model history."""

import re
from datetime import datetime, timezone

_WORD = re.compile(r"[a-z0-9_./-]{3,}", re.I)
_STOP = frozenset({"the","and","for","with","from","that","this","into","your","user","project",
                   "file","files","task","use","using","was","are","has","have","not","but"})


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_store():
    return {"version": 2, "facts": {}, "tasks": [], "files": {}}


def normalize_store(value):
    if not isinstance(value, dict):
        return empty_store()
    if value.get("version") == 2:
        store = empty_store()
        store["facts"] = value.get("facts") if isinstance(value.get("facts"), dict) else {}
        store["tasks"] = value.get("tasks") if isinstance(value.get("tasks"), list) else []
        store["files"] = value.get("files") if isinstance(value.get("files"), dict) else {}
        return store
    # v1 was a flat {key: {fact, source, updated}} mapping.
    facts = {str(k): v for k, v in value.items()
             if isinstance(v, dict) and isinstance(v.get("fact"), str)}
    return {"version": 2, "facts": facts, "tasks": [], "files": {}}


def terms(text):
    return {word.lower() for word in _WORD.findall(str(text or "")) if word.lower() not in _STOP}


def _score(query_terms, text):
    item_terms = terms(text)
    if not query_terms or not item_terms:
        return 0
    return len(query_terms & item_terms) * 5 + len({q for q in query_terms for t in item_terms
                                                    if len(q) >= 5 and (q in t or t in q)})


def recall(store, query, limit=8):
    """Return a small relevant slice; never dump the whole memory file into a prompt."""
    limit = max(1, min(12, int(limit)))
    query_terms = terms(query)
    candidates = []
    for key, item in store.get("facts", {}).items():
        if not isinstance(item, dict):
            continue
        text = " ".join((str(key), str(item.get("fact", "")), str(item.get("source", ""))))
        candidates.append((_score(query_terms, text), str(item.get("updated", "")),
                           {"kind": "fact", "key": key, "fact": str(item.get("fact", ""))[:1200],
                            "source": str(item.get("source", ""))[:300],
                            "updated": item.get("updated")}))
    for item in store.get("tasks", []):
        if not isinstance(item, dict):
            continue
        text = " ".join((str(item.get("goal", "")), str(item.get("summary", "")),
                         " ".join(item.get("files", []) if isinstance(item.get("files"), list) else [])))
        candidates.append((_score(query_terms, text), str(item.get("updated", "")),
                           {"kind": "task", "goal": str(item.get("goal", ""))[:500],
                            "status": item.get("status"), "summary": str(item.get("summary", ""))[:1000],
                            "files": list(item.get("files", []))[:20], "updated": item.get("updated")}))
    for path, item in store.get("files", {}).items():
        if not isinstance(item, dict):
            continue
        score = _score(query_terms, path + " " + str(item.get("task", "")))
        if score:
            candidates.append((score, str(item.get("updated", "")),
                               {"kind": "file", "path": path, "sha256": item.get("sha256"),
                                "size": item.get("size"), "updated": item.get("updated")}))
    relevant = [row for row in candidates if row[0] > 0]
    relevant.sort(key=lambda row: (row[0], row[1]), reverse=True)
    if not relevant:
        # A single recent task gives continuity without replaying an entire project history.
        tasks = [item for item in store.get("tasks", []) if isinstance(item, dict)]
        if tasks:
            item = sorted(tasks, key=lambda x: str(x.get("updated", "")), reverse=True)[0]
            return [{"kind": "task", "goal": str(item.get("goal", ""))[:500],
                     "status": item.get("status"), "summary": str(item.get("summary", ""))[:1000],
                     "files": list(item.get("files", []))[:20], "updated": item.get("updated")}]
        return []
    return [row[2] for row in relevant[:limit]]


def remember_fact(store, key, fact, source):
    facts = store.setdefault("facts", {})
    if len(facts) >= 100 and key not in facts:
        raise ValueError("Project fact memory is full.")
    facts[key] = {"fact": fact, "source": source, "updated": timestamp()}


def record_file(store, path, digest, size, task):
    files = store.setdefault("files", {})
    files[path] = {"sha256": digest, "size": size, "task": str(task or "")[:300], "updated": timestamp()}
    if len(files) > 300:
        oldest = sorted(files, key=lambda key: str(files[key].get("updated", "")))[:len(files)-300]
        for key in oldest:
            files.pop(key, None)


def remember_task(store, session_id, goal, status, summary, files):
    tasks = [item for item in store.setdefault("tasks", [])
             if not isinstance(item, dict) or item.get("session_id") != session_id]
    tasks.append({"session_id": session_id, "goal": str(goal or "")[:500], "status": status,
                  "summary": str(summary or "")[:1200], "files": list(dict.fromkeys(files))[:30],
                  "updated": timestamp()})
    store["tasks"] = tasks[-40:]
