---
name: double-commander-docs
description: Cerca nella documentazione locale di Double Commander. Usa questa skill quando l’utente chiede informazioni su Double Commander, comandi interni, opzioni, file doublecmd.xml, scorciatoie, toolbar, parametri, variabili, Lua scripting, plugin, ricerca file, sincronizzazione directory, gestione archivi o comportamento dell’interfaccia.
allowed-tools: Read Grep Bash
---

# SKILL

Questa skill serve a rispondere a domande su Double Commander usando prima la documentazione locale fornita nella cartella `references/`.

Non inventare comportamenti non presenti nella documentazione. Se una voce non è documentata, dichiaralo esplicitamente e cerca corrispondenze vicine, o affidati a ricerche web.

## Struttura prevista della skill

Questa skill deve valere **solo** per il progetto locale:

```text
C:\Desktop\Claude\Main
```

La cartella della skill deve quindi essere:

```text
C:\Desktop\Claude\Main\.claude\skills\double-commander-docs\
├── SKILL.md
└── references\
    ├── Archive Handling.md
    ├── Basic Help.md
    ├── cm_Options Reference.md
    ├── Command Line.md
    ├── Configuration.md
    ├── Copying and Moving Files.md
    ├── Directory Hotlist.md
    ├── doublecmd.xml Settings.md
    ├── FAQ.md
    ├── File Viewer.md
    ├── Find Files.md
    ├── images\
    ├── Indice.md
    ├── Internal Commands.md
    ├── Keyboard Layout.md
    ├── Lua Scripting.md
    ├── Multi-Rename Tool.md
    ├── Pre-installed Plugins.md
    ├── Regular Expressions.md
    ├── Synchronize Directories.md
    ├── Toolbar.md
    ├── Variables in Parameters.md
    └── What is Double Commander.md
```

## Mappa rapida dei file

Usa questa mappa per scegliere dove cercare prima.

| Tipo di domanda                                              | File prioritari                                                            |
| ------------------------------------------------------------ | -------------------------------------------------------------------------- |
| Comandi interni, `cm_*`, azioni richiamabili da toolbar/menu | `Internal Commands.md`, `cm_Options Reference.md`, `Toolbar.md`            |
| Opzioni e preferenze dell’interfaccia                        | `Configuration.md`, `cm_Options Reference.md`, `doublecmd.xml Settings.md` |
| Parametri da linea di comando                                | `Command Line.md`, `Variables in Parameters.md`                            |
| Copia, spostamento, rinomina, operazioni file                | `Copying and Moving Files.md`, `Multi-Rename Tool.md`, `Basic Help.md`     |
| Hotlist directory, preferiti, percorsi rapidi                | `Directory Hotlist.md`, `Variables in Parameters.md`                       |
| Viewer integrato                                             | `File Viewer.md`, `Pre-installed Plugins.md`                               |
| Ricerca file                                                 | `Find Files.md`, `Regular Expressions.md`                                  |
| Regex                                                        | `Regular Expressions.md`, `Find Files.md`, `Multi-Rename Tool.md`          |
| Sincronizzazione cartelle                                    | `Synchronize Directories.md`, `Copying and Moving Files.md`                |
| Archivi compressi                                            | `Archive Handling.md`, `Pre-installed Plugins.md`                          |
| Plugin                                                       | `Pre-installed Plugins.md`, `File Viewer.md`, `Archive Handling.md`        |
| Lua scripting                                                | `Lua Scripting.md`, `Variables in Parameters.md`, `Internal Commands.md`   |
| Scorciatoie e layout tastiera                                | `Keyboard Layout.md`, `Internal Commands.md`                               |
| File di configurazione XML                                   | `doublecmd.xml Settings.md`, `Configuration.md`                            |
| Domande generali o introduttive                              | `What is Double Commander.md`, `Basic Help.md`, `FAQ.md`, `Indice.md`      |
| Immagini citate dalla documentazione                         | `images/`                                                                  |

## Procedura di lookup

Quando l’utente chiede qualcosa su Double Commander:

1. Identifica il tipo di richiesta:
   
   - comando interno
   - opzione
   - parametro
   - scorciatoia
   - file di configurazione
   - operazione file
   - plugin
   - scripting
   - comportamento dell’interfaccia

2. Normalizza i termini da cercare:
   
   - conserva il nome esatto se contiene `_`, `-`, `.`, `cm_`, `%`, `$`, XML tag o nomi di file
   - prova anche varianti case-insensitive
   - per i comandi interni, cerca sia il nome completo sia la parte dopo `cm_`

3. Cerca prima nei file prioritari indicati nella mappa.

4. Se non trovi una corrispondenza precisa, cerca in tutti i file Markdown sotto `references/`.

5. Se ci sono immagini referenziate nel Markdown, controlla il path sotto `references/images/` solo se l’immagine è necessaria per capire la risposta.

6. Rispondi solo in base alla documentazione locale, salvo richiesta esplicita di usare fonti esterne.

7. Se la documentazione non contiene la voce richiesta:
   
   - dichiara che non hai trovato una corrispondenza esatta
   - mostra le corrispondenze più vicine
   - non dedurre il comportamento se non è documentato

## Comandi di ricerca consigliati

Per una ricerca esatta:

```bash
rg -n --fixed-strings "TERMINE_ESATTO" references/
```

Per una ricerca case-insensitive:

```bash
rg -n -i "TERMINE" references/
```

Per avere contesto intorno alla corrispondenza:

```bash
rg -n -i --context 3 "TERMINE" references/
```

Per cercare un comando interno Double Commander:

```bash
rg -n -i --context 4 "cm_NomeComando|NomeComando" \
  "references/Internal Commands.md" \
  "references/cm_Options Reference.md" \
  "references/Toolbar.md"
```

Per cercare in tutto il manuale escludendo immagini:

```bash
rg -n -i --glob '*.md' "TERMINE" references/
```

## Strategia per comandi `cm_*`

Se l’utente chiede, per esempio:

```text
A cosa serve cm_CopyFullNamesToClip?
```

usa questa sequenza:

```bash
rg -n -i --context 4 "cm_CopyFullNamesToClip" "references/Internal Commands.md" "references/cm_Options Reference.md" "references/Toolbar.md"
```

Se non trovi nulla:

```bash
rg -n -i --context 4 "CopyFullNamesToClip|Copy Full Names|FullNames|Clip" references/ --glob '*.md'
```

Poi rispondi con:

```text
`cm_CopyFullNamesToClip` serve a ...

Fonte locale:
- references/Internal Commands.md:<riga>

Dettagli:
...

Comandi correlati:
...
```

## Strategia per opzioni e configurazione

Per opzioni grafiche, preferenze e impostazioni:

1. Cerca in `Configuration.md`.
2. Cerca in `cm_Options Reference.md`.
3. Cerca in `doublecmd.xml Settings.md` se la domanda riguarda valori persistiti, XML, nomi di chiavi o configurazione avanzata.

Comandi:

```bash
rg -n -i --context 4 "TERMINE" \
  "references/Configuration.md" \
  "references/cm_Options Reference.md" \
  "references/doublecmd.xml Settings.md"
```

## Strategia per toolbar e parametri

Per domande su pulsanti, toolbar, variabili o parametri:

```bash
rg -n -i --context 4 "TERMINE" \
  "references/Toolbar.md" \
  "references/Variables in Parameters.md" \
  "references/Internal Commands.md" \
  "references/Command Line.md"
```

## Strategia per Lua scripting

Per domande su automazione, script o estensioni Lua:

```bash
rg -n -i --context 4 "TERMINE" \
  "references/Lua Scripting.md" \
  "references/Variables in Parameters.md" \
  "references/Internal Commands.md"
```

Rispondi distinguendo chiaramente:

- cosa è supportato direttamente dal comando interno
- cosa richiede Lua
- cosa richiede parametri o variabili
- cosa non è documentato

## Strategia per immagini

La cartella `references/images/` contiene immagini usate dai file Markdown.

Usa le immagini solo quando:

- il testo rimanda esplicitamente a uno screenshot
- la domanda riguarda un elemento grafico dell’interfaccia
- il contenuto testuale non basta a chiarire la procedura

Non caricare immagini inutilmente.

## Formato risposta consigliato

Per una domanda su un comando:

```text
`<comando>` in Double Commander serve a <spiegazione breve>.

Dettagli:
- ...
- ...

Dove si trova nella documentazione locale:
- `references/<file>.md:<riga>`

Note:
- ...
```

Per una domanda su una procedura:

```text
Per fare <azione> in Double Commander:

1. ...
2. ...
3. ...

Documentazione locale consultata:
- `references/<file>.md:<riga>`
```

Per una voce non trovata:

```text
Non ho trovato una corrispondenza esatta per `<termine>` nella documentazione locale.

Corrispondenze vicine:
- `<voce simile>` — `references/<file>.md:<riga>`
- `<voce simile>` — `references/<file>.md:<riga>`

Non deduco il comportamento perché non è documentato nei file disponibili.
```

## Regole di accuratezza

- Dai priorità alle corrispondenze esatte rispetto a quelle semantiche.
- Non usare conoscenza generica su file manager simili per spiegare Double Commander.
- Non assumere che un comando funzioni come in Total Commander se il manuale locale non lo dice.
- Se più file danno informazioni diverse, segnala la differenza e cita entrambi.
- Se una sezione sembra riferirsi a una versione specifica, menzionalo.
- Se il manuale usa nomi inglesi, mantieni il nome tecnico originale e spiega in italiano.
- Per comandi, opzioni, variabili, tag XML e nomi file usa sempre backtick.

## Esempi di richieste che devono attivare questa skill

- “A cosa serve `cm_CopyFullNamesToClip` Double Commander ?”
- “Come funziona la Directory Hotlist Double Commander ?”
- “Dove si configura il viewer interno Double Commander ?”
- “Come uso le regex nel Find Files Double Commander ?”
- “Che variabili posso usare nei parametri della toolbar in Double Commander ?”
- “Come modifico `doublecmd.xml` per Double Commander ?”
- “Come funziona il Multi-Rename Tool per Double Commander ?”
- “Come faccio una sincronizzazione directory con Double Commander ?”
- “Double Commander supporta Lua?”
- “Quali plugin sono preinstallati Double Commander ?”

## Esempio operativo completo

Domanda utente:

```text
A cosa serve il comando cm_FocusCmdLine in Double Commander?
```

Azioni:

```bash
rg -n -i --context 4 "cm_FocusCmdLine" "references/Internal Commands.md" "references/cm_Options Reference.md" "references/Toolbar.md"
```

Se non basta:

```bash
rg -n -i --context 4 "FocusCmdLine|Focus Cmd Line|command line" references/ --glob '*.md'
```

Risposta:

```text
`cm_FocusCmdLine` serve a ...

Dettagli:
- ...

Fonte locale:
- `references/Internal Commands.md:<riga>`

Correlati:
- `Command Line.md`, se la documentazione lo collega alla riga di comando.
```
