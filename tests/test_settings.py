import json

import pytest

from desktop_agent.settings import Settings, load_settings, save_settings, get_api_key, set_api_key


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
