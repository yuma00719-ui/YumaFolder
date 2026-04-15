@echo off
REM ============================================================
REM setup_task_scheduler.bat
REM
REM Windowsタスクスケジューラに「毎朝7時に実行」を登録します。
REM 管理者権限で実行してください（右クリック → 管理者として実行）。
REM ============================================================

REM スクリプトのあるディレクトリ
set SCRIPT_DIR=%~dp0

REM タスク名
set TASK_NAME=MorningBriefing

REM 既存のタスクを削除（エラーは無視）
schtasks /Delete /TN "%TASK_NAME%" /F 2>nul

REM タスクを新規作成
REM   /SC DAILY    : 毎日
REM   /ST 07:00    : 07:00 に実行
REM   /RL HIGHEST  : 最高権限（ネットワーク接続等に必要な場合あり）
schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "\"%SCRIPT_DIR%run_briefing.bat\"" ^
    /SC DAILY ^
    /ST 07:00 ^
    /RL HIGHEST ^
    /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ タスクスケジューラへの登録が完了しました。
    echo    タスク名: %TASK_NAME%
    echo    実行時刻: 毎朝 07:00
    echo    実行ファイル: %SCRIPT_DIR%run_briefing.bat
    echo.
    echo 確認するには: タスクスケジューラ → タスクスケジューラライブラリ → %TASK_NAME%
) else (
    echo.
    echo ❌ 登録に失敗しました。管理者権限で実行しているか確認してください。
)

pause
