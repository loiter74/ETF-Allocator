"""ETF Dashboard E2E — Playwright automation v2"""
import sys, os
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_output")
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
        check(True, "Page loaded")
    except Exception as e:
        check(False, f"Load failed: {e}")
        b.close(); sys.exit(1)

    pg.wait_for_timeout(3000)
    pg.screenshot(path=os.path.join(OUT, "01-initial.png"), full_page=True)
    body = pg.content()

    # Handle loading/error states
    if "加载配置数据" in body:
        print("[INFO] Loading state - waiting for API...")
        pg.wait_for_timeout(8000)
        body = pg.content()
    if "数据加载失败" in body:
        print("[WARN] Error state - API not responding")
        retry = pg.locator("button").filter(has_text="重试")
        if retry.count() > 0: retry.first.click(); pg.wait_for_timeout(3000)
        body = pg.content()

    pg.screenshot(path=os.path.join(OUT, "02-state.png"), full_page=True)

    # 2. Check what rendered
    print("\n[2] Page elements...")
    has_title = "ETF" in body and "Allocator" in body
    has_glass = "glass" in body
    has_ripple = "ripple" in body
    check(has_title, f"Title 'ETF Allocator' present: {has_title}")
    check(has_glass, f"Glass panels: {body.count('glass')} occurrences")
    check(has_ripple, f"Ripple grid: {has_ripple}")

    # 3. Theme button
    print("\n[3] Theme switcher...")
    theme_btn = pg.locator("button").filter(has_text="🎨")
    if theme_btn.count() > 0:
        check(True, "Theme button found")
        theme_btn.first.click()
        pg.wait_for_timeout(800)
        pg.screenshot(path=os.path.join(OUT, "03-theme.png"), full_page=True)
    else:
        check(False, "Theme button NOT found")
        btns = pg.locator("button").all()
        print(f"  Total buttons: {len(btns)}")
        for btn in btns[:5]:
            try: print(f"    '{btn.text_content()}'")
            except: pass

    # 4. Console
    print("\n[4] Console...")
    msgs = []
    pg.on("console", lambda m: msgs.append(m))
    pg.reload()
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(5000)
    errs = [m for m in msgs if m.type == "error"]
    warns = [m for m in msgs if m.type == "warning"]
    check(len(errs) == 0, f"Console errors: {len(errs)}")
    for e in errs: print(f"     ⚠ {e.text[:120]}")
    for w in warns[:3]: print(f"     ⚡ {w.text[:120]}")

    # 5. Content
    print("\n[5] Content...")
    final = pg.content()
    check(("温度计" in final) or ("thermometer" in final.lower()), "Thermometer")
    check("权益" in final, "Equity text")
    check(("VALUE" in final) or ("GROWTH" in final), "Factor groups")

    # 6. Mobile
    print("\n[6] Responsive...")
    pg.set_viewport_size({"width": 375, "height": 812})
    pg.wait_for_timeout(500)
    pg.screenshot(path=os.path.join(OUT, "04-mobile.png"), full_page=True)
    check(True, "Mobile screenshot done")

    b.close()
    print(f"\n{'='*50}")
    print(f"RESULT: {passed} passed, {failed} failed")
    print(f"Screenshots: {OUT}")
    sys.exit(0 if failed == 0 else 1)
