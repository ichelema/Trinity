# Ponytail Help

Mostra questa reference card quando viene invocata. One-shot, NON cambiare modalità,
scrivere file flag o persistere qualcosa.

## Livelli

| Livello | Trigger | Cosa cambia |
|-------|---------|-------------|
| **Lite** | `/trinity:ponytail:ponytail lite` | Costruisci ciò che è chiesto, nomina in una riga l'alternativa più pigra. |
| **Full** | `/trinity:ponytail:ponytail` | La scala applicata: YAGNI → stdlib → native → one line → minimum. Default. |

Il livello resta fino a cambiato o a fine sessione.

## Skill

| Skill | Trigger | Cosa fa |
|-------|---------|--------------|
| **ponytail** | `/trinity:ponytail:ponytail` | La modalità pigra stessa. La soluzione più semplice che funziona. |
| **ponytail-review** | `/trinity:ponytail:ponytail-review` | Revisione over-engineering: `L42: yagni: factory, one product. Inline.` |
| **ponytail-audit** | `/trinity:ponytail:ponytail-audit` | Audit over-engineering dell'intero repo: lista classificata di cosa cancellare. |
| **ponytail-debt** | `/trinity:ponytail:ponytail-debt` | Raccogli i commenti di scorciatoia `ponytail:` in un ledger tracciato. |
| **ponytail-gain** | `/trinity:ponytail:ponytail-gain` | Scoreboard dell'impatto misurato: meno codice, meno costo, più velocità. |
| **ponytail-help** | `/trinity:ponytail:ponytail-help` | Questa card. |

Codex usa `@ponytail`, `@ponytail-review` e `@ponytail-help`; Claude Code
e OpenCode usano le forme slash-command qui sopra (OpenCode offre tutte e sei come
slash command).

## Disattiva

Dì "stop ponytail" o "normal mode". Riprendi quando vuoi con `/trinity:ponytail:ponytail`.
Funziona anche `/trinity:ponytail:ponytail off`.

## Configura la modalità di default

Modalità di default = `full`, auto-attiva ogni sessione. Cambiala:

**Variabile d'ambiente** (priorità massima):
```bash
export PONYTAIL_DEFAULT_MODE=lite
```

**File di config** (`~/.config/ponytail/config.json`):
```json
{ "defaultMode": "lite" }
```

Imposta `"off"` per disabilitare l'auto-attivazione all'avvio della sessione, attivala
manualmente con `/trinity:ponytail:ponytail` quando vuoi.

Risoluzione: env var > file di config > `full`.

## Update

Abilita l'auto-update una volta: apri `/plugin`, vai su Marketplaces, scegli ponytail, Abilita auto-update. Claude Code scarica poi le nuove versioni all'avvio (esegui `/reload-plugins` quando lo richiede). Refresh manuale: `/plugin marketplace update ponytail` poi `/reload-plugins`.

Se `/plugin` non è riconosciuto, la tua Claude Code è obsoleta. Aggiornala (`npm install -g @anthropic-ai/claude-code@latest`, o `brew upgrade claude-code`) e riavvia. Gli altri host usano il loro flusso di update.

## Altro

Documentazione completa + esempi: https://github.com/DietrichGebert/ponytail
