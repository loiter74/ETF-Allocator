"""ETF Dashboard E2E — Playwright automation"""
import sys, os
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
OUT = os.path.join(os.path.dirname(__file__), "e2e_output")
os.makedirs(OUT, exist_ok=True)

passed, failed = 0, 0
def check(cond, msg):
    global passed, failed
    if cond: passed += 1; print(f"  OK  {msg}")
    else: failed += 1; print(f"  FAIL {msg}")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})

    # 1. Load
    print("\n[1] Page load...")
    try:
        pg.goto(URL, timeout=20000)
        pg.wait_for_load_state("networkidle")
        check(True, "Page loaded successfully")
    except Exception as e:
        check(False, f"Load failed: {e}")
        b.close(); sys.exit(1)
    pg.screenshot(path=os.path.join(OUT, "01-loaded.png"), full_page=True)

    # 2. Core elements
    print("\n[2] Core elements...")
    t = pg.locator("h1").first
    check(t.is_visible(), f"Title visible: {t.text_content()}")
    check("ETF" in (t.text_content() or ""), "Title contains ETF")

    ripple = pg.locator(".ripple-grid")
    check(ripple.count() > 0, f"Ripple grid: {ripple.count()} present")

    glass = pg.locator(".glass")
    check(glass.count() >= 3, f"Glass panes: {glass.count()} (need >=3)")

    handles = pg.locator(".drag-handle")
    check(handles.count() >= 3, f"Drag handles: {handles.count()} (need >=3)")

    # 3. Theme interaction
    print("\n[3] Theme switcher...")
    btn = pg.locator("button").filter(has_text="🎨").first
    check(btn.is_visible(), "Theme button visible")
    btn.click()
    pg.wait_for_timeout(800)
    pg.screenshot(path=os.path.join(OUT, "02-theme-open.png"), full_page=True)

    cols = pg.locator("button.rounded-full")
    check(cols.count() >= 2, f"Color buttons: {cols.count()} visible after click")

    # 4. Console errors
    print("\n[4] Console check...")
    msgs = []
    pg.on("console", lambda m: msgs.append(m))
    pg.reload()
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(3000)
    errs = [m for m in msgs if m.type == "error"]
    check(len(errs) == 0, f"Console errors: {len(errs)}")
    for e in errs:
        print(f"     ⚠ {e.text}")

    # 5. Content
    print("\n[5] Content check...")
    html = pg.content()
    check(("温度计" in html) or ("thermometer" in html.lower()), "Thermometer widget present")
    check("权益" in html, "Equity text present")
    check(("VALUE" in html) or ("GROWTH" in html), "Factor group text present")

    # 6. Mobile
    print("\n[6] Responsive...")
    pg.set_viewport_size({"width": 375, "height": 812})
    pg.wait_for_timeout(500)
    pg.screenshot(path=os.path.join(OUT, "03-mobile.png"), full_page=True)
    check(True, "Mobile screenshot captured")

    b.close()
    print(f"\n{'='*50}")
    print(f"RESULT: {passed} passed, {failed} failed")
    print(f"Screenshots: {OUT}")
    sys.exit(0 if failed == 0 else 1)
