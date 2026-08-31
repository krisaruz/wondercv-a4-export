# -*- coding: utf-8 -*-
"""
连接已登录的 WonderCV 编辑页：
1) 去掉预览水印/客服浮层
2) 高 DPI 真实像素截取两页
3) 合成清晰 A4 PDF

推荐入口：export_resume.py
流程文档：docs/WONDERCV_A4_EXPORT.md
"""
from __future__ import annotations

import base64
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_PDF = ROOT / "resume_a4.pdf"
PREVIEW = ROOT / "accept_preview"
# A4 @ 300dpi
A4 = (2480, 3508)


def cdp_available(port=9222) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def qa(img, label):
    from PIL import ImageStat

    w, h = img.size
    top = img.crop((0, 0, w, max(1, int(h * 0.15))))
    body = img.crop((0, int(h * 0.08), w, int(h * 0.45)))
    st_t, st_b = ImageStat.Stat(top), ImageStat.Stat(body)
    tm, tv = sum(st_t.mean) / 3, sum(st_t.var) / 3
    bm, bv = sum(st_b.mean) / 3, sum(st_b.var) / 3
    dark_flat_top = tm < 70 and tv < 250
    blankish = bv < 200 and bm > 245
    return {
        "label": label,
        "size": [w, h],
        "top_mean": round(tm, 1),
        "top_var": round(tv, 1),
        "body_var": round(bv, 1),
        "dark_flat_top": dark_flat_top,
        "blankish": blankish,
        "ok": (not dark_flat_top) and (not blankish),
        "hires": w >= 1400,  # 期望高清
    }


def pages_to_pdf(im1, im2, out_path: Path):
    """缩放到 300dpi A4 后尽量无损写入 PDF。"""
    from PIL import Image

    tmp_dir = ROOT / ".pdf_pages"
    tmp_dir.mkdir(exist_ok=True)
    paths = []
    for idx, im in enumerate((im1, im2), 1):
        filled = im.resize(A4, Image.Resampling.LANCZOS)
        p = tmp_dir / f"a4_{idx}.png"
        filled.save(p, "PNG", optimize=True)
        paths.append(p)

    try:
        import img2pdf

        a4_pt = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
        layout = img2pdf.get_layout_fun(a4_pt)
        with open(out_path, "wb") as f:
            f.write(img2pdf.convert([str(x) for x in paths], layout_fun=layout))
        print("pdf via img2pdf (lossless png embed)")
    except Exception as e:
        print("img2pdf fallback:", e)
        pages = [Image.open(p).convert("RGB") for p in paths]
        pages[0].save(
            out_path,
            "PDF",
            resolution=300.0,
            save_all=True,
            append_images=pages[1:],
        )


def prepare_page(page, scale: float = 3.0):
    """去水印 + 提高设备像素比。"""
    page.wait_for_selector("[data-resume-page]", timeout=60000)
    page.wait_for_timeout(1500)

    # 提高 DPR（清晰度关键）
    try:
        client = page.context.new_cdp_session(page)
        metrics = page.evaluate(
            "() => ({w: Math.max(1200, window.innerWidth), h: Math.max(900, window.innerHeight)})"
        )
        client.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": int(metrics["w"]),
                "height": int(metrics["h"]),
                "deviceScaleFactor": scale,
                "mobile": False,
            },
        )
        print(f"deviceScaleFactor={scale}")
    except Exception as e:
        print("setDeviceMetricsOverride fail:", e)

    removed = page.evaluate(
        """() => {
  const killed = [];
  const kill = (el, why) => {
    if (!el) return;
    el.remove();
    killed.push(why);
  };

  // 浮层 / 客服
  ['wondercv-capture-tip','wondercv-capture-panel','wondercv-snapshot-panel','wondercv-print-panel']
    .forEach(id => kill(document.getElementById(id), id));
  document.querySelectorAll(
    '#udesk_container_self, .udesk, [class*="udesk" i], .service-popup, iframe[src*="udesk"]'
  ).forEach(el => kill(el, 'udesk'));

  // 水印遮罩 + 预览底纹图（要干净导出，去掉 cv-pattern）
  document.querySelectorAll('.cover, .cover-transparent').forEach(el => kill(el, 'cover'));
  document.querySelectorAll(
    '[class*="watermark" i], [class*="water-mark" i], [class*="shuiyin" i], img.cv-pattern, .cv-pattern'
  ).forEach(el => kill(el, 'watermark-or-pattern'));
  document.querySelectorAll('[data-resume-page] img').forEach(img => {
    const src = img.getAttribute('src') || '';
    if (/logo\.wondercv\.com|watermark|shuiyin|banner|pattern|preview/i.test(src)) {
      // 保留用户头像（一般在 oss / avatars 路径）
      if (/avatar|accounts\/avatars|user.*photo/i.test(src)) return;
      kill(img, 'wm-img');
    }
  });

  // 带「超级简历 / 仅供预览 / 水印」文案的绝对定位大层
  document.querySelectorAll('div, section, span').forEach(el => {
    const t = (el.innerText || '').replace(/\\s+/g, '');
    if (!t) return;
    if (t.length > 80) return;
    if (/超级简历|仅供预览|预览展示|下载版本无水印|该水印/.test(t)) {
      const st = getComputedStyle(el);
      const abs = st.position === 'absolute' || st.position === 'fixed';
      const big = el.getBoundingClientRect().width > 120;
      if (abs || big) kill(el, 'watermark-text:' + t.slice(0, 20));
    }
  });

  // 背景图水印：简历页内一律去掉 background-image（顶栏 cv-pattern 装饰除外）
  document.querySelectorAll(
    '[data-resume-page], [data-resume-page] *, .resume-main, .resume-main *'
  ).forEach(el => {
    if (el.classList && el.classList.contains('cv-pattern')) return;
    if (el.classList && el.classList.contains('user-avatar-image')) return;
    const bg = getComputedStyle(el).backgroundImage || '';
    if (bg && bg !== 'none') {
      // 头像用 background-image，保留
      if (el.classList && /avatar|photo|user-avatar/i.test(el.className)) return;
      el.style.setProperty('background-image', 'none', 'important');
      killed.push('bg-image-cleared');
    }
  });
  // 半透明覆盖层
  document.querySelectorAll('[data-resume-page] *').forEach(el => {
    const st = getComputedStyle(el);
    if (st.pointerEvents === 'none' && parseFloat(st.opacity) > 0 && parseFloat(st.opacity) < 0.5) {
      const r = el.getBoundingClientRect();
      if (r.width > 200 && r.height > 200) {
        el.style.setProperty('display', 'none', 'important');
        killed.push('opacity-overlay');
      }
    }
  });

  // 注入强力隐藏（含伪元素）
  let st = document.getElementById('wondercv-nowm');
  if (!st) {
    st = document.createElement('style');
    st.id = 'wondercv-nowm';
    document.head.appendChild(st);
  }
  st.textContent = `
    .cover, .cover-transparent,
    [class*="watermark" i], [class*="water-mark" i], [class*="shuiyin" i] {
      display: none !important; opacity: 0 !important; visibility: hidden !important;
    }
    [data-resume-page]::before, [data-resume-page]::after,
    .main::before, .main::after, .one-page-container::before, .one-page-container::after,
    .content::before, .content::after {
      display: none !important; content: none !important; background: none !important;
    }
  `;

  return { killed: killed.length, samples: killed.slice(0, 20) };
}"""
    )
    print("watermark cleanup:", removed)
    page.wait_for_timeout(500)


def capture_with_page(page, scale: float = 3.0):
    from PIL import Image

    prepare_page(page, scale=scale)
    n = page.locator("[data-resume-page]").count()
    print("data-resume-page count:", n)
    if n < 2:
        raise RuntimeError("预览不足两页")

    hide_floaters = """() => {
  document.querySelectorAll(
    '#udesk_container_self, .udesk, [class*="udesk" i], .service-popup,' +
    'iframe[src*="udesk"], [class*="ai-mentor" i], [class*="float" i],' +
    '.entry-tooltip, .tips-content, [class*="chat" i]'
  ).forEach(el => {
    el.style.setProperty('display', 'none', 'important');
    el.style.setProperty('visibility', 'hidden', 'important');
    el.style.setProperty('opacity', '0', 'important');
    el.style.setProperty('pointer-events', 'none', 'important');
  });
  // 固定定位且靠右下的小部件
  document.querySelectorAll('body *').forEach(el => {
    const st = getComputedStyle(el);
    if (st.position !== 'fixed' && st.position !== 'sticky') return;
    const r = el.getBoundingClientRect();
    if (r.width < 420 && r.height < 220 && r.right > innerWidth - 280 && r.bottom > innerHeight - 280) {
      el.style.setProperty('display', 'none', 'important');
    }
  });
}"""

    imgs = []
    client = page.context.new_cdp_session(page)
    # Emulation override 是 per-session 的，新 CDP session 不继承 prepare_page 设的状态，
    # 必须在同一个 session 里重新设。
    # height 留足余量（一页约 1018，给 1500），保证元素完整在视口内，避免 clip 被视口裁剪
    metrics = page.evaluate(
        "() => ({w: Math.max(1200, window.innerWidth), h: Math.max(1500, window.innerHeight)})"
    )
    client.send(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": int(metrics["w"]),
            "height": int(metrics["h"]),
            "deviceScaleFactor": scale,
            "mobile": False,
        },
    )
    page.wait_for_timeout(500)

    # 切到 print media：编辑页的 fixed/sticky 顶栏、侧边工具栏在 print 下通常不显示，
    # 简历正文不受遮挡，截图顶部不会被 WonderCV UI 盖住
    try:
        client.send("Emulation.setEmulatedMedia", {"media": "print"})
        page.wait_for_timeout(500)
    except Exception as e:
        print("setEmulatedMedia print fail:", e)

    for i in range(2):
        page.evaluate(hide_floaters)
        loc = page.locator("[data-resume-page]").nth(i)
        # 手动 scrollIntoView 顶部对齐，并等滚动稳定。
        # scroll_into_view_if_needed 在某些布局下不会把顶部对齐到视口顶，
        # 导致 bounding_box.y 为负，CDP clip 会把负 y clamp 到 0 → 顶部被裁。
        page.evaluate(
            """(idx) => {
              const el = document.querySelectorAll('[data-resume-page]')[idx];
              if (el) el.scrollIntoView({block: 'start', inline: 'start'});
            }""",
            i,
        )
        page.wait_for_timeout(600)
        page.evaluate(hide_floaters)
        page.wait_for_timeout(200)
        box = loc.bounding_box()
        if not box:
            raise RuntimeError(f"第{i+1}页 bounding_box 为空")
        if box["y"] < 0:
            # 元素顶部仍在视口上方，再滚一次
            page.evaluate(
                """(idx) => {
                  const el = document.querySelectorAll('[data-resume-page]')[idx];
                  if (el) el.scrollIntoView({block: 'start'});
                }""",
                i,
            )
            page.wait_for_timeout(500)
            box = loc.bounding_box()
        if box["y"] < 0:
            # 还不行就强制 window.scrollTo 让元素顶到视口顶
            page.evaluate(
                """(idx) => {
                  const el = document.querySelectorAll('[data-resume-page]')[idx];
                  if (!el) return;
                  const r = el.getBoundingClientRect();
                  window.scrollBy(0, r.top - 8);
                }""",
                i,
            )
            page.wait_for_timeout(500)
            box = loc.bounding_box()
        if box["y"] < 0 or box["y"] + box["height"] > metrics["h"]:
            print(f"warn: page{i+1} box 仍不在视口内，y={box['y']}, h={box['height']}")
        r = client.send(
            "Page.captureScreenshot",
            {
                "format": "png",
                "captureBeyondViewport": True,
                "clip": {
                    "x": box["x"],
                    "y": max(0.0, box["y"]),
                    "width": box["width"],
                    "height": box["height"],
                    "scale": 1,
                },
            },
        )
        im = Image.open(io.BytesIO(base64.b64decode(r["data"]))).convert("RGB")
        imgs.append(im)
        print(f"page{i+1} size:", im.size, "css box:", [round(v, 1) for v in (box["x"], box["y"], box["width"], box["height"])])

    # 还原 media，避免影响后续
    try:
        client.send("Emulation.setEmulatedMedia", {"media": ""})
    except Exception:
        pass

    return imgs[0], imgs[1], page.url


def find_wondercv_page(browser):
    for ctx in browser.contexts:
        for pg in ctx.pages:
            u = pg.url or ""
            if "wondercv.com" in u and "/cvs/" in u and "auth" not in u:
                return pg
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if "wondercv.com" in (pg.url or ""):
                return pg
    return None


def main():
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader

    PREVIEW.mkdir(exist_ok=True)
    report = {"method": None}
    scale = 4.0

    with sync_playwright() as p:
        context = None
        browser = None

        if cdp_available(9222):
            print("连接 CDP 9222 …")
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            report["method"] = "cdp"
            page = find_wondercv_page(browser)
            if not page:
                raise SystemExit("已连上 Chrome，但没找到简历编辑页，请先打开编辑页")
            print("tab:", page.url)
        else:
            print("无 CDP，使用本地 profile …")
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
            page = None
            for pg in context.pages:
                if "wondercv.com" in (pg.url or "") and "/cvs/" in (pg.url or ""):
                    page = pg
                    break
            if page is None:
                page = context.new_page()
                page.goto(
                    "https://www.wondercv.com/cvs/6A8U_qNd/editor",
                    wait_until="domcontentloaded",
                    timeout=90000,
                )
            try:
                page.wait_for_selector("[data-resume-page]", timeout=120000)
            except Exception:
                print("未检测到预览，url=", page.url)
                context.close()
                sys.exit(4)

        im1, im2, url = capture_with_page(page, scale=scale)
        report["url"] = url

        if context:
            context.close()

    im1.save(PREVIEW / "snap_page_1.png")
    im2.save(PREVIEW / "snap_page_2.png")
    im1.save(ROOT / "wondercv_page_1.png")
    im2.save(ROOT / "wondercv_page_2.png")

    qa1, qa2 = qa(im1, "page1"), qa(im2, "page2")
    print("qa1:", qa1)
    print("qa2:", qa2)

    pages_to_pdf(im1, im2, OUT_PDF)
    reader = PdfReader(str(OUT_PDF))
    report.update(
        {
            "pdf": str(OUT_PDF),
            "page_count": len(reader.pages),
            "scale": scale,
            "qa": {"page1": qa1, "page2": qa2},
            "note": "截图导出；已尝试去除预览水印；高 DPR 提升清晰度",
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
        fail.append("分辨率偏低(期望>=1400px宽)")
    report["fail_reasons"] = fail
    report["pass"] = not fail
    (ROOT / "accept_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if fail:
        sys.exit(2)
    print("ACCEPT PASS:", OUT_PDF)


if __name__ == "__main__":
    main()
