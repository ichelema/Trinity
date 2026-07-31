#!/usr/bin/env python3
"""Sincronizza ~/.claude/settings.json dai file versionati in config/claude/.

Merge in tre strati, l'ultimo vince:
  1. file esistente sulla macchina (le chiavi solo locali sopravvivono)
  2. settings.shared.json (preferenze portabili, uguali su tutti gli OS)
  3. settings.<os>.json (env/path specifici: windows o linux)
I dict si fondono ricorsivamente; liste e scalari vengono sostituiti (le
permissions vivono per intero nello shared, niente union che resusciterebbe
voci rimosse dal repo). TRINITY_PLUGIN_DIR viene impostata dalla posizione
del repo, mai dagli overlay. Prima di scrivere crea settings.json.bak.

Uso: sync-claude-settings.py <path di settings.json>
(su Windows passare il path in formato Windows: il Python mise è nativo)
"""

import json
import os
import shutil
import sys
from pathlib import Path


# Chiavi possedute PER INTERO dal repo: si sostituiscono, niente merge — il
# deep-merge non rimuove mai chiavi, quindi voci obsolete (es. un marketplace
# dismesso) sopravvivrebbero per sempre nel file locale.
REPLACE_KEYS = frozenset({"enabledPlugins", "extraKnownMarketplaces"})


def deep_merge(base: dict, overlay: dict, replace_keys: frozenset = frozenset()) -> dict:
    for key, value in overlay.items():
        if key not in replace_keys and isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def main() -> int:
    if len(sys.argv) != 2:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2

    settings_path = Path(sys.argv[1])
    # abspath e NON resolve(): sul setup a chiavetta il drive E: e' una
    # junction/subst di D: e resolve() la attraverserebbe, scrivendo in
    # TRINITY_PLUGIN_DIR un path D:/ che il resto del sistema non usa.
    root = Path(os.path.abspath(__file__)).parents[2]
    cfg_dir = root / "config" / "claude"
    os_name = "windows" if os.name == "nt" else "linux"

    shared = json.loads((cfg_dir / "settings.shared.json").read_text(encoding="utf-8"))
    overlay = json.loads((cfg_dir / f"settings.{os_name}.json").read_text(encoding="utf-8"))

    old_text = None
    data = {}
    if settings_path.exists():
        old_text = settings_path.read_text(encoding="utf-8")
        data = json.loads(old_text)

    deep_merge(data, shared, REPLACE_KEYS)
    deep_merge(data, overlay, REPLACE_KEYS)
    data.setdefault("env", {})["TRINITY_PLUGIN_DIR"] = root.as_posix()

    new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if new_text == old_text:
        print(f"  [OK ] settings.json gia' allineato ({os_name}): {settings_path}")
        return 0

    if old_text is not None:
        backup = settings_path.with_name(settings_path.name + ".bak")
        shutil.copy2(settings_path, backup)
        print(f"  [OK ] backup: {backup}")

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    # newline esplicito: senza, su Windows write_text tradurrebbe in CRLF e il
    # primo sync riscriverebbe ogni riga di un file nato LF.
    settings_path.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"  [OK ] settings.json aggiornato ({os_name}): {settings_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
