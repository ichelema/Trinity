#!/usr/bin/env python3
"""Lint del report di /trinity:dream.

Uso:  python dream_report_lint.py <report.md> [--apply]

Controlli strutturali (sempre): ID A<n> univoci e sequenziali da 1, contatori
dell'intestazione uguali alle azioni trovate (totale e per sezione), campi
obbligatori per tipo di azione, solo mm-refresh pre-flaggata in audit.
Con --apply: ogni azione flaggata che altera o ritira una memoria esistente
(hs-invalidate, hs-update, hs-correct-doc, file-update, file-delete) deve avere
una `Verifica:` sul campo, non "solo daily/trascrizioni/bank".
Exit 0 = PASS, 1 = FAIL, 2 = uso errato.
"""
import re
import sys

ACTION_RE = re.compile(r"^- \[( |x)\] \*\*A(\d+)\*\* · ([a-z-]+) · (.*)$")
HEADER_RE = re.compile(
    r"^- Azioni proposte: (\d+) \(obsolete: (\d+), aggiornamenti: (\d+), "
    r"nuove: (\d+), policy: (\d+), mental model: (\d+)\)"
)
SECTIONS = {
    "## Obsolete": "obsolete",
    "## Da aggiornare": "aggiornamenti",
    "## Nuove da salvare": "nuove",
    "## Violazioni policy MEMORY.md": "policy",
    "## Mental model": "mental model",
}
TYPES = {
    "hs-invalidate", "hs-update", "hs-correct-doc", "hs-retain",
    "file-update", "file-delete", "file-create", "policy-migrate", "mm-refresh",
}
NEEDS_VERIFICA = TYPES - {"policy-migrate", "mm-refresh"}
NEEDS_PROPOSTA = {"hs-update", "hs-correct-doc", "hs-retain",
                  "file-update", "file-create", "policy-migrate"}
ALTERS_EXISTING = {"hs-invalidate", "hs-update", "hs-correct-doc",
                   "file-update", "file-delete"}
NOT_FIELD_VERIFIED = re.compile(r"^\s*solo\b", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s+- ([A-Za-z ]+?)(?: \([^)]*\))?:\s*(.*)$")


def parse(text):
    """Ritorna (header|None, [azioni], allineata:bool). Ogni azione e' un dict."""
    header = None
    actions = []
    section = None
    allineata = "Memoria allineata, nessuna azione proposta" in text
    for line in text.splitlines():
        m = HEADER_RE.match(line)
        if m:
            header = dict(zip(
                ("totale", "obsolete", "aggiornamenti", "nuove", "policy", "mental model"),
                map(int, m.groups())))
            continue
        if line.startswith("## "):
            section = SECTIONS.get(line.strip())
            continue
        m = ACTION_RE.match(line)
        if m:
            actions.append({
                "flag": m.group(1) == "x", "id": int(m.group(2)),
                "type": m.group(3), "rest": m.group(4), "section": section,
                "done": "→ FATTO" in line, "fields": {},
            })
            continue
        if actions and section is not None:
            f = FIELD_RE.match(line)
            if f:
                actions[-1]["fields"][f.group(1).strip()] = f.group(2)
    return header, actions, allineata


def lint(text, apply_mode=False):
    errors = []
    header, actions, allineata = parse(text)
    if not actions:
        if allineata:
            return errors
        errors.append("nessuna azione trovata e manca la frase 'Memoria allineata'")
        return errors
    if header is None:
        errors.append("intestazione 'Azioni proposte: ...' assente o malformata")
    ids = [a["id"] for a in actions]
    if ids != list(range(1, len(ids) + 1)):
        errors.append(f"ID non sequenziali o duplicati: {ids}")
    if header:
        if header["totale"] != len(actions):
            errors.append(f"totale dichiarato {header['totale']}, azioni trovate {len(actions)}")
        for key in ("obsolete", "aggiornamenti", "nuove", "policy", "mental model"):
            n = sum(1 for a in actions if a["section"] == key)
            if header[key] != n:
                errors.append(f"contatore '{key}' dichiarato {header[key]}, azioni in sezione {n}")
    for a in actions:
        tag = f"A{a['id']}"
        t, f = a["type"], a["fields"]
        if t not in TYPES:
            errors.append(f"{tag}: tipo sconosciuto '{t}'")
            continue
        if a["section"] is None:
            errors.append(f"{tag}: fuori da ogni sezione nota")
        if not apply_mode and a["flag"] and t != "mm-refresh":
            errors.append(f"{tag}: pre-flaggata in audit (solo mm-refresh può esserlo)")
        if t == "mm-refresh":
            continue
        if "Cosa fa" not in f:
            errors.append(f"{tag}: manca 'Cosa fa:'")
        if "Fonte" not in f and "Motivo" not in f:
            errors.append(f"{tag}: manca 'Fonte:' o 'Motivo:'")
        if t in NEEDS_VERIFICA and "Verifica" not in f:
            errors.append(f"{tag}: manca 'Verifica:'")
        if t in NEEDS_PROPOSTA and "Proposta" not in f:
            errors.append(f"{tag}: manca 'Proposta:'")
        if t.startswith("hs-") and "bank `" not in a["rest"]:
            errors.append(f"{tag}: azione Hindsight senza bank di destinazione")
        if t.startswith("file-") and not re.search(r"`(~/|[A-Za-z]:/|/)", a["rest"]):
            errors.append(f"{tag}: azione file senza path completo")
        if apply_mode and a["flag"] and not a["done"] and t in ALTERS_EXISTING:
            v = f.get("Verifica", "")
            if NOT_FIELD_VERIFIED.match(v):
                errors.append(f"{tag}: {t} flaggata senza verifica sul campo (Verifica: {v[:60]})")
    return errors


def main(argv):
    args = [x for x in argv[1:] if not x.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    apply_mode = "--apply" in argv
    with open(args[0], encoding="utf-8") as fh:
        errors = lint(fh.read(), apply_mode)
    for e in errors:
        print(f"ERROR {e}")
    mode = "apply" if apply_mode else "audit"
    print(f"{'FAIL' if errors else 'PASS'} ({len(errors)} errori, modo {mode})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
