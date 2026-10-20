# Consultare la memoria su richiesta

Indice: Quando usarla · Prima di cercare · 1. Ricerche larghe · 2. Ricerche mirate · 3. Controlli sui risultati ·
4. Sintesi facoltativa · Risposta all'utente

Procedura per ricostruire da Hindsight cosa è stato fatto, deciso o configurato su un argomento.

## Quando usarla

Usala solo quando l'utente chiede in modo esplicito di consultare la memoria, per esempio "cerca in memoria…", "cosa abbiamo
configurato per…", "ti ricordi come abbiamo…", "cosa sai di…". Per un recall veloce durante il lavoro basta una sola query
breve e mirata: questa procedura non serve.

## Prima di cercare

Fai queste domande solo se la richiesta non le chiarisce e se la risposta cambia le query:

1. A cosa servono le informazioni: rifare una configurazione, risolvere un guasto o un ripasso.
2. Qual è il perimetro: macchina, progetto, app o periodo.
3. Puoi controllare i fatti sul sistema reale (repository, file, server), o l'utente vuole solo cosa dice la memoria?

Se l'utente non risponde, esegui tutti i passi e segna come "da controllare" ogni fatto che non hai controllato.

## 1. Ricerche larghe

Lancia in parallelo 2–3 `recall` sull'argomento generale:

| Query | Scopo |
| --- | --- |
| `<argomento> configurazione` | il quadro generale |
| `<argomento> modifiche recenti` | cosa è cambiato e quando |
| `<argomento> problemi e soluzioni` | guasti noti e rimedi |

Parametri: `budget: "mid"`, `prefer_observations: true`, `tags: ["claude-code"]`. Le observation sono sintesi già
consolidate: danno il quadro con meno risultati.

Per un periodo preciso passa `temporal_window: {"start": "<ISO>", "end": "<ISO>"}`. Il parametro mette prima le memorie del
periodo, ma non esclude le altre.

### Lettura completa di un periodo

Il tool MCP `list_memories` non filtra per data. Per leggere tutte le memorie di un periodo usa l'API HTTP attraverso il
tunnel, solo con richieste `GET`:

```bash
curl -s "http://127.0.0.1:8888/v1/default/banks/trinity-project/memories/list?start_date=<ISO>&end_date=<ISO>&time_field=mentioned_at&limit=100&offset=0"
```

- L'intervallo è `[start_date, end_date)`. `time_field` sceglie la data: `created_at` (predefinita), `updated_at`,
  `mentioned_at`, `occurred_start`, `occurred_end`. Le memorie senza quella data restano fuori.
- La risposta ha `total`: se supera `limit`, leggi le pagine successive con `offset`.
- Mai `POST`, `PATCH` o `DELETE` via API: aggirano l'allowlist dei tool MCP.

## 2. Ricerche mirate

Dai risultati del passo 1 raccogli i nomi propri: programmi, file, host, comandi, hash di commit. Lancia una `recall` per ogni
nome, con `prefer_observations: false`, per avere i fatti con i dettagli (path, valori, versioni). Aggiungi `repo:<nome>` ai
tag solo se l'argomento riguarda un repository preciso.

Fermati quando le nuove query restituiscono solo memorie già viste.

## 3. Controlli sui risultati

- **Date.** Leggi `occurred_start` e `mentioned_at`. Se due memorie si contraddicono, vale la più recente: segnala la
  contraddizione all'utente.
- **Fonti.** Annota hash di commit, path e nomi di file: sono le prove da controllare.
- **Fatti che cambiano.** Porte, versioni, regole di firewall e contenuto dei file vanno controllati sul sistema reale prima di
  usarli. La memoria non è la source of truth.
- Se l'utente lo permette, controlla i fatti chiave sul sistema con comandi in sola lettura (`git log`, lettura dei file).

## 4. Sintesi facoltativa

Usa `reflect` solo dopo i passi 1–3, e solo se serve una sintesi o un giudizio su molte memorie: costa più di `recall`.
Parametri: `budget: "mid"`, `max_tokens: 2000`. Confronta la risposta di `reflect` con i fatti raccolti: deve dare ordine, non
aggiungere fatti nuovi.

## Risposta all'utente

- Metti la risposta diretta nella prima frase.
- Raggruppa per argomento (per esempio accesso, notifiche, guasti noti), con path, comandi e commit esatti.
- Per ogni fatto indica se l'hai controllato sul sistema o se viene solo dalla memoria.
- Elenca cosa non hai trovato in memoria.
