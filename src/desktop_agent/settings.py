"""Validated nonsecret settings; credentials stay in Windows Credential Manager."""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path

import keyring


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "DesktopAgent"


@dataclass(frozen=True)
class Settings:
    model_id: str = "gemini-3.5-flash-lite"
    vault_path: str = ""
    memory_saving: bool = False
    max_model_calls: int = 10
    max_tool_actions: int = 20
    request_timeout_seconds: int = 60
    max_output_tokens: int = 1024
    stronger_model_id: str = ""
    budget_usd: str = ""
    rate_model_id: str = ""
    input_rate_usd: str = ""
    output_rate_usd: str = ""
    rate_date: str = ""

    def __post_init__(self):
        if type(self.model_id) is not str or not self.model_id.strip() or len(self.model_id) > 128:
            raise ValueError("Invalid model ID")
        if type(self.vault_path) is not str or type(self.memory_saving) is not bool:
            raise ValueError("Invalid memory settings")
        for value in (self.max_model_calls, self.max_tool_actions, self.request_timeout_seconds, self.max_output_tokens):
            if type(value) is not int or value < 1 or value > 65536:
                raise ValueError("Invalid request limit")
        for value in (self.stronger_model_id, self.rate_model_id, self.rate_date):
            if type(value) is not str or len(value) > 128:
                raise ValueError("Invalid model/rate metadata")
        for value in (self.budget_usd, self.input_rate_usd, self.output_rate_usd):
            if type(value) is not str or len(value) > 32:
                raise ValueError("Money estimates must be bounded decimal strings")
            if value:
                try:
                    amount = Decimal(value)
                    if not amount.is_finite() or amount < 0:
                        raise ValueError("Money estimates must be finite and nonnegative")
                except InvalidOperation as exc:
                    raise ValueError("Invalid money estimate") from exc
        rates = (self.rate_model_id, self.input_rate_usd, self.output_rate_usd, self.rate_date)
        if any(rates) and not all(rates):
            raise ValueError("Rates need a model ID, input/output USD per million tokens, and an ISO date")
        if self.rate_date:
            date.fromisoformat(self.rate_date)


def load_settings(path: Path | None = None) -> Settings:
    path = path or data_dir() / "settings.json"
    if not path.exists():
        return Settings()
    try:
        values = json.loads(path.read_text(encoding="utf-8-sig"))
        if type(values) is not dict:
            raise ValueError("Settings must be an object")
        return Settings(**values)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid settings; original file left unchanged") from exc


def save_settings(settings: Settings, path: Path | None = None) -> None:
    if not isinstance(settings, Settings):
        raise ValueError("Expected validated settings")
    path = path or data_dir() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # A fixed schema keeps credentials out even if callers pass an unexpected field.
    path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")


def get_api_key() -> str | None:
    return keyring.get_password("DesktopPilot", "gemini-api-key")


def set_api_key(value: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise ValueError("Enter a nonempty API key")
    keyring.set_password("DesktopPilot", "gemini-api-key", value.strip())
