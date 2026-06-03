# -*- coding: utf-8 -*-
"""ETF Dashboard E2E v4 — light theme, current component classes"""
import sys, os, time
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"

passed = failed = 0
def check(cond, msg):
    global passed, failed
    if cond: passed += 1; print(f"  [PASS] {msg}")
    else: failed += 1; print(f"  [FAIL] {msg}")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})

    # ── 1. Load (wait for React hydration, not just network idle) ──
    print("\n[1] Loading...")
    loaded = False
    for attempt in range(10):
        try:
            pg.goto(URL, timeout=25000)
            # Wait for React to render: body must have > 5000 chars
            pg.wait_for_load_state("networkidle")
            for _ in range(20):
                time.sleep(1)
                body = pg.content()
                if len(body) > 5000:
                    loaded = True
                    break
            if loaded:
                check(True, f"React rendered ({len(body)} chars, attempt {attempt+1})")
                break
        except Exception as e:
            pass
        if attempt == 9:
            check(False, "React never hydrated — page stays blank")
            b.close(); sys.exit(1)
        print(f"  Waiting for React... ({attempt+2}/10)")

    # ── 2. API connectivity ──
    print("\n[2] API check...")
    loading = "加载配置数据" in body
    error = "数据加载失败" in body
    if loading and not error:
        print("  [INFO] Still loading, waiting 8s more...")
        time.sleep(8)
        body = pg.content()
        loading = "加载配置数据" in body
        error = "数据加载失败" in body

    check(not loading, "Not stuck in loading")
    check(not error, "No API error")

    # ── 3. Page elements ──
    print("\n[3] Elements...")
    check("ETF" in body and "Allocator" in body, "Title ETF Allocator")
    check("本月概览" in body, "NavBar tab present")
    check("glass-card" in body, f"GlassCard CSS ({body.count('glass-card')} occurrences)")
    check("权益" in body, "Equity content")
    check(("VALUE" in body) or ("GROWTH" in body), "Factor groups")

    # ── 4. Theme button ──
    print("\n[4] Theme...")
    btns = pg.locator("button").all()
    check(len(btns) > 0, f"Buttons on page: {len(btns)}")
    if len(btns) > 0:
        for b2 in btns[:8]:
            try:
                txt = (b2.text_content() or "").encode('ascii', 'replace').decode()
                if txt.strip():
                    print(f"  btn: {txt}")
            except: pass

    # ── 5. Console ──
    print("\n[5] Console...")
    msgs = []
    pg.on("console", lambda m: msgs.append(m))
    try:
        pg.reload()
        pg.wait_for_load_state("networkidle", timeout=15000)
    except Exception as e:
        print(f"  [WARN] Reload failed: {e} — using pre-reload body")
    time.sleep(3)
    errs = [m for m in msgs if m.type == "error"]
    check(len(errs) == 0, f"Errors: {len(errs)}")
    for e in errs:
        txt = e.text[:120]
        try: print(f"  ERR: {txt}")
        except: print(f"  ERR: {txt.encode('ascii','replace').decode()}")

    # ── 6. Debug ──
    body2 = pg.content()
    print(f"\n[6] Final body: {len(body2)} chars")
    for needle in ["glass-card", "w-8 h-8", "backdrop-blur", "本月概览", "权益"]:
        count = body2.count(needle)
        print(f"  '{needle}': {count}")
    check(count > 0, f"'{needle}' present")

    b.close()
    print(f"\n{'='*50}")
    print(f"RESULT: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
