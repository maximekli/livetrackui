from dataclasses import dataclass
from typing import Literal

SessionState = Literal["active", "unavailable"]


@dataclass
class Session:
    url: str
    state: SessionState = "unavailable"

    def as_api_dict(self) -> dict[str, str]:
        return {"url": self.url}
