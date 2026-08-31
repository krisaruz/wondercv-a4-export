# -*- coding: utf-8 -*-
"""
WonderCV 编辑页 → 高清 A4 两页 PDF（推荐入口）

用法：
  1) 推荐先运行 start_chrome_debug.bat，登录并打开编辑页
  2) python export_resume.py
  3) 查看 resume_a4.pdf 与 accept_preview/snap_page_*.png

详见 docs/WONDERCV_A4_EXPORT.md
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def cdp_ok(port: int = 9222) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def run_export(url: str, scale: float) -> int:
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader

    import _capture_via_cdp as core

    preview = ROOT / "accept_preview"
    out_pdf = ROOT / "resume_a4.pdf"
    preview.mkdir(exist_ok=True)
    report = {"method": None, "url": url, "scale": scale}

    with sync_playwright() as p:
        context = None
        page = None

        if cdp_ok(9222):
            print("连接 CDP 9222 …")
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            report["method"] = "cdp"
            page = core.find_wondercv_page(browser)
            if not page:
                ctx = browser.contexts[0] if browser.contexts else None
                if not ctx:
                    print("CDP 已连接但无 browser context")
                    return 3
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
            print("tab:", page.url)
            if "auth" in page.url or "signin" in page.url:
                print("当前未登录：请在 debug Chrome 中登录编辑页后重试")
                return 4
            # 列表页/其它页 → 导航到目标编辑页
            if "/editor" not in (page.url or ""):
                print(f"导航到编辑页：{url}")
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                if "auth" in page.url or "signin" in page.url:
                    print("导航后跳到登录页，请登录后重试")
                    return 4
        else:
            print("无 CDP 9222，使用 .chrome-wondercv-profile …")
            print("提示：更稳妥请先运行 start_chrome_debug.bat")
            report["method"] = "persistent"
            pw_dir = ROOT / ".chrome-wondercv-profile"
            pw_dir.mkdir(exist_ok=True)
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(pw_dir),
                channel="chrome",
                headless=False,
                viewport={"width": 1440, "height": 1100},
                device_scale_factor=scale,
                args=["--disable-blink-features=AutomationControlled"],
            )
            for pg in context.pages:
                if "wondercv.com" in (pg.url or "") and "/cvs/" in (pg.url or ""):
                    page = pg
                    break
            if page is None:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=90000)

            # 若未登录或预览未就绪，把窗口交给你手动操作；就绪后回车继续
            def _preview_ready() -> bool:
                try:
                    return page.locator("[data-resume-page]").count() >= 2
                except Exception:
                    return False

            if not _preview_ready():
                print(
                    "\n========================================\n"
                    "未检测到两页预览。请在弹出的 Chrome 窗口里：\n"
                    "  1) 登录 WonderCV 账号\n"
                    "  2) 打开编辑页确认两页预览正常显示\n"
                    f"  目标 URL：{url}\n"
                    "  3) 回到这个终端按 回车 继续\n"
                    "========================================"
                )
                try:
                    sys.stdin.readline()
                except Exception:
                    pass
                deadline_attempts = 30
                for _ in range(deadline_attempts):
                    if _preview_ready():
                        break
                    page.wait_for_timeout(1000)
                if not _preview_ready():
                    print("仍未检测到两页预览，url=", page.url)
                    context.close()
                    return 4

        im1, im2, final_url = core.capture_with_page(page, scale=scale)
        report["url"] = final_url
        if context:
            context.close()

    im1.save(preview / "snap_page_1.png")
    im2.save(preview / "snap_page_2.png")
    im1.save(ROOT / "wondercv_page_1.png")
    im2.save(ROOT / "wondercv_page_2.png")

    qa1, qa2 = core.qa(im1, "page1"), core.qa(im2, "page2")
    print("qa1:", qa1)
    print("qa2:", qa2)

    core.pages_to_pdf(im1, im2, out_pdf)
    reader = PdfReader(str(out_pdf))
    report.update(
        {
            "pdf": str(out_pdf),
            "page_count": len(reader.pages),
            "qa": {"page1": qa1, "page2": qa2},
            "docs": str(ROOT / "docs" / "WONDERCV_A4_EXPORT.md"),
        }
    )
    fail = []
    if report["page_count"] != 2:
        fail.append("不是2页")
    if not qa1["ok"]:
        fail.append("第1页视觉失败")
    if not qa2["ok"]:
        fail.append("第2页视觉失败")
    if not qa1.get("hires") or not qa2.get("hires"):
        fail.append("分辨率偏低")
    report["fail_reasons"] = fail
    report["pass"] = not fail
    (ROOT / "accept_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n请人工目检 accept_preview/snap_page_1.png 与 snap_page_2.png（Read 图片）")
    if fail:
        print("ACCEPT FAIL:", fail)
        return 2
    print("ACCEPT PASS:", out_pdf)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export WonderCV preview pages to A4 PDF")
    parser.add_argument(
        "--url",
        default="https://www.wondercv.com/cvs/6A8U_qNd/editor",
        help="WonderCV editor URL",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=4.0,
        help="Capture deviceScaleFactor (default 4)",
    )
    args = parser.parse_args(argv)
    return run_export(args.url, args.scale)


if __name__ == "__main__":
    sys.exit(main())
