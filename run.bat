@echo off
setlocal
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -m dependency_graph %*
endlocal

