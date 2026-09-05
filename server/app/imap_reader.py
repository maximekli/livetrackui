import asyncio
import email
import imaplib
import logging
from collections.abc import Callable
from email import policy

from .config import Settings
from .parser import parse_garmin_email, sender_address
from .state import StateStore

logger = logging.getLogger(__name__)


class ImapReader:
    def __init__(self, settings: Settings, state: StateStore, on_session: Callable):
        self.settings = settings
        self.state = state
        self.on_session = on_session

    def _connect(self):
        if self.settings.imap_use_ssl:
            client = imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port)
        else:
            client = imaplib.IMAP4(self.settings.imap_host, self.settings.imap_port)
        client.login(self.settings.imap_username, self.settings.imap_password)
        status, _ = client.select(self.settings.imap_folder)
        if status != "OK":
            raise RuntimeError(f"Unable to select IMAP folder {self.settings.imap_folder}")
        return client

    def _poll_once(self) -> None:
        client = self._connect()
        try:
            uidvalidity = int(client.response("UIDVALIDITY")[1][0])
            if self.state.state.imap_uidvalidity != uidvalidity:
                logger.info("IMAP UIDVALIDITY changed; rescanning folder")
                self.state.state.imap_uidvalidity = uidvalidity
                self.state.state.last_imap_uid = 0
                self.state.save()

            start_uid = self.state.state.last_imap_uid + 1
            status, data = client.uid(
                "search",
                None,
                "FROM",
                self.settings.imap_sender,
            )
            if status != "OK":
                raise RuntimeError("Unable to search IMAP folder")

            uids = [int(value) for value in data[0].split() if int(value) >= start_uid]
            for uid in sorted(uids):
                status, fetched = client.uid("fetch", str(uid), "(BODY.PEEK[])")
                if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    logger.warning("Unable to fetch IMAP message UID %s", uid)
                    self.state.state.last_imap_uid = uid
                    self.state.save()
                    continue

                self.state.state.last_imap_uid = uid
                self.state.save()
                message = email.message_from_bytes(fetched[0][1], policy=policy.default)
                if sender_address(message) != self.settings.imap_sender.lower():
                    continue

                parsed = parse_garmin_email(message)
                if parsed is None:
                    logger.warning(
                        "Dropped malformed email sender=%s subject=%r date=%r",
                        message.get("From", ""),
                        message.get("Subject", ""),
                        message.get("Date", ""),
                    )
                else:
                    logger.info("Parsed LiveTrack email url=%s", parsed)
                    self.on_session(parsed)

        finally:
            try:
                client.logout()
            except imaplib.IMAP4.error:
                pass

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(self._poll_once)
            except Exception:
                logger.exception("IMAP polling failed")
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=self.settings.imap_poll_interval_seconds
                )
            except asyncio.TimeoutError:
                pass
