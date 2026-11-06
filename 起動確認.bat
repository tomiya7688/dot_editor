@echo off
rem ワンクリック起動確認: ダブルクリックするだけで、自動確認と目で見る確認を順に行います。
rem 手順: docs\起動確認の手順.md  /  設計: docs\design\startup-check.md
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0"

rem Pythonを探す: 開発用の仮想環境 > py ランチャー > python の順。
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Pythonが見つかりません。Python 3.10以上をインストールしてから、もう一度実行してください。
  popd
  pause
  exit /b 2
)

%PY% scripts\startup_check.py
set RESULT=%ERRORLEVEL%
popd
echo.
echo 終了値: %RESULT%  (0=成功 / 1=失敗 / 2=確認できなかった)
pause
exit /b %RESULT%
