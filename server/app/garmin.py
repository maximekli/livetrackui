from enum import Enum

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


class ValidationResult(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    UNAVAILABLE = "unavailable"


async def _is_effectively_visible(locator) -> bool:
    if await locator.count() == 0:
        return False
    return await locator.evaluate_all(
        """element => {
            return element.some(node => {
                for (let current = node; current; current = current.parentElement) {
                    const style = window.getComputedStyle(current);
                    if (style.display === 'none'
                        || style.visibility === 'hidden'
                        || Number(style.opacity) === 0) {
                        return false;
                    }
                }
                const rect = node.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            });
        }"""
    )


async def validate_page(page: Page) -> ValidationResult:
    ended = page.locator(
        '[data-tid="session_complete_banner"], [class*="session-ended-view_container"]'
    )
    try:
        await page.wait_for_function(
            """() => Array.from(document.querySelectorAll(
                '[data-tid="session_complete_banner"], [class*="session-ended-view_container"], .leaflet-container'
            )).some(node => {
                for (let current = node; current; current = current.parentElement) {
                    const style = window.getComputedStyle(current);
                    if (style.display === 'none'
                        || style.visibility === 'hidden'
                        || Number(style.opacity) === 0) {
                        return false;
                    }
                }
                const rect = node.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            })""",
            timeout=5000,
        )
    except PlaywrightTimeoutError:
        return ValidationResult.UNAVAILABLE

    if await _is_effectively_visible(ended):
        return ValidationResult.ENDED

    map_container = page.locator(".leaflet-container")
    if await _is_effectively_visible(map_container):
        return ValidationResult.ACTIVE

    return ValidationResult.UNAVAILABLE
