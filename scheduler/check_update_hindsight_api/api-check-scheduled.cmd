@echo off
REM ===========================================================================
REM api-check-scheduled.cmd — Ponte Windows -> MSYS2 per System Scheduler.
REM
REM System Scheduler e' un'app Windows e non conosce l'ambiente MSYS2: qui
REM impostiamo MSYSTEM (sottosistema UCRT64), il PATH di MSYS, poi eseguiamo lo
REM script di logica con bash --noprofile --norc (niente config utente, che
REM altrimenti farebbe partire zsh interattivo invece dello script).
REM
REM Da mettere nel campo "Application" di System Scheduler (Parameters vuoto,
REM Working Dir = E:\AI\Claude\Trinity, State = Minimized o Hidden).
REM ===========================================================================

set "MSYSTEM=UCRT64"
set "CHERE_INVOKING=1"
set "MSYS2_PATH_TYPE=strict"

set "HOME=E:\msys64\home\Sphynx"
set "MISE_DATA_DIR=E:\msys64\home\Sphynx\.local\share\mise"
set "MISE_CACHE_DIR=E:\msys64\home\Sphynx\.cache\mise"
set "TRINITY_PLUGIN_DIR=E:\AI\Claude\Trinity"
set "PATH=E:\msys64\ucrt64\bin;E:\msys64\usr\bin;%PATH%"
E:\msys64\usr\bin\bash.exe --noprofile --norc "/e/AI/Claude/Trinity/scheduler/check_update_hindsight_api/api-check-scheduled.sh"
