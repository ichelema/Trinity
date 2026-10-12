# Il firewall ENINET firma certificati senza Authority Key Identifier: Python 3.13
# li rifiuta con VERIFY_X509_STRICT. Catena, bundle CA e hostname restano verificati.
# Caricato da solo all'avvio di Python quando start-hindsight mette questa cartella
# in PYTHONPATH (solo con HS_TLS_NO_X509_STRICT, definita in C:/certs/proxy.env).
import ssl

_orig = ssl.create_default_context


def _create_default_context(*args, **kwargs):
    ctx = _orig(*args, **kwargs)
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


ssl.create_default_context = _create_default_context
