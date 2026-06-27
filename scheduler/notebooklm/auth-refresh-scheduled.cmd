@echo off
REM ===========================================================================
REM auth-refresh-scheduled.cmd - Ponte Windows -> MSYS2 per System Scheduler.
REM
REM System Scheduler e' un'app Windows e non conosce l'ambiente MSYS2: qui
REM impostiamo MSYSTEM (sottosistema UCRT64), il PATH di MSYS per i coreutils,
REM poi eseguiamo lo script di logica con bash --noprofile --norc, che rinnova
REM la sessione notebooklm (auth refresh) per non far scadere i cookie.
REM NB: si usa bash --noprofile --norc (niente config utente) perche' la config
REM di login dell'utente fa partire zsh interattivo (prompt) invece dello script.
REM
REM Da mettere nel campo "Application" di System Scheduler (Parameters vuoto,
REM Working Dir = E:\AI\Claude\Trinity, State = Minimized o Hidden).
REM Cadenza consigliata: ogni 15-20 minuti (o piu' rada se il PC e' spesso spento).
REM ===========================================================================

set "MSYSTEM=UCRT64"
set "CHERE_INVOKING=1"
set "MSYS2_PATH_TYPE=strict"

set "HOME=E:\msys64\home\Sphynx"
set "MISE_DATA_DIR=E:\msys64\home\Sphynx\.local\share\mise"
set "MISE_CACHE_DIR=E:\msys64\home\Sphynx\.cache\mise"
REM Cartella del progetto: esplicita, cosi' lo script non dipende da come zsh
REM risolve il path (in zsh BASH_SOURCE e' vuoto) ne' dall'ambiente Windows.
set "TRINITY_PLUGIN_DIR=E:\AI\Claude\Trinity"
REM PATH di MSYS per i comandi di sistema (date, tr, cygpath, find, stat...),
REM dato che bash gira --noprofile --norc e non eredita /etc/profile.
set "PATH=E:\msys64\ucrt64\bin;E:\msys64\usr\bin;%PATH%"
E:\msys64\usr\bin\bash.exe --noprofile --norc "/e/AI/Claude/Trinity/scheduler/notebooklm/auth-refresh-scheduled.sh"
