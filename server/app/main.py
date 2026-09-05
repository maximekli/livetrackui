import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright

from .config import Settings
from .garmin import ValidationResult, validate_page
from .imap_reader import ImapReader
from .models import Session
from .state import StateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
settings = Settings()
state_store = StateStore(settings.state_file)
stop_event = asyncio.Event()


def add_session(url: str) -> None:
    state_store.upsert_session(Session(url=url))
    state_store.save()


async def validation_loop() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            while not stop_event.is_set():
                for session in list(state_store.state.sessions):
                    try:
                        page = await browser.new_page()
                        try:
                            await page.goto(
                                session.url,
                                wait_until="domcontentloaded",
                                timeout=settings.playwright_timeout_seconds * 1000,
                            )
                            result = await validate_page(page)
                        finally:
                            await page.close()
                    except Exception:
                        logger.exception("LiveTrack validation failed for url=%s", session.url)
                        result = ValidationResult.UNAVAILABLE

                    if result == ValidationResult.ENDED:
                        state_store.remove_session(session.url)
                    else:
                        session.state = result.value
                    logger.info(
                        "LiveTrack validation result=%s url=%s",
                        result.value,
                        session.url,
                    )
                    state_store.save()

                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=settings.validation_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            await browser.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop_event.clear()
    imap_reader = ImapReader(settings, state_store, add_session)
    tasks = [
        asyncio.create_task(imap_reader.run(stop_event)),
        asyncio.create_task(validation_loop()),
    ]
    yield
    stop_event.set()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="LiveTrackUI API", lifespan=lifespan)


@app.get("/sessions")
def sessions() -> dict[str, list[dict[str, str]]]:
    return {"sessions": [session.as_api_dict() for session in state_store.active_sessions()]}


@app.get("/electron/download")
def electron_download() -> FileResponse:
    artifact = Path(settings.electron_artifact_path)
    if not artifact.is_file():
        raise HTTPException(status_code=404, detail="Electron artifact is not available")
    return FileResponse(
        artifact,
        filename=artifact.name,
        media_type="application/octet-stream",
    )
