import re
from email.message import Message
from email.utils import parseaddr

LIVE_TRACK_URL = re.compile(
    r"https://livetrack\.garmin\.com/session/[A-Za-z0-9-]+/token/[A-Za-z0-9_-]+"
)
def _parts(message: Message) -> list[str]:
    values: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            try:
                values.append(part.get_content())
            except (LookupError, UnicodeError):
                continue
    else:
        try:
            values.append(message.get_content())
        except (LookupError, UnicodeError):
            pass
    return values


def parse_garmin_email(message: Message) -> str | None:
    content = "\n".join(_parts(message))
    url_match = LIVE_TRACK_URL.search(content)
    return url_match.group(0) if url_match else None


def sender_address(message: Message) -> str:
    return parseaddr(message.get("From", ""))[1].lower()
