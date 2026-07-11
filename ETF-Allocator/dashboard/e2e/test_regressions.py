"""Fresh Playwright regression check for the current React dashboard."""
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "http://localhost:5173"
OUTPUT = Path(__file__).resolve().parent / "e2e_output"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            service_workers="block",
        )
        page = context.new_page()
        console_errors: list[str] = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

        page.goto(BASE_URL, wait_until="networkidle", timeout=30_000)
        page.get_by_text("市场温度计", exact=True).wait_for(timeout=30_000)
        assert page.get_by_text("数据加载失败").count() == 0
        assert page.get_by_text("本月概览", exact=True).is_visible()
        assert page.get_by_text("持仓模拟", exact=True).count() == 0
        page.screenshot(path=OUTPUT / "regression-desktop.png", full_page=True)

        page.goto(f"{BASE_URL}/simulator", wait_until="networkidle", timeout=30_000)
        page.wait_for_url(f"{BASE_URL}/")
        page.get_by_text("市场温度计", exact=True).wait_for(timeout=30_000)

        page.get_by_text("历史趋势", exact=True).click()
        page.wait_for_url("**/trends")
        page.get_by_text("PE 分位走势", exact=True).wait_for(timeout=15_000)
        assert page.get_by_text("本月概览", exact=True).is_visible()
        assert page.get_by_text("数据加载失败").count() == 0

        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(BASE_URL, wait_until="networkidle", timeout=30_000)
        page.get_by_role("button", name="打开导航菜单").click()
        assert page.get_by_text("资金记录", exact=True).last.is_visible()
        assert page.get_by_text("持仓模拟", exact=True).count() == 0
        page.screenshot(path=OUTPUT / "regression-mobile.png", full_page=True)

        assert not console_errors, f"Browser console errors: {console_errors}"
        context.close()
        browser.close()

    print("PASS: desktop, removed simulator redirect, trends, mobile menu, and console checks")


if __name__ == "__main__":
    main()
