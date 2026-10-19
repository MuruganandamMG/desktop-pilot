import json

import pytest

from desktop_agent.settings import Settings, load_settings, save_settings, get_api_key, set_api_key


@pytest.fixture(autouse=True)
def isolate_local_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("desktop_agent.settings.PROJECT_ROOT", tmp_path, raising=False)
    (tmp_path / "pyproject.toml").write_text('[project]\nname="desktop-pilot"\n')


def test_defaults_and_validated_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    assert load_settings(path).model_id == "gemini-3.5-flash-lite"
    settings = Settings(vault_path=str(tmp_path / "vault"))
    save_settings(settings, path)
    assert load_settings(path) == settings
    path.write_text(json.dumps({"model_id": "x", "api_key": "secret"}))
    with pytest.raises(ValueError):
        load_settings(path)


def test_credential_backend_is_separate_from_settings(tmp_path, monkeypatch):
    values = {}
    monkeypatch.setattr("keyring.set_password", lambda service, user, value: values.update({(service, user): value}))
    monkeypatch.setattr("keyring.get_password", lambda service, user: values.get((service, user)))
    assert get_api_key() is None
    set_api_key("test-secret")
    assert get_api_key() == "test-secret"
    path = tmp_path / "settings.json"
    save_settings(Settings(), path)
    assert "test-secret" not in path.read_text()
    with pytest.raises(ValueError):
        set_api_key("")


@pytest.mark.parametrize("values", [
    {"budget_usd": "NaN"}, {"budget_usd": "-1"}, {"input_rate_usd": "1"},
    {"input_rate_usd": "1", "output_rate_usd": "2", "rate_model_id": "x", "rate_date": "yesterday"},
    {"stronger_model_id": 42},
])
def test_invalid_budget_or_rate_metadata_is_rejected(values):
    with pytest.raises(ValueError):
        Settings(**values)


def test_process_key_takes_precedence_without_reading_other_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "process-test-key")
    (tmp_path / ".env").write_text('GEMINI_API_KEY="bad unfinished')
    monkeypatch.setattr("keyring.get_password", lambda *args: pytest.fail("Credential backend should not be read"))
    assert get_api_key() == "process-test-key"


@pytest.mark.parametrize("line", [
    "GEMINI_API_KEY=file-test-key", 'GEMINI_API_KEY="file-test-key" # local',
    "export GEMINI_API_KEY='file-test-key'", "\ufeffGEMINI_API_KEY=file-test-key",
])
def test_project_env_key_is_loaded_without_mutating_process_environment(tmp_path, monkeypatch, line):
    import os
    (tmp_path / ".env").write_text(line, encoding="utf-8")
    monkeypatch.setattr("keyring.get_password", lambda *args: pytest.fail("File key should override Credential Manager"))
    assert get_api_key() == "file-test-key"
    assert "GEMINI_API_KEY" not in os.environ


def test_blank_file_key_falls_back_to_credential_manager(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("# empty template\nGEMINI_API_KEY=\nOTHER_SETTING=ignored")
    monkeypatch.setattr("keyring.get_password", lambda *args: "credential-test-key")
    assert get_api_key() == "credential-test-key"


def test_env_does_not_expand_or_execute_values(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GEMINI_API_KEY='${OTHER_KEY}$(command)'\n")
    monkeypatch.setenv("OTHER_KEY", "must-not-be-read")
    assert get_api_key() == "${OTHER_KEY}$(command)"


@pytest.mark.parametrize("contents", [
    'GEMINI_API_KEY="private unfinished',
    "GEMINI_API_KEY=private one two",
    "GEMINI_API_KEY=private-first\nGEMINI_API_KEY=private-second",
    "GEMINI_API_KEY=" + "x" * 70000,
], ids=["unclosed-quote", "multiple-values", "duplicate-key", "oversized-file"])
def test_invalid_env_configuration_fails_without_exposing_values(tmp_path, contents):
    (tmp_path / ".env").write_text(contents)
    with pytest.raises(ValueError) as caught:
        get_api_key()
    assert "private" not in str(caught.value)
    assert "GEMINI_API_KEY" in str(caught.value)


def test_current_directory_env_is_not_discovered(tmp_path, monkeypatch):
    other = tmp_path / "untrusted"
    other.mkdir()
    (other / ".env").write_text("GEMINI_API_KEY=untrusted-key")
    monkeypatch.chdir(other)
    monkeypatch.setattr("keyring.get_password", lambda *args: None)
    assert get_api_key() is None
