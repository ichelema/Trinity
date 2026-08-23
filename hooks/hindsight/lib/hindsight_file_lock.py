"""Lock file interprocesso cross-platform (flock su POSIX, msvcrt su Windows)."""

from __future__ import annotations

import contextlib
import os
import time


@contextlib.contextmanager
def file_lock(path, timeout: float = 2.0, chmod: int | None = None):
    """Lock interprocesso best-effort su `path` (usa `path + ".lock"`).
    flock su POSIX, msvcrt.locking su Windows; polling non bloccante fino a
    `timeout`. Yield di `acquired`: True se il lock e' stato preso. Non solleva
    mai: qualunque errore (import, open, acquire) degrada a acquired=False —
    sta al chiamante decidere se procedere comunque o saltare il corpo.
    Il lock e' legato al fd, quindi si rilascia da solo se il processo muore.
    `chmod` (es. 0o600) viene applicato best-effort al file .lock."""
    lock_path = str(path) + ".lock"
    handle = None
    release = None
    acquired = False
    # Setup in un try SENZA yield: lo yield deve stare FUORI da questo try. Se
    # ci finisse dentro, un'eccezione nel CORPO del with rientrerebbe qui via
    # throw(), l'except farebbe un secondo yield e il chiamante riceverebbe
    # RuntimeError("generator didn't stop after throw()") che maschera
    # l'errore originale.
    try:
        try:
            import fcntl

            def acquire(fd):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def unlock(fd):
                fcntl.flock(fd, fcntl.LOCK_UN)

        except ImportError:
            import msvcrt

            # msvcrt.locking blocca dalla posizione corrente: seek(0) cosi'
            # tutti i contendenti bloccano lo stesso byte 0 (per flock la
            # posizione e' ininfluente).
            def acquire(fd):
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

            def unlock(fd):
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

        handle = open(lock_path, "a+b")
        if chmod is not None:
            try:
                os.chmod(lock_path, chmod)
            except OSError:
                pass
        deadline = time.monotonic() + timeout
        while True:
            try:
                acquire(handle.fileno())
                acquired = True
                release = unlock
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break  # timeout: acquired resta False (best-effort)
                time.sleep(0.02)
    except Exception:
        pass  # qualunque problema col lock non deve rompere il chiamante
    try:
        yield acquired
    finally:
        if handle is not None:
            if release is not None:
                try:
                    release(handle.fileno())
                except Exception:
                    pass
            handle.close()
