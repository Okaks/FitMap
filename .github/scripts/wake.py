import os
import re
import sys
from playwright.sync_api import sync_playwright

URLS = [u.strip() for u in os.environ["APP_URLS"].splitlines() if u.strip()]
SLEEP_MARKER = re.compile(r"gone to sleep", re.I)
os.makedirs("shots", exist_ok=True)


def slug(url):
    return url.replace("https://", "").replace("/", "_").strip("_")


def wake(page, url):
    name = slug(url)
    page.goto(url, wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(5_000)
    page.screenshot(path=f"shots/{name}-1-arrived.png", full_page=True)

    button = page.get_by_role("button", name=re.compile(r"back up", re.I))
    if button.count() == 0:
        button = page.locator("button", has_text=re.compile(r"back up", re.I))

    if button.count() > 0:
        print(f"    asleep, clicking wake button")
        button.first.click()
        for _ in range(24):
            page.wait_for_timeout(5_000)
            if not SLEEP_MARKER.search(page.content()):
                break
        page.wait_for_timeout(15_000)
    else:
        print(f"    no wake button found")

    page.screenshot(path=f"shots/{name}-2-after.png", full_page=True)

    page.reload(wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(10_000)
    page.screenshot(path=f"shots/{name}-3-verify.png", full_page=True)

    if SLEEP_MARKER.search(page.content()):
        raise RuntimeError("still showing the sleep screen after wake attempt")

    return page.title()


failures = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    )

    for url in URLS:
        print(f"--> {url}")
        page = context.new_page()
        try:
            print(f"OK  {url} -> {wake(page, url)}")
        except Exception as exc:
            failures.append(url)
            print(f"ERR {url} -> {exc}")
        finally:
            page.close()

    browser.close()

if failures:
    print(f"\nFAILED: {len(failures)} of {len(URLS)} apps")
    sys.exit(1)

print(f"\nAll {len(URLS)} apps awake")