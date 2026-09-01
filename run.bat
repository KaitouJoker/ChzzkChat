@echo off
chcp 65001 >nul
title Chzzk Chat Crawler

echo ========================================================
echo   Chzzk Chat Crawler - 치지직 채팅 크롤러
echo ========================================================
echo.

:: Conda 환경 활성화 시도
where conda >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    call conda activate chzzk 2>nul
) else (
    if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
        call "%USERPROFILE%\anaconda3\Scripts\activate.bat" chzzk 2>nul
    ) else if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
        call "%USERPROFILE%\miniconda3\Scripts\activate.bat" chzzk 2>nul
    ) else if exist "%LOCALAPPDATA%\miniforge3\Scripts\activate.bat" (
        call "%LOCALAPPDATA%\miniforge3\Scripts\activate.bat" chzzk 2>nul
    ) else if exist "%PROGRAMDATA%\anaconda3\Scripts\activate.bat" (
        call "%PROGRAMDATA%\anaconda3\Scripts\activate.bat" chzzk 2>nul
    ) else if exist "%PROGRAMDATA%\miniconda3\Scripts\activate.bat" (
        call "%PROGRAMDATA%\miniconda3\Scripts\activate.bat" chzzk 2>nul
    )
)

:: Python 실행 (인자가 있으면 그대로 전달)
python run.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [알림] 실행이 종료되었거나 오류가 발생했습니다.
    pause
)
