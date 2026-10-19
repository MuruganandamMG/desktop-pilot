"""Read-only, on-demand search over explicitly granted Markdown folders."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import stat


@dataclass(frozen=True)
class MemoryExcerpt:
    path: str
    text: str
    modified_at: str
    provenance: str


def _ordinary(path: Path, *, allow_hidden: bool = False) -> bool:
    try:
        info = path.lstat()
        blocked = 0x400 if allow_hidden else 0x402
        return not (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & blocked)
    except OSError:
        return False


class MemoryStore:
    def __init__(self, vault: Path, granted_folders: set[str]):
        vault = Path(vault).absolute()
        # Windows marks drive roots/AppData hidden; only reparse ancestors are unsafe.
        if not vault.is_dir() or not _ordinary(vault) or any(not _ordinary(parent, allow_hidden=True) for parent in vault.parents):
            raise ValueError("Vault is unavailable or contains a hidden/reparse path")
        if any(not name or name.startswith(".") or len(Path(name).parts) != 1
               or Path(name).is_absolute() or ":" in name or "/" in name or "\\" in name
               for name in granted_folders):
            raise ValueError("Grant a named top-level vault folder")
        self.vault = vault.resolve()
        self.grants = frozenset(granted_folders)

    def search(self, query: str, limit: int = 5) -> list[MemoryExcerpt]:
        if type(query) is not str or len(query) > 2000 or type(limit) is not int:
            raise ValueError("Invalid memory query")
        terms = set(re.findall(r"\w+", query.casefold()))
        if not terms or limit < 1:
            return []
        matches = []
        examined = 0
        for grant in sorted(self.grants):
            root = self.vault / grant
            if not _ordinary(root) or not root.is_dir():
                continue
            for directory, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = sorted(name for name in dirs if not name.startswith(".") and _ordinary(Path(directory) / name))
                for name in sorted(names):
                    examined += 1
                    if examined > 1000:
                        raise ValueError("Memory search exceeds 1,000 files; grant a smaller folder")
                    path = Path(directory) / name
                    if name.startswith(".") or path.suffix.lower() != ".md" or not _ordinary(path):
                        continue
                    try:
                        before = path.stat()
                        if not stat.S_ISREG(before.st_mode) or before.st_size > 262144:
                            continue
                        if not path.resolve().is_relative_to(self.vault):
                            continue
                        with path.open("rb") as source:
                            opened = os.fstat(source.fileno())
                            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                                continue
                            raw = source.read(262145)
                        after = path.stat()
                        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                            continue
                        if len(raw) > 262144 or not _ordinary(path):
                            continue
                        text = raw.decode("utf-8-sig")
                    except (OSError, UnicodeError):
                        continue
                    relative = path.relative_to(self.vault).as_posix()
                    score = sum(3 * (term in relative.casefold()) + (term in text.casefold()) for term in terms)
                    if score:
                        provenance = "unspecified"
                        marker = re.search(r"(?im)^Provenance:\s*(user-stated|observed|inferred)\b", text)
                        if marker:
                            provenance = marker[1].lower()
                        positions = [text.casefold().find(term) for term in terms if term in text.casefold()]
                        start = max(0, min(positions) - 500) if positions else 0
                        excerpt = MemoryExcerpt(relative, text[start:start + 12000], datetime.fromtimestamp(after.st_mtime, timezone.utc).isoformat(), provenance)
                        matches.append((-score, relative, excerpt))
        selected, budget = [], 32000
        for _, _, excerpt in sorted(matches)[:min(limit, 5)]:
            bounded = MemoryExcerpt(excerpt.path, excerpt.text[:budget], excerpt.modified_at, excerpt.provenance)
            selected.append(bounded)
            budget -= len(bounded.text)
            if budget <= 0:
                break
        return selected
