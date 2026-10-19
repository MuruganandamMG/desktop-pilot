"""Validated settings with explicit process/project key overrides."""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import shlex

import keyring


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def _checked_key(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if len(value) > 4096 or any(character.isspace() for character in value):
        raise ValueError("Invalid GEMINI_API_KEY configuration")
    return value


def _project_env_key(variable="GEMINI_API_KEY") -> str | None:
    # Never discover .env through the current directory or parent traversal.
    if not (PROJECT_ROOT / "pyproject.toml").is_file():
        return None
    path = PROJECT_ROOT / ".env"
    try:
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("Invalid GEMINI_API_KEY project .env path")
        with path.open("rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError("GEMINI_API_KEY project .env exceeds 64 KiB")
        found, value = False, None
        for line in raw.decode("utf-8-sig").splitlines():
            name, separator, literal = line.partition("=")
            fields = name.strip().split()
            if fields == ["export", variable]:
                name = variable
            if not separator or name.strip() != variable:
                continue
            if found:
                raise ValueError("Duplicate GEMINI_API_KEY configuration")
            found = True
            tokens = shlex.split(literal, comments=True, posix=True)
            if len(tokens) > 1:
                raise ValueError("Invalid GEMINI_API_KEY literal")
            value = _checked_key(tokens[0] if tokens else None)
        return value
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, ValueError):
        raise ValueError("Cannot load GEMINI_API_KEY from the project .env; check its format and size") from None


def get_api_key() -> str | None:
    return (_checked_key(os.environ.get("GEMINI_API_KEY"))
            or _project_env_key()
            or _checked_key(keyring.get_password("DesktopPilot", "gemini-api-key")))


def set_api_key(value: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise ValueError("Enter a nonempty API key")
    keyring.set_password("DesktopPilot", "gemini-api-key", value.strip())


def voice_settings() -> tuple[str, int | None, int | None]:
    def value(name, default=None):
        return os.environ.get(name) or _project_env_key(name) or default
    model = value("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    if not model or len(model) > 128 or any(c.isspace() or ord(c) < 32 for c in model):
        raise ValueError("Invalid GEMINI_LIVE_MODEL")
    def device(name):
        raw = value(name)
        if raw is None:
            return None
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 5:
            raise ValueError(f"Invalid {name}; use the device number from --list-audio-devices")
        return int(raw)
    return model, device("VOICE_INPUT_DEVICE"), device("VOICE_OUTPUT_DEVICE")
