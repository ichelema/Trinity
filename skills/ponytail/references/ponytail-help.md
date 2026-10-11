# Ponytail Help

Mostra questa reference card quando viene invocata. One-shot, NON cambiare modalità, scrivere
file flag o persistere qualcosa.

## Livelli

| Livello  | Trigger                           | Cosa cambia                                                                                                                                    |
| -------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Lite** | `/trinity:ponytail:ponytail lite` | Costruisci ciò che è chiesto, nomina in una riga l'opzione più piccola.                                                                        |
| **Full** | `/trinity:ponytail:ponytail`      | La modifica completa più piccola, un controllo dove la logica lo richiede, e una risposta che nomina cosa è stato saltato e ogni rischio. Default. |

Il livello resta fino a cambiato o a fine sessione.

## Skill

| Skill               | Trigger                            | Cosa fa                                                                                                                                  |
| ------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **ponytail**        | `/trinity:ponytail:ponytail`       | La modalità pigra stessa: meno codice nuovo, risposte chiare che nominano il lavoro saltato e i rischi.                                  |
| **ponytail-review** | `/trinity:ponytail:ponytail-review` | Revisione di qualità di un diff: bug, sicurezza, carico, test mancanti, velocità, cosa tagliare. Ogni finding dice cosa va storto e come correggerlo. |
| **ponytail-audit**  | `/trinity:ponytail:ponytail-audit`  | La stessa revisione di qualità per l'intero repo, classificata.                                                                          |
| **ponytail-debt**   | `/trinity:ponytail:ponytail-debt`   | Raccogli i commenti di scorciatoia (`ponytail:` / `shortcut:`) in un ledger tracciato.                                                   |
| **ponytail-gain**   | `/trinity:ponytail:ponytail-gain`   | Scoreboard dell'impatto misurato: meno codice, meno costo, più velocità.                                                                 |
| **ponytail-help**   | `/trinity:ponytail:ponytail-help`   | Questa card.                                                                                                                             |

Codex CLI e l'estensione IDE invocano le skill con `$ponytail:ponytail`,
`$ponytail:ponytail-review` o `$ponytail:ponytail-help`. Claude Code e OpenCode usano le forme
slash-command qui sopra (OpenCode offre tutte e sei come slash command).

## Disattiva

Dì "stop ponytail" o "normal mode". Riprendi quando vuoi con `/trinity:ponytail:ponytail`.
Funziona anche `/trinity:ponytail:ponytail off`.

## Configura la modalità di default

Modalità di default = `full`, auto-attiva ogni sessione. Cambiala:

**Variabile d'ambiente** (priorità massima):
```bash
export PONYTAIL_DEFAULT_MODE=lite
```

**File di config** (`~/.config/ponytail/config.json`, Windows: `%APPDATA%\ponytail\config.json`):
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
