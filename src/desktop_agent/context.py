"""Bound and redact granted context before preview or transmission."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Source:
    id: str
    text: str


@dataclass(frozen=True)
class ContextBundle:
    text: str
    sources: tuple[str, ...]


_SECRETS = re.compile(
    r"(?i)(?:authorization\s*:\s*bearer\s+)[^\s]+"
    r'''|["']?(?:api[_-]?key|password|secret|token)["']?\s*[=:]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;}]+)'''
    r"|\bgh[pousr]_[A-Za-z0-9_]{20,}\b"
    r"|\bAIza[A-Za-z0-9_-]{30,}\b"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
)


def redact(text: str) -> str:
    return _SECRETS.sub("[REDACTED]", text)


def prepare_context(sources: list[Source], grants: set[str]) -> ContextBundle:
    parts, included = [], []
    remaining = 32000
    for source in sources:
        if type(source.id) is not str or type(source.text) is not str:
            raise ValueError("Context sources require string identifiers and text")
        if source.id not in grants or source.id in included or remaining <= 0:
            continue
        # Redact before truncation so a boundary cannot split and expose a token.
        part = redact(source.text)[:min(12000, remaining)]
        parts.append(part)
        included.append(source.id)
        remaining -= len(part) + 2
    return ContextBundle("\n\n".join(parts), tuple(included))
