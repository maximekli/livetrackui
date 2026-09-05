import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import Session


@dataclass
class PersistedState:
    imap_uidvalidity: int | None = None
    last_imap_uid: int = 0
    sessions: list[Session] = field(default_factory=list)


class StateStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.state = self._load()

    def _load(self) -> PersistedState:
        if not self.path.exists():
            return PersistedState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            sessions = [
                Session(url=item["url"], state=item.get("state", "unavailable"))
                for item in raw.get("sessions", [])
            ]
            return PersistedState(
                imap_uidvalidity=raw.get("imap_uidvalidity"),
                last_imap_uid=int(raw.get("last_imap_uid", 0)),
                sessions=sessions,
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise RuntimeError(f"Unable to load state file {self.path}: {exc}") from exc

    def save(self) -> None:
        self.path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        payload = {
            "imap_uidvalidity": self.state.imap_uidvalidity,
            "last_imap_uid": self.state.last_imap_uid,
            "sessions": [asdict(session) for session in self.state.sessions],
        }
        fd, temporary_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
                json.dump(payload, temporary_file, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.chmod(temporary_path, 0o644)
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def upsert_session(self, session: Session) -> None:
        for index, current in enumerate(self.state.sessions):
            if current.url == session.url:
                self.state.sessions[index] = session
                return
        self.state.sessions.append(session)

    def remove_session(self, url: str) -> None:
        self.state.sessions = [session for session in self.state.sessions if session.url != url]

    def active_sessions(self) -> list[Session]:
        return [session for session in self.state.sessions if session.state == "active"]
