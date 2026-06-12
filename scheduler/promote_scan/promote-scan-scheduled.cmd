@echo off
REM ===========================================================================
REM promote-scan-scheduled.cmd — Ponte Windows -> MSYS2 per System Scheduler.
REM
REM Job SETTIMANALE: scan + triage dei bank Hindsight di progetto alla ricerca
REM di fatti candidati alla promozione sul bank core. NON promuove mai nulla
REM (il move resta a /trinity:promote con review umana): genera solo il report
REM logs/promote-candidates.json e, se ci sono candidati, apre un alert.
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
C:\msys64\usr\bin\zsh.exe --login -c "exec zsh /d/AI/Claude/Trinity/scheduler/promote_scan/promote-scan-scheduled.sh"
