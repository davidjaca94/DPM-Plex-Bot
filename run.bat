echo off
cls

call activate bots

echo 1 - Run
echo 2 - Run (with watermark)
echo 3 - Run (in facade mode)
echo.

set /p preg0= Select an option: 

echo.
if %preg0% == 1 python tg_bot.py
if %preg0% == 2 python tg_bot.py --watermark
if %preg0% == 3 python tg_bot.py --facade
echo.

pause
