# Creare una Issue

Usa questo workflow quando l'utente vuole creare una nuova issue in Linear.

## Raccolta dei dati

Prima di creare la issue, determina:

- titolo
- descrizione
- progetto
- stato
- priorità
- label
- eventuale parent issue

Recupera i valori validi dal workspace con i tool MCP, mai a memoria:

| Campo | Tool |
| --- | --- |
| Progetti | `list_projects` |
| Stati | `list_issue_statuses` |
| Label | `list_issue_labels` |
| Team | `list_teams` |
| Assegnatari | `list_users` |

Stati e label sono configurabili per workspace e per team: gli elenchi di un
progetto non valgono per un altro, e proporre un valore inesistente fa fallire
la creazione o la fa passare con un campo vuoto.

La priorità è invece un'enum fissa di Linear: `0` nessuna, `1` urgente,
`2` alta, `3` media, `4` bassa.

Se mancano informazioni, chiedi solo i campi mancanti. Se l'utente ha già
fornito un valore valido, non richiederlo di nuovo.

## Presentare le opzioni

Quando serve una scelta, mostra i valori **letti da Linear in quel momento**,
raggruppati per campo:

    Project:
    - <valori da list_projects>
    - Nessuno

    Status:
    - <valori da list_issue_statuses>

    Labels:
    - <valori da list_issue_labels>

Questo è un formato di presentazione, non un elenco di valori: i nomi vanno
sempre dalla risposta dei tool.

## Lingua

- La descrizione della issue deve essere sempre scritta in inglese.
- Eventuali commenti aggiunti alla issue devono essere sempre scritti in inglese.

Se l'utente fornisce una descrizione in italiano, traducila in inglese prima di
salvarla in Linear.

## Conferma

Prima di creare la issue mostra:

- Titolo
- Project
- Status
- Priority
- Labels
- Parent
- Description

Mostra la descrizione già nella versione inglese che verrà salvata, così
l'utente approva il testo reale e non una sua anteprima in un'altra lingua.

Chiedi conferma prima della creazione.

Solo dopo la conferma crea la issue con `save_issue` (senza `id`: con un `id`
aggiorneresti una issue esistente invece di crearne una nuova).

Dopo la creazione mostra:

- ID issue
- titolo
- project
- status
- priority
- labels
- URL
