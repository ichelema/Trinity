# Ponytail Help

Mostra questa reference card quando viene invocata. One-shot: non cambiare modalità, non scrivere
file flag e non persistere niente.

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

## Disattiva

Dì "stop ponytail" o "normal mode". Riprendi quando vuoi con `/trinity:ponytail:ponytail`.
Funziona anche `/trinity:ponytail:ponytail off`.

## Configura la modalità di default

Modalità di default = `full`, auto-attiva ogni sessione. Cambiala:

**Variabile d'ambiente** (priorità massima):
```bash
export PONYTAIL_DEFAULT_MODE=lite
```

**File di config** (`$XDG_CONFIG_HOME/ponytail/config.json` se la variabile esiste, altrimenti
`~/.config/ponytail/config.json`; su Windows `~` è `HOME` o `USERPROFILE`):
```json
{ "defaultMode": "lite" }
```

Imposta `"off"` per disabilitare l'auto-attivazione all'avvio della sessione, attivala
manualmente con `/trinity:ponytail:ponytail` quando vuoi.

Risoluzione: env var > file di config > `full`.

## Altro

Documentazione completa + esempi: https://github.com/DietrichGebert/ponytail
