@echo off
rem Startet einen Befehl in der QNX-SDP-Umgebung (mit der QNX-eigenen bash statt WSL).
call C:\Users\Admin\qnx800\qnxsdp-env.bat >nul
set PATH=%PATH%;C:\Program Files\Oracle\VirtualBox
cd /d "%~dp0.."
"C:\Users\Admin\qnx800\host\win64\x86_64\usr\bin\bash.exe" -c "%*"
