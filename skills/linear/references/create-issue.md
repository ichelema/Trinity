# Creare una Issue

Usa questo workflow quando l'utente vuole creare una nuova issue in Linear.

## Raccolta dei dati

Prima di creare la issue, determina:

- titolo operativo
- descrizione del problema
- criteri di accettazione
- estimate
- progetto
- stato
- priorità
- label
- vincoli tecnici (se presenti)
- test richiesti (se presenti)
- dipendenze da altre issue (se presenti)
- eventuale parent issue

Recupera i valori validi dal workspace con i tool MCP, mai a memoria:

| Campo | Tool |
| --- | --- |
| Progetti | `list_projects` |
| Stati | `list_issue_statuses` |
| Label | `list_issue_labels` |
| Team | `list_teams` |
| Assegnatari | `list_users` |
| Scala estimate | `get_team` |

Stati e label sono configurabili per workspace e per team: gli elenchi di un
progetto non valgono per un altro, e proporre un valore inesistente fa fallire
la creazione o la fa passare con un campo vuoto.

La priorità è un'enum fissa di Linear: `0` nessuna, `1` urgente,
`2` alta, `3` media, `4` bassa.

Se mancano informazioni, chiedi solo i campi mancanti. Se l'utente ha già
fornito un valore valido, non richiederlo di nuovo.

## Titolo operativo

Il titolo descrive l'azione da compiere, non il sintomo. Chi lo legge nella
board deve capire cosa fare senza aprire la issue.

**Esempio:**
- Male: "Login bug"
- Bene: "Fix redirect after magic link login"

## Corpo della issue

La descrizione segue un template strutturato. Problem e Acceptance criteria
sono obbligatori; le altre sezioni si includono solo quando hanno contenuto
utile — una sezione vuota o riempita per obbligo è rumore.

Template:

    ## Problem

    <what is broken or missing, with enough context that the reader
    understands the why without having to ask>

    ## Acceptance criteria

    - [ ] <testable condition — the reader should be able to answer yes/no>
    - [ ] <testable condition>

    ## Technical constraints

    <architectural limitations, system dependencies, compatibility requirements>

    ## Required tests

    - [ ] <specific test to write or verify>

**Esempio compilato:**

    ## Problem

    After logging in via magic link the user is redirected to `/` instead of
    the page they were on before. This breaks the flow for users who click a
    shared link while logged out.

    ## Acceptance criteria

    - [ ] After magic-link login the user lands on the original URL
    - [ ] If no return URL is present, the user lands on the dashboard
    - [ ] The return URL is validated to prevent open-redirect attacks

    ## Technical constraints

    The auth callback runs in a serverless function with a 10 s timeout;
    adding a DB lookup for the return URL may require caching.

    ## Required tests

    - [ ] Integration test: magic-link login with a return URL
    - [ ] Unit test: return-URL validation rejects external domains

## Estimate

L'estimate rappresenta lo sforzo stimato. La scala è configurata per team
in Linear (lineare, fibonacci, t-shirt, ecc.) — non è fissa come la priorità.

Recupera la configurazione del team con `get_team` per conoscere la scala
attiva e i valori ammessi. Se il team non ha l'estimation attiva, salta il
campo.

Passa il valore numerico a `save_issue` nel campo `estimate`.

## Dipendenze

Se la issue dipende da altre issue Linear, usa il campo `blockedBy` di
`save_issue` passando gli identificativi delle issue bloccanti
(es. `["ICH-42", "ICH-55"]`).

Non inventare identificativi: verifica che le issue referenziate esistano
con `get_issue` o `list_issues` prima di aggiungerle come dipendenza.

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

    Estimate:
    - <valori dalla scala del team>

Questo è un formato di presentazione, non un elenco di valori: i nomi vanno
sempre dalla risposta dei tool.

## Lingua

- La descrizione della issue deve essere sempre scritta in inglese.
- Eventuali commenti aggiunti alla issue devono essere sempre scritti in inglese.

Se l'utente fornisce una descrizione in italiano, traducila in inglese prima di
salvarla in Linear.

## Conferma

Prima di creare la issue mostra:

- Title
- Estimate
- Project
- Status
- Priority
- Labels
- Parent
- Blocked by
- Description (full body)

Mostra la descrizione completa in inglese, così l'utente approva il testo reale
e non una sua anteprima in un'altra lingua.

Chiedi conferma prima della creazione.

Solo dopo la conferma crea la issue con `save_issue` (senza `id`: con un `id`
aggiorneresti una issue esistente invece di crearne una nuova).

Dopo la creazione mostra in forma tabellare:

- Issue ID
- Title
- Estimate
- Project
- Status
- Priority
- Labels
- Blocked by
- URL
