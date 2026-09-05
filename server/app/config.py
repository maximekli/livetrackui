from dataclasses import dataclass
import os


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


@dataclass(frozen=True)
class Settings:
    imap_host: str = os.getenv("IMAP_HOST", "")
    imap_port: int = _int("IMAP_PORT", 993)
    imap_use_ssl: bool = _bool("IMAP_USE_SSL", True)
    imap_username: str = os.getenv("IMAP_USERNAME", "")
    imap_password: str = os.getenv("IMAP_PASSWORD", "")
    imap_folder: str = os.getenv("IMAP_FOLDER", "INBOX")
    imap_sender: str = os.getenv("IMAP_SENDER", "noreply@garmin.com")
    imap_poll_interval_seconds: int = _int("IMAP_POLL_INTERVAL_SECONDS", 60)
    validation_interval_seconds: int = _int("VALIDATION_INTERVAL_SECONDS", 60)
    playwright_timeout_seconds: int = _int("PLAYWRIGHT_TIMEOUT_SECONDS", 30)
    state_file: str = os.getenv("STATE_FILE", "/data/state.json")
    electron_artifact_path: str = os.getenv(
        "ELECTRON_ARTIFACT_PATH",
        "/opt/livetrackui/electron/dist/LiveTrackUI.AppImage",
    )
    backend_url: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    sessions_poll_interval_seconds: int = _int("SESSIONS_POLL_INTERVAL_SECONDS", 60)
