@echo off
REM ============================================================
REM run_briefing.bat — Morning Briefing System 実行バッチ
REM
REM このファイルのパスをタスクスケジューラに登録してください。
REM 文字コード: UTF-8 (BOM あり) で保存してください。
REM ============================================================

REM スクリプトのあるディレクトリに移動
cd /d "%~dp0"

REM Python の場所（仮想環境がある場合は venv\Scripts\python.exe に変更）
REM 例: set PYTHON_PATH=C:\Users\YourName\morning_briefing\venv\Scripts\python.exe
set PYTHON_PATH=python

REM ログ出力先（bat 実行ログ）
set BAT_LOG=%~dp0logs\bat_runner.log

REM 実行
echo [%DATE% %TIME%] Morning Briefing 開始 >> "%BAT_LOG%"
"%PYTHON_PATH%" "%~dp0main.py"

REM 終了コードをログ
if %ERRORLEVEL% EQU 0 (
    echo [%DATE% %TIME%] 正常終了 (exit code: 0) >> "%BAT_LOG%"
) else (
    echo [%DATE% %TIME%] エラー終了 (exit code: %ERRORLEVEL%) >> "%BAT_LOG%"
)
