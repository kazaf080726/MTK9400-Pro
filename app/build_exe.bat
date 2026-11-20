@echo off
rem 重新打包 MTK9400.exe
rem 需要 mtkclient 目录下的 python.exe (3.12) 已安装 pyinstaller
setlocal
set "REPO=%~dp0.."
set "PY=%REPO%\python.exe"

if not exist "%PY%" (
  echo [ERROR] python.exe not found: %PY%
  pause
  exit /b 1
)

copy /y "%REPO%\mtk.py" "%~dp0mtk.py" >nul
copy /y "%REPO%\gpt_partitions.txt" "%~dp0gpt_partitions.txt" >nul

cd /d "%~dp0"
"%PY%" -m PyInstaller --noconfirm --clean --onefile --console --name MTK9400 ^
  --paths "%REPO%" ^
  --add-data "%REPO%\mtkclient\Loader\OPLUS_DA_mt6991.bin;mtkclient\Loader" ^
  --add-data "%REPO%\mtkclient\Loader\OPLUS_mt6991.auth;mtkclient\Loader" ^
  --add-data "%REPO%\mtkclient\payloads;mtkclient\payloads" ^
  --add-data "%REPO%\mtkclient\Windows;mtkclient\Windows" ^
  --add-data "%REPO%\mtkclient\Library\Filesystem\bin;mtkclient\Library\Filesystem\bin" ^
  --add-data "%~dp0gpt_partitions.txt;." ^
  launcher.py

echo.
echo 输出: %~dp0dist\MTK9400.exe
pause
