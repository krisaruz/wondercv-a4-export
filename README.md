# WonderCV → 高清 A4 PDF

把 WonderCV 编辑页预览导出为**高清 A4 两页 PDF**（布局/分页与预览一致，并尽量去掉预览水印）。

## 快速开始

```bat
python -m pip install -r requirements.txt
python -m playwright install chromium

REM 1) 启动可调试 Chrome，登录编辑页
start_chrome_debug.bat

REM 2) 导出
python export_resume.py
```

产物：

- `resume_a4.pdf`
- `accept_preview/snap_page_*.png`
- `accept_report.json`

## 文档

→ **[docs/WONDERCV_A4_EXPORT.md](docs/WONDERCV_A4_EXPORT.md)**

Cursor 规则：`.cursor/rules/wondercv-a4-export.mdc`
