@echo off
setlocal
set "ROOT=%~dp0"
"C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "%ROOT%chatbot_terminal.py" %*
