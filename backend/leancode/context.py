import hashlib
import json
import os
from pathlib import Path

from .policy import PolicyError

IGNORED = {"node_modules", "__pycache__", "dist", "build", "vendor", "venv", ".venv"}
EXTENSIONS = {".py", ".md", ".txt", ".toml", ".json", ".yaml", ".yml", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".csv"}


class Repository:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)

    def path(self, relative):
        path = Path(relative)
        if path.is_absolute() or not path.parts or any(p in {".", ".."} or p.startswith(".") or p in IGNORED for p in path.parts):
            raise PolicyError("Hidden, generated, or out-of-workspace paths are forbidden")
        if path.suffix not in EXTENSIONS or any(s in path.name.lower() for s in ("secret", "credential", "private_key")):
            raise PolicyError("File type or sensitive path is not allowed")
        candidate = self.root
        for part in path.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise PolicyError("Symlinks cannot be read, edited, or mounted")
        if not candidate.resolve().is_relative_to(self.root):
            raise PolicyError("Path escapes repository")
        if candidate.exists() and (not candidate.is_file() or candidate.stat().st_nlink != 1):
            raise PolicyError("Only regular, non-hardlinked files are allowed")
        return candidate

    def inventory(self):
        files = []
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in IGNORED
                             and not (Path(directory) / d).is_symlink())
            for name in sorted(names):
                relative = str((Path(directory) / name).relative_to(self.root))
                try:
                    validated = self.path(relative)
                    if validated.is_file():
                        files.append(relative)
                except PolicyError:
                    continue
                if len(files) > 500:
                    raise PolicyError("MVP supports up to 500 eligible files; select a smaller repository")
        return sorted(files)

    def text(self, relative):
        path = self.path(relative)
        if not path.exists():
            raise PolicyError("File does not exist")
        if path.stat().st_size > 96_000:
            raise PolicyError("File exceeds 96 KB read limit")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise PolicyError("Only UTF-8 text files are supported") from exc

    def read(self, relative, start=1, end=160):
        if not 1 <= start <= end or end - start >= 200:
            raise PolicyError("Read at most 200 lines with valid line numbers")
        text = self.text(relative)
        lines = text.splitlines()
        excerpt = "\n".join(f"{i}: {lines[i-1]}" for i in range(start, min(end, len(lines)) + 1))
        return {"path": relative, "hash": self.hash(relative), "start": start, "end": end,
                "content": excerpt[:16_000], "clipped": len(excerpt) > 16_000 or end < len(lines)}

    def hash(self, relative):
        path = self.path(relative)
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    def snapshot(self):
        return {path: self.hash(path) for path in self.inventory()}

    def search(self, query):
        results = []
        for path in self.inventory():
            try:
                lines = self.text(path).splitlines()
            except PolicyError:
                continue
            for index, line in enumerate(lines, 1):
                if query.casefold() in line.casefold():
                    results.append({"path": path, "line": index, "text": line[:300]})
                    if len(results) == 30:
                        return {"matches": results, "clipped": True}
        return {"matches": results, "clipped": False}


MAX_CONTEXT_BYTES = 48_000


def context_packet(session, repo):
    state = session["state"]
    packet = {"task": session["task"], "files": repo.inventory(),
              "remaining_turns": 12 - state.get("turns", 0)}
    history = state.get("history", [])
    if state.get("mode") == "baseline":
        packet["source"] = {path: repo.text(path) for path in repo.inventory()}
        packet["history"] = history
        if len(json.dumps(packet).encode()) > MAX_CONTEXT_BYTES:
            raise PolicyError("Baseline exceeds context limit; benchmark a smaller repository without truncation")
        return packet

    # Keep source once, with a hash; stale excerpts must never stand in for current code.
    memory = []
    for cached in state.get("read_cache", {}).values():
        if repo.hash(cached["path"]) == cached["hash"]:
            memory.append(cached)
    compact = []
    for entry in history[-6:]:
        if entry.get("op") == "read":
            result = entry["result"]
            compact.append({"op": "read", "path": result["path"], "start": result["start"], "end": result["end"]})
        else:
            item = dict(entry)
            result = item.get("result")
            if isinstance(result, dict) and len(result.get("output", "")) > 3000:
                item["result"] = {**result, "output": result["output"][:1500] + "\n[output clipped]\n" + result["output"][-1500:]}
            compact.append(item)
    packet.update(history=compact, inspected_code=memory,
                  verification={"edits": state.get("edits", 0), "tests_passed_on_current_files":
                                bool(state.get("verified_snapshot")) and state["verified_snapshot"] == repo.snapshot()})
    omitted = []
    while len(json.dumps(packet).encode()) > MAX_CONTEXT_BYTES and memory:
        old = memory.pop(0)
        omitted.append({"path": old["path"], "start": old["start"], "end": old["end"]})
        packet["omitted_reads"] = omitted
    while len(json.dumps(packet).encode()) > MAX_CONTEXT_BYTES and len(compact) > 2:
        compact.pop(0)
    if len(json.dumps(packet).encode()) > MAX_CONTEXT_BYTES:
        raise PolicyError("Required task context exceeds the context limit; narrow the task")
    return packet
