import pytest

from desktop_agent.context import Source, prepare_context, redact


def test_context_excludes_ungranted_sources_and_bounds_output():
    bundle = prepare_context([Source("a", "a" * 20000), Source("b", "private")], {"a"})
    assert len(bundle.text) <= 32000
    assert "private" not in bundle.text
    assert bundle.sources == ("a",)
    assert len(bundle.text) < 13000


def test_secret_patterns_are_redacted():
    text = "api_key=secret123 Authorization: Bearer abc.def.ghi ghp_" + "a" * 36
    safe = redact(text)
    for secret in ("secret123", "abc.def.ghi", "ghp_" + "a" * 36):
        assert secret not in safe
    assert "[REDACTED]" in safe


def test_invalid_source_is_rejected():
    with pytest.raises(ValueError):
        prepare_context([Source("a", 3)], {"a"})
