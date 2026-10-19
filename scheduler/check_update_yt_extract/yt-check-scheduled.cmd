@echo off
REM ===========================================================================
REM yt-check-scheduled.cmd — Ponte Windows -> MSYS2 per System Scheduler.
REM
REM System Scheduler non conosce l'ambiente MSYS2: qui impostiamo MSYSTEM
REM (sottosistema UCRT64), il PATH di MSYS, poi eseguiamo lo script di logica
REM con bash --noprofile --norc (niente config utente).
REM
REM Da mettere nel campo "Application" di System Scheduler (Parameters vuoto,
REM Working Dir = D:\AI\Claude\Trinity, State = Minimized o Hidden).
REM ===========================================================================

set "MSYSTEM=UCRT64"
set "CHERE_INVOKING=1"
set "MSYS2_PATH_TYPE=strict"

set "HOME=D:\msys64\home\Sphynx"
set "MISE_DATA_DIR=D:\msys64\home\Sphynx\.local\share\mise"
set "MISE_CACHE_DIR=D:\msys64\home\Sphynx\.cache\mise"
set "TRINITY_PLUGIN_DIR=D:\AI\Claude\Trinity"
set "PATH=D:\msys64\ucrt64\bin;D:\msys64\usr\bin;%PATH%"
D:\msys64\usr\bin\bash.exe --noprofile --norc "/d/AI/Claude/Trinity/scheduler/check_update_yt_extract/yt-check-scheduled.sh"
