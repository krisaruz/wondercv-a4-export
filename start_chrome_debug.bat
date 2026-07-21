@echo off
chcp 65001 >nul
echo ============================================================
echo  WonderCV 导出：启动带调试端口的 Chrome
echo ============================================================
echo.
echo 步骤：
echo   1. 将关闭现有 Chrome 窗口
echo   2. 以 --remote-debugging-port=9222 重新打开
echo   3. 请在该窗口登录 WonderCV，确认简历两页预览正常
echo   4. 回到终端执行：  python export_resume.py
echo.
echo 文档：docs\WONDERCV_A4_EXPORT.md
echo.
pause

taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul

set CHROME=
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
if "%CHROME%"=="" (
  echo 未找到 chrome.exe，请手动安装 Google Chrome
  pause
  exit /b 1
)

start "" "%CHROME%" --remote-debugging-port=9222 --restore-last-session "https://www.wondercv.com/cvs/6A8U_qNd/editor"
echo.
echo Chrome 已启动（CDP 9222）。登录并确认预览后执行：
echo   python export_resume.py
echo.
pause
