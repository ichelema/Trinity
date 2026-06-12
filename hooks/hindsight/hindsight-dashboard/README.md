# Hindsight Log Dashboard

Dashboard locale in Ruby/Roda per analizzare `hindsight-debug.log` in formato JSONL.

## Funzioni

- apertura del file log da path locale
- lettura iniziale delle ultime N righe
- tail realtime via Server-Sent Events
- colori per livello/evento:
  - rosso: `*_error`, `parse_error`, status HTTP >= 400
  - giallo: `*_skip`
  - verde: `retain_result` OK
  - cyan: `recall`
  - blu: `retain`
- filtri per eventi e testo
- popup di dettaglio su click riga
- visualizzazione dedicata di `memories[]` con `type`, `text`, `entities`
- JSON completo navigabile con sezioni expand/collapse

## Installazione

```bash
bundle install
```

## Avvio

### Default

```bash
bundle exec puma -p 9292
```

Apri:

```text
http://localhost:9292
```

### Con path iniziale del log

```bash
LOG_FILE="D:/AI/Claude/Trinity/logs/hindsight-debug.log" bundle exec puma -p 9292
```

## Uso

- `Log file`: inserisci il path del JSONL e premi **Apri**.
- `Eventi`: filtro comma-separated, esempio `recall,recall_error,recall_skip`.
- `Grep`: filtro testuale su event, level, message e raw JSON.
- Click su una riga: apre il dettaglio con `memories[]` e JSON completo.

## Note

Questa dashboard è pensata per uso locale. Non esporla su rete pubblica: permette di aprire path locali dal processo Ruby.

## Static assets note

CSS and JavaScript are served from `/assets/app.css` and `/assets/app.js` through Rack::Static.

## Shutdown / Ctrl+C

`Ctrl+C` e `TERM` sono gestiti direttamente dall'app.
Questo evita che connessioni SSE aperte tengano vivo Puma durante lo shutdown.
