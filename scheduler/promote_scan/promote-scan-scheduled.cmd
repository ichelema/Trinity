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
REM Working Dir = E:\AI\Claude\Trinity, State = Minimized o Hidden).
REM ===========================================================================

set "MSYSTEM=UCRT64"
set "CHERE_INVOKING=1"
set "MSYS2_PATH_TYPE=strict"

set "HOME=E:\msys64\home\Sphynx"
set "MISE_DATA_DIR=E:\msys64\home\Sphynx\.local\share\mise"
set "MISE_CACHE_DIR=E:\msys64\home\Sphynx\.cache\mise"
REM Cartella del progetto: esplicita, cosi' lo script non dipende da BASH_SOURCE
REM (vuoto in zsh) ne' dall'ambiente Windows.
set "TRINITY_PLUGIN_DIR=E:\AI\Claude\Trinity"
REM PATH di MSYS per i comandi di sistema (date, tr, cygpath, find, curl...),
REM dato che bash gira --noprofile --norc e non eredita /etc/profile.
set "PATH=E:\msys64\ucrt64\bin;E:\msys64\usr\bin;%PATH%"
E:\msys64\usr\bin\bash.exe --noprofile --norc "/e/AI/Claude/Trinity/scheduler/promote_scan/promote-scan-scheduled.sh"
