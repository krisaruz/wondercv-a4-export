# WonderCV 简历 → 清晰 A4 两页 PDF（可复现流程）

目标：从线上编辑页拿到**布局/分页与预览一致**、尽量**高清**、**去掉预览水印**的 A4 两页 PDF。

验证过的简历示例：`https://www.wondercv.com/cvs/6A8U_qNd/editor`

---

## 结论（给后续 Agent）

| 做法 | 是否可用 | 原因 |
|------|----------|------|
| 手搓 HTML/CSS 还原 | ❌ | 难 1:1，分页对不齐 |
| 控制台导出 DOM + 外链 CSS | ❌ | 缺样式，白页纯文字 |
| 控制台内联 computed style | ⚠️ | 样式近似，分页/顶栏易坏 |
| **html2canvas 截页** | ❌ | 叠字、水印错乱、第 2 页空白 |
| **Playwright 对 `[data-resume-page]` 真实像素截图** | ✅ | 布局/分页与线上一致 |
| 官方「下载 PDF」 | ✅（若有权限） | 矢量最清晰；免费预览有水印 |

**唯一推荐自动化路径：** 已登录的 Chrome → Playwright 截两页预览 → 去水印 → 高 DPR → 合成 A4 PDF。

核心脚本：`export_resume.py`（封装 `_capture_via_cdp.py`）

---

## 前置条件

1. Windows + 已安装 Google Chrome  
2. Python 3.11+，依赖：

```bat
python -m pip install -r requirements.txt
python -m playwright install chromium
```

3. 本机可打开 WonderCV 编辑页并看到**两页预览**

---

## 标准流程（按顺序）

### Step A — 保证浏览器可被自动化登录态使用

**方式 1（推荐，可复用已开标签）：CDP 9222**

```bat
start_chrome_debug.bat
```

作用：关闭现有 Chrome，用 `--remote-debugging-port=9222` 启动，并打开编辑页。  
然后在该窗口**登录**，确认两页预览正常。

**方式 2（兜底）：持久化 profile**

若不存在 CDP 9222，`export_resume.py` 会使用：

`.chrome-wondercv-profile/`

首次需在弹出的 Chrome 里登录；之后可复用登录态。

### Step B — 一键导出

```bat
python export_resume.py
```

可选参数：

```bat
python export_resume.py --url https://www.wondercv.com/cvs/<ID>/editor
python export_resume.py --scale 4
```

### Step C — 验收标准（必须过）

脚本会写：

- `resume_a4.pdf` — 交付物  
- `accept_preview/snap_page_1.png` / `snap_page_2.png` — 目检  
- `accept_report.json` — 机器验收  

**机器验收：**

- PDF 正好 **2 页**
- 纸张约 **A4（210×297mm）**
- 截图像素宽 **≥ 1400**（推荐 scale=4 → ~2880）
- 第 1 页顶部不是「整块深蓝坏图」
- 第 2 页上半有正文（不是近乎空白）

**人工目检（Agent 必须 Read 两张 preview 图）：**

1. 第 1 页：头像、姓名、教育/工作/项目，圆角卡片，无叠字  
2. 第 2 页：项目续写 + 个人总结，分页与线上一致  
3. 无明显「超级简历 / 仅供预览」大水印、无右下角客服气泡  
4. 文字清晰（高 DPR），不是发虚低清图  

任一目检失败 → **不得**向用户宣称通过。

---

## 脚本在做什么（实现要点）

文件：`_capture_via_cdp.py`

1. 连接 `http://127.0.0.1:9222`（CDP），或启动 persistent Chrome  
2. 定位含 `/cvs/` 的 WonderCV 编辑页  
3. `Emulation.setDeviceMetricsOverride` 设 `deviceScaleFactor`（默认 **4**）  
4. 去水印 / 浮层：  
   - `.cover` / watermark class  
   - `img.cv-pattern` 预览底纹  
   - `logo.wondercv.com` 等非头像图  
   - 清空可疑 `background-image`  
   - 隐藏 udesk / 右下角 fixed 小部件  
5. 对 `[data-resume-page]` 第 1、2 页分别 `locator.screenshot()`（**不要**改 scale/负 margin 布局）  
6. 缩放到 300dpi A4，用 **img2pdf** 无损嵌入 PNG  
7. 写出 `accept_report.json`；失败 `exit 2`

**关键约束：**

- 不要对整棵 DOM `height/overflow: auto !important`「解锁」——会毁掉顶栏，出现大块深蓝坏图  
- 不要用 html2canvas  
- 第 2 页留白是线上分页正常现象，不要误判为失败（看上半是否有正文）

---

## 常见故障

**1. `auth-signin` / 找不到 `[data-resume-page]`**  
→ 未登录。用 `start_chrome_debug.bat` 登录后再跑。

**2. 未检测到 CDP 9222**  
→ 用户没跑 bat，或 Chrome 不是 debug 实例。脚本会尝试 persistent profile。

**3. PDF 发虚**  
→ 确认 `scale>=3`（默认 4），且 `accept_report.json` 里 page 宽 ≥1400。

**4. 仍有水印**  
→ 检查 cleanup 是否杀掉 `cover` / `cv-pattern`；预览会员水印 DOM 若变更，需更新选择器。  
官方无水印矢量 PDF 仍只有站点正式下载最稳。

**5. 第 1 页顶部整块深蓝**  
→ 错误地「解锁」了布局。回到本流程，只截图、不改分页结构。

---

## 目录结构

```
export_resume.py              # 入口
_capture_via_cdp.py           # 核心实现
start_chrome_debug.bat        # 启动可调试 Chrome
requirements.txt
docs/WONDERCV_A4_EXPORT.md    # 本文档
.cursor/rules/wondercv-a4-export.mdc
resume_a4.pdf                 # 本地输出（勿提交）
accept_preview/               # 本地预览图（勿提交）
.chrome-wondercv-profile/     # 本地登录缓存（勿提交）
```

勿提交：`.chrome-wondercv-profile/`、`.env`、`resume_a4.pdf`、含真实 Cookie 的文件。
