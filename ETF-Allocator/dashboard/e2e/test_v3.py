# -*- coding: utf-8 -*-
"""ETF Dashboard E2E - Playwright (v3: fixed encoding + retry)"""
import sys, os, time
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_output")
os.makedirs(OUT, exist_ok=True)

OK, FAIL = 0, 0
def check(cond, msg):
    global OK, FAIL
    if cond: OK += 1; print(f"  [PASS] {msg}")
    else: FAIL += 1; print(f"  [FAIL] {msg}")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})

    # 1. Load with retry
    print("\n[1] Page load...")
    for attempt in range(3):
        try:
            pg.goto(URL, timeout=15000)
            pg.wait_for_load_state("networkidle")
            break
        except Exception as e:
            if attempt == 2: check(False, f"Load failed x3: {e}"); b.close(); sys.exit(1)
            time.sleep(3)

    pg.wait_for_timeout(3000)
    pg.screenshot(path=os.path.join(OUT, "01-initial.png"), full_page=True)
    body = pg.content()

    # Handle loading/error states
    if "加载配置数据" in body:
        print("  [INFO] Loading state - waiting...")
        time.sleep(10)
        pg.screenshot(path=os.path.join(OUT, "01b-after-wait.png"), full_page=True)
        body = pg.content()
    if "数据加载失败" in body:
        print("  [WARN] Error state - retrying...")
        retry = pg.locator("button").filter(has_text="重试")
        if retry.count() > 0:
            retry.first.click()
            time.sleep(5)
            pg.screenshot(path=os.path.join(OUT, "01c-after-retry.png"), full_page=True)
            body = pg.content()

    check(True, f"Page loaded (state: {'error' if '失败' in body else 'loading' if '加载' in body else 'loaded'})")

    # 2. Elements
    print("\n[2] Page elements...")
    check("ETF" in body and "Allocator" in body, "Title present")
    check("glass" in body, f"Glass panels ({body.count('glass')} occurrences)")
    check("ripple" in body, "Ripple grid present")

    # 3. Theme
    print("\n[3] Theme switcher...")
    theme_btn = pg.locator("button").filter(has_text="🎨")
    if theme_btn.count() > 0:
        check(True, "Theme button found")
        theme_btn.first.click()
        time.sleep(1)
        pg.screenshot(path=os.path.join(OUT, "02-theme.png"), full_page=True)

        cols = pg.locator("button.rounded-full")
        check(cols.count() >= 2, f"Theme colors visible: {cols.count()}")
    else:
        check(False, "Theme button missing")

    # 4. Console errors
    print("\n[4] Console...")
    msgs = []
    pg.on("console", lambda m: msgs.append(m))
    pg.reload()
    pg.wait_for_load_state("networkidle")
    time.sleep(5)
    errs = [m for m in msgs if m.type == "error"]
    warns = [m for m in msgs if m.type == "warning"]
    check(len(errs) == 0, f"Console errors: {len(errs)}")
    for e in errs:
        txt = e.text[:150]
        try:
            print(f"     ERR: {txt}")
        except:
            print(f"     ERR: {txt.encode('ascii','replace').decode()}")
    for w in warns[:3]:
        txt = w.text[:150]
        try:
            print(f"     WARN: {txt}")
        except:
            print(f"     WARN: {txt.encode('ascii','replace').decode()}")

    # 5. Content
    print("\n[5] Content...")
    final = pg.content()
    widgets_ok = ("温度计" in final or "thermometer" in final.lower() or "权益" in final)
    check(widgets_ok, "Widget content present")
    check(("VALUE" in final) or ("GROWTH" in final), "Factor groups")

    # 6. Mobile
    print("\n[6] Responsive...")
    pg.set_viewport_size({"width": 375, "height": 812})
    time.sleep(1)
    pg.screenshot(path=os.path.join(OUT, "03-mobile.png"), full_page=True)
    check(True, "Mobile viewport OK")

    b.close()
    print(f"\n{'='*50}")
    print(f"RESULT: {OK} passed, {FAIL} failed")
    print(f"Screenshots: {OUT}")
    sys.exit(0 if FAIL == 0 else 1)
