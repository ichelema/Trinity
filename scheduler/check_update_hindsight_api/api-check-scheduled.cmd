@echo off
REM ===========================================================================
REM api-check-scheduled.cmd — Ponte Windows -> MSYS2 per System Scheduler.
REM
REM System Scheduler e' un'app Windows e non conosce l'ambiente MSYS2: qui
REM impostiamo MSYSTEM (sottosistema UCRT64) e CHERE_INVOKING (non fare cd a
REM ~), poi entriamo in una login shell che esegue lo script di logica.
REM
REM Da mettere nel campo "Application" di System Scheduler (Parameters vuoto,
REM Working Dir = D:\AI\Claude\Trinity, State = Minimized o Hidden).
REM ===========================================================================

set "MSYSTEM=UCRT64"
set "CHERE_INVOKING=1"
set "MSYS2_PATH_TYPE=strict"

set "HOME=C:\msys64\home\%USERNAME%"
set "MISE_DATA_DIR=C:\msys64\home\%USERNAME%\.local\share\mise"
set "MISE_CACHE_DIR=C:\msys64\home\%USERNAME%\.cache\mise"
C:\msys64\usr\bin\zsh.exe --login -c "exec zsh /d/AI/Claude/Trinity/scheduler/check_update_hindsight_api/api-check-scheduled.sh"
