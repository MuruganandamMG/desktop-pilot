from pathlib import Path

import pytest

from desktop_agent.memory import MemoryStore


def test_search_returns_only_bounded_granted_markdown(tmp_path):
    for folder in ("Preferences", "Project", ".obsidian"):
        (tmp_path / folder).mkdir()
    (tmp_path / "Preferences" / "Editor.md").write_text("Provenance: user-stated\nUse VS Code editor")
    (tmp_path / "Project" / "private.md").write_text("editor secret project")
    (tmp_path / ".obsidian" / "secret.md").write_text("editor internal")
    (tmp_path / "Preferences" / "huge.md").write_text("editor" * 50000)
    (tmp_path / "Preferences" / ".hidden.md").write_text("editor hidden")
    memory = MemoryStore(tmp_path, {"Preferences"})
    result = memory.search("editor")
    assert len(result) == 1
    assert result[0].path == "Preferences/Editor.md"
    assert result[0].provenance == "user-stated"
    assert result[0].modified_at
    assert len(result[0].text) <= 12000


def test_search_is_stable_and_capped_to_five(tmp_path):
    (tmp_path / "Project").mkdir()
    for number in range(8):
        (tmp_path / "Project" / f"{number}.md").write_text("Gemini cloud")
    memory = MemoryStore(tmp_path, {"Project"})
    assert len(memory.search("Gemini", limit=99)) == 5
    assert memory.search("Gemini") == memory.search("Gemini")
    assert memory.search("") == []


def test_grants_cannot_escape_vault(tmp_path):
    for grant in ("..", "../outside", ".obsidian", str(Path(tmp_path.anchor))):
        with pytest.raises(ValueError):
            MemoryStore(tmp_path, {grant})


def test_symlink_and_unavailable_vault_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        MemoryStore(tmp_path / "absent", {"Project"})
    (tmp_path / "Project").mkdir()
    (tmp_path / "outside.md").write_text("secret")
    try:
        (tmp_path / "Project" / "link.md").symlink_to(tmp_path / "outside.md")
    except OSError:
        pytest.skip("Host does not permit test symlinks")
    assert MemoryStore(tmp_path, {"Project"}).search("secret") == []


def test_excerpt_contains_matching_evidence_after_long_introduction(tmp_path):
    (tmp_path / "Project").mkdir()
    (tmp_path / "Project" / "notes.md").write_text("introduction " * 1100 + "\nImportant Vulkan configuration")
    result = MemoryStore(tmp_path, {"Project"}).search("Vulkan")
    assert len(result) == 1
    assert "Vulkan" in result[0].text
    assert len(result[0].text) <= 12000
