---
name: pragmatic-functional-ruby
description: >
  Scrivi, analizza e rifattorizza codice Ruby in questo progetto usando lo stile
  funzionale pragmatico basato su FunctionalLightService: pipeline dichiarative
  di action (Organizer + steps), contratti expects/promises, errori come valori
  con try! e fail_and_return!, immutabilità selettiva (Hamster, IceNine, freeze)
  e separazione fra logica pura ed effetti collaterali. Usa questa skill quando
  crei o modifichi action, controller, concern o model, quando devi decidere
  come propagare un errore, o quando valuti se introdurre un'astrazione.
---

# Pragmatic Functional Ruby (PrevisioneSteg)

## Obiettivo

Codice Ruby prevedibile ed esplicito nella gestione degli errori, che resti
idiomatico e leggibile.

Lo scopo **non** è imitare Haskell. Lo scopo è usare tecniche funzionali dove
rendono il codice più testabile e componibile, e lasciare imperativo tutto il
resto.

Questo stile va descritto come:

> Ruby funzionale pragmatico basato su pipeline di action, tipi espliciti per
> successo e fallimento, e immutabilità selettiva.

Mai come "programmazione funzionale pura".

---

## Vincoli dello stack (non negoziabili)

Prima di scrivere qualsiasi esempio, verifica che sia compatibile con:

| Vincolo | Valore |
|---|---|
| Ruby | **3.1.0** |
| Gem funzionale | `functional-light-service` **0.3.x** |
| Immutabilità | `hamster` 3.0, `ice_nine` 0.11 |
| Piattaforma | Windows, WIN32OLE per Excel COM |
| Formattazione | `rufo` (double quotes, `parens_in_def :dynamic`, chained calls allineate) |
| Lint | `rubocop` con config `standard` |
| Test | **nessuna suite di test** nel progetto |

### Costrutti vietati perché Ruby 3.2+

- `Data.define(...)` → usa `Struct.new(..., keyword_init: true)` o un `Hash` congelato.
- `Hash#except` su Ruby < 3.0 non è un problema, ma non usare API 3.2+ senza verificarle.

Se proponi un costrutto moderno, prima controlla che esista in 3.1.

---

## API reali di `Result` (leggi prima di scrivere una pipeline)

Questo è il punto in cui è più facile sbagliare: `functional-light-service`
**non** segue la convenzione `dry-monads`.

| Metodo su `Result` | Semantica reale | Alias |
|---|---|---|
| `map` | **monadico** — il blocco DEVE restituire un `Result` | `>>`, `and_then`, `bind` |
| `map_err` | monadico sul ramo di errore — il blocco DEVE restituire un `Result` | `or_else` |
| `pipe` | esegue il blocco per effetto collaterale e restituisce `self` invariato | `<<` |
| `fmap` | funtoriale (da `Monad`), riavvolge il valore | — |
| `match` | pattern matching esaustivo | — |
| `success?` / `failure?` | predicati | — |
| `value` | estrae il valore grezzo | — |

Regole che ne discendono:

1. **Su `Result` usa `map` / `>>`, non `bind`.** Sono lo stesso metodo; `map`
   e `>>` sono la forma usata nel progetto.
2. **Non usare `fmap` su `Result`.** Se il blocco restituisce un `Failure`,
   `fmap` lo incapsula in `Success(Failure(...))` e la pipeline non
   short-circuita. `fmap` è sicuro solo su `Option`.
3. Ogni funzione concatenata deve restituire un `Result`. Mai `nil`, mai un
   valore nudo.

Forma canonica della pipeline, come in [filter_data.rb](app/actions/forecast/filter_data.rb:62):

```ruby
ctx.filtered_data = Success(ctx.consuntivi) \
               >> method(:filter_giorno) \
               >> method(:filter_festivo) \
               >> method(:filter_festivita)
ctx.fail_and_return!(ctx.filtered_data.value) if ctx.filtered_data.failure?
```

```text
Input -> Success -> Success -> Success
             \
              Failure -----------------> Failure
```

Non aggiungere controlli manuali intermedi: il `Result` short-circuita da solo.

---

## Pattern matching

Le enum della gem **non definiscono `deconstruct` / `deconstruct_keys`**: il
pattern matching nativo di Ruby (`case ... in Success(value)`) **non funziona**.

Usa il DSL `match`, che è esaustivo (solleva `NoMatchError` se manca un ramo):

```ruby
result.match do
  Success() { |value| value }
  Failure() { |error| log.error error.message }
end
```

Con guardia:

```ruby
result.match do
  Success(where { s.is_a?(Array) }) { |s| s.first }
  Success()                         { |s| s }
  Failure()                         { |f| ctx.fail_and_return!(f) }
end
```

Le variabili nella guardia prendono il nome degli argomenti del blocco.

---

## Errori previsti come valori

### Regola

- Errore **previsto** di dominio → `Failure` / `ctx.fail_and_return!`.
- Errore **eccezionale** (bug, invariante violata) → eccezione, gestita dal
  `rescue` del controller che logga in `fatal` ed esce con codice 1.

Non usare eccezioni come controllo di flusso, e non usare booleani quando il
chiamante deve conoscere il motivo del fallimento.

### `try!` invece di `rescue`

Nelle action **non scrivere mai un `rescue` nudo**. `try!` cattura
`StandardError` e lo trasforma in `Failure(exception)`:

```ruby
try! do
  ctx.previsione[ps] << media_ponderata(ps, fcs_hour) * 1000
end.map_err do |err|
  ctx.fail_and_return!(
    {message: "Errore non sono riuscito a fare la media ponderata per la ps:#{ps.capitalize} ora:#{hour}",
     detail: err.message,
     location: "#{__FILE__}:#{__LINE__}"}
  )
end
```

### Forma dell'errore

L'hash di errore ha **sempre** tre chiavi, perché
[BaseController#check_result](lib/ikigai/base_controller.rb:61) le legge:

| Chiave | Contenuto |
|---|---|
| `:message` | messaggio leggibile per l'utente finale, in italiano, che dice cosa controllare |
| `:detail` | `err.message` dell'eccezione originale — mostrato solo con `--verbose` |
| `:location` | `"#{__FILE__}:#{__LINE__}"` |

Non perdere la causa originale. Non mettere in `:message` dettagli tecnici che
l'utente non può usare.

Per errori di configurazione dell'Excel, il messaggio è una heredoc che indica
file, foglio e valore atteso, come in
[get_excel_params.rb](app/actions/forecast/get_excel_params.rb:74).

### Nota sul meccanismo

`ctx.fail_and_return!` internamente interrompe il flusso con un throw. È il
meccanismo del framework, non una violazione della regola "niente eccezioni per
il flusso": dal punto di vista dell'action è una `return` che porta con sé
l'errore.

---

## Anatomia di una action

Template completo. Rispettalo: l'ordine dei blocchi è parte dello stile.

```ruby
#!/usr/bin/env ruby
# warn_indent: true
# frozen_string_literal: true

module ForecastActions
  ##
  # Descrizione in italiano di cosa fa l'action
  #
  # <div class="lsp">
  #   <h2>Expects:</h2>
  #   - some_input (Hash) Descrizione<br>
  #   <h2>Promises:</h2>
  #   - some_output (Array) Descrizione<br>
  # </div>
  #
  class MyAction
    # @!parse
    #   extend FunctionalLightService::Action
    extend FunctionalLightService::Action

    expects :some_input
    promises :some_output

    # @!method MyAction(ctx)
    #
    #   @!scope class
    #
    #   @param ctx [FunctionalLightService::Context]
    #
    #   @expects some_input [Hash] Descrizione
    #
    #   @promises some_output [Array] Descrizione
    #
    #   @example some_output
    #       # dump reale del dato, non inventato
    #
    #   @return [FunctionalLightService::Context, FunctionalLightService::Context.fail_and_return!]
    executed do |ctx|
      try! do
        ctx.some_output = compute(ctx.some_input)
      end.map_err do |err|
        ctx.fail_and_return!(
          {message: "Messaggio in italiano che dice cosa controllare",
           detail: err.message,
           location: "#{__FILE__}:#{__LINE__}"}
        )
      end
    end

    # Descrizione dell'helper
    #
    # @param input [Hash]
    #
    # @return [Array]
    def self.compute(input)
      # ...
    end

    private_class_method :compute
  end
end
```

Poi aggiungi la classe all'array `.steps` del controller e documentala nel
commento YARD sopra `.steps`.

Regole:

- header a tre righe (`#!/usr/bin/env ruby`, `warn_indent`, `frozen_string_literal`);
- gli helper sono **metodi di classe** (`def self.x`), dichiarati
  `private_class_method` in fondo con la lista allineata;
- `expects` / `promises` sono il contratto: se un dato serve allo step
  successivo passa dal `ctx`, altrimenti resta una variabile locale;
- documentazione YARD con `@example` contenente **dump reali** dei dati, perché
  sono la vera documentazione del formato.

---

## La pipeline sta nel controller

Il Railway di questo progetto non è una catena di `>>`: è l'array `.steps`.

```ruby
def self.steps
  # rubocop:disable Layout/ExtraSpacing
  [
    SetExcelDay,    # E:[]                P:[data]
    GetExcelParams, # E:[]                P:[params]
    ReadDb,         # E:[excel]           P:[consuntivi]
    FilterData      # E:[consuntivi, params] P:[filtered_data]
  ]
  # rubocop:enable Layout/ExtraSpacing
end

private_class_method :steps
```

Ogni riga porta il commento `E:[expects] P:[promises]` allineato. Se aggiungi
uno step, aggiorna anche il commento e il blocco YARD sopra `.steps`.

L'entry point è sempre:

```ruby
def self.call(env:)
  result = with(env: env).reduce(steps)
  check_result(result, detail: env.dig(:global_options, :verbose) > "0")
  nil
rescue => e
  # log fatal + exit 1
end
```

Exit code: **2** = fallimento previsto di un'action, **1** = eccezione non
gestita.

---

## Immutabilità selettiva

Congela quello che protegge il modello, non tutto.

| Cosa | Come |
|---|---|
| Costanti di dominio | `PS = %w[...].freeze` |
| Stringhe | `# frozen_string_literal: true` in testa a ogni file |
| Parametri di input letti una volta | `Hamster::Hash[...]` |
| Dataset letto dal DB e mai mutato | `IceNine.deep_freeze!(...)` |

Esempio reale, [read_db.rb](app/actions/forecast/read_db.rb:63):

```ruby
ctx.consuntivi = IceNine.deep_freeze!(value[1..].map(&value[0].method(:zip)).map(&:to_h))
```

Non congelare: oggetti `WIN32OLE`, connessioni, workbook, oggetti di librerie
esterne, o accumulatori che vengono riempiti in un ciclo.

`freeze` è superficiale: per una struttura annidata serve `IceNine.deep_freeze!`,
e ha un costo. Applicalo dove il dato è grande e condiviso fra step, non ovunque.

---

## Context: mutabile per scelta

Il `ctx` di FunctionalLightService è mutabile e va bene così.

```ruby
ctx.previsione ||= PS.to_h { |s| [s, []] }
```

Regole:

- il context appartiene a **una sola esecuzione** del controller;
- non condividerlo fra thread;
- un'action non conserva il context in una variabile di classe;
- metti nel context solo ciò che serve a uno step successivo — le
  trasformazioni locali restano variabili locali.

Non copiare il context a ogni step per simulare immutabilità. Mai
`Marshal.load(Marshal.dump(context))`.

---

## Stato globale: la deviazione documentata

I concern in [forecast_concern.rb](app/controllers/concerns/forecast_concern.rb)
usano variabili di classe (`@@excel`, `@@workbook`, `@@params`) per la
connessione COM a Excel.

**Questa è una scelta deliberata, non un difetto da correggere.** Una
connessione WIN32OLE è costosa e non ricreabile per ogni step; la cache
attraversa tutte le action del processo.

Non proporre di rifattorizzarla in dependency injection a meno che l'utente non
lo chieda esplicitamente. Se ci lavori sopra, rispetta le regole COM del
progetto:

- `WIN32OLE.const_load(@@excel, ExcelConst)` prima di usare costanti VB;
- `.activate` sul workbook prima di operarci;
- una cella vuota restituisce `""`, non `nil` — controlla sempre;
- i named range restituiscono una formula: passala a `Evaluate`.

---

## Functional core, imperative shell

Tieni pura la logica di calcolo:

```ruby
def self.media_ponderata(ps, fcs_hour)
  fcs_hour.then do |forecast|
    forecast.map { |h| [h["Flow_#{ps.capitalize}"], h["Peso"]] }
  end
    .then do |tmp|
    tmp.reduce(0) { |sum, num| sum + num[0] * num[1] } / tmp.reduce(0) { |sum, num| sum + num[1] }
  end
end
```

Il chaining con `.then` è lo stile del progetto per le trasformazioni pure in
più passaggi: ogni blocco ha un commento che mostra la forma del dato in uscita.

Sono effetti collaterali: database, filesystem, rete, SFTP, email, Excel COM,
log, ora corrente, casualità. Vivono nelle action, ai bordi della pipeline, mai
dentro un helper di calcolo.

---

## Option

`Option` / `Some` / `None` esistono nella gem ma **non sono ancora usati** in
questo progetto.

Se li introduci:

- `Option` quando l'assenza è un esito **normale**, non un errore;
- `Result` quando il chiamante deve sapere **perché** è fallito;
- su `Option`, `fmap` è funtoriale e `map` è monadico (opposto della convenzione
  comune, come per `Result`);
- `Option.some?(expr)`, `Option.any?(expr)` per convertire da `nil`.

Non usare `Failure(:not_found)` per un'assenza attesa.

Segnala all'utente che stai introducendo un costrutto nuovo per il progetto.

---

## Stile del codice

### Guard clause

```ruby
def self.filter_giorno(consuntivi)
  return Success(consuntivi) if ctx.params[:giorno_settimana] == "NO"
  try! do
    consuntivi.select { |row| row["Giorno_Sett_Num"] == ctx.params[:day].value[5].to_i }
  end.map_err { Failure("Non riesco ad applicare il filtro giorno_settimana") }
end
```

### Metodi

Estrai un metodo quando rappresenta un concetto del dominio, riduce complessità
reale o elimina duplicazione sostanziale. Non frammentare in metodi di una riga
privi di significato.

### Commenti

Il progetto commenta molto, in italiano, spesso con la forma del dato inline.
**Mantieni questa densità.** Non ripulire commenti esistenti mentre fai altro.

### Metaprogrammazione

Usata nel loader ([forecast_actions.rb](app/actions/forecast_actions.rb)) e
nell'autoload di `Ikigai::Initialization`. Non aggiungerne altra: non nascondere
controllo di flusso, dipendenze o gestione errori dietro una DSL.

---

## Verifica del lavoro

Non ci sono test. La verifica è:

```bash
bundle exec rubocop -c .rubocop_strict.yml
```

```bash
bundle exec rufo app/
```

Poi, se la modifica tocca una pipeline, esecuzione reale:

```bash
ruby steg.rb --log=debug --interface=cli --enviroment=development forecast --dt 10/04/2021 --H 10
```

Il config `.rubocop_strict.yml` intercetta anche i `binding.pry` dimenticati.

Se aggiungi logica di calcolo pura e complessa, proponi un test isolato in
`test/` — ma dichiaralo come aggiunta, non darlo per scontato.

---

## Anti-pattern

```ruby
class Operation
  def call(params)
    @params = params
    validate!
    normalize!
    save!
    notify!
    @user
  rescue StandardError
    false
  end
end
```

Problemi: stato implicito nelle variabili di istanza, `rescue` che ingoia la
causa, output booleano non informativo, impossibile sapere quali step siano
stati eseguiti, non componibile.

Altri anti-pattern specifici di questo progetto:

- `rescue` nudo dentro un'action al posto di `try!`;
- errore passato a `fail_and_return!` come stringa quando serve l'hash a tre chiavi;
- `fmap` su un `Result`;
- `case/in` su `Success`/`Failure`;
- dato messo nel `ctx` che nessuno step successivo legge;
- action che restituisce a volte un valore, a volte `nil`, a volte un `Result`.

---

## Processo di analisi e refactoring

1. identifica input, output ed effetti collaterali dell'action;
2. distingui errori previsti da errori eccezionali;
3. verifica se `nil` o booleani stanno nascondendo uno stato di dominio;
4. controlla che ogni `rescue` sia un `try!`;
5. verifica che l'hash di errore abbia le tre chiavi;
6. controlla la coerenza fra `expects`/`promises`, il commento `E:[] P:[]` nei
   `steps` e la YARD;
7. separa il calcolo puro dall'accesso a Excel/DB;
8. valuta se il dato nel `ctx` serve davvero;
9. proponi **la modifica minima** che migliora il design.

Non riscrivere codice imperativo funzionante solo per renderlo funzionale.

---

## Criteri decisionali

Prima di introdurre un'astrazione:

1. riduce complessità reale?
2. rende gli errori più espliciti?
3. migliora la composizione?
4. elimina stato implicito?
5. resta idiomatica in Ruby 3.1 e coerente con il resto del progetto?
6. si spiega con un esempio breve?
7. il beneficio supera il costo di manutenzione?

Se le prime cinque risposte sono deboli, usa la soluzione più semplice.

---

## Regole per l'assistente

Quando generi o modifichi codice in questo progetto:

- non sostituire tutto con monadi;
- non imporre immutabilità totale;
- non aggiungere gem senza necessità;
- non usare costrutti Ruby 3.2+;
- non usare `fmap` su `Result`, né `case/in` sulle enum della gem;
- non usare `rescue` nudo in un'action;
- non rifattorizzare le variabili di classe dei concern Excel;
- non toccare commenti o formattazione adiacenti alla modifica;
- non dichiarare miglioramenti prestazionali senza misurarli.

Quando proponi una soluzione:

1. mostra il contratto (`expects` / `promises`) prima del codice;
2. spiega il percorso `Success` e quello `Failure`;
3. evidenzia gli effetti collaterali;
4. indica dove hai inserito lo step nella `steps` del controller;
5. verifica che il codice sia Ruby valido per la 3.1;
6. dai una soluzione concreta e completa, non un ventaglio di alternative.

---

## Forma architetturale

```text
costanti e input congelati (freeze / Hamster / IceNine)
        ↓
trasformazioni pure (self.metodo privato, chaining .then)
        ↓
try! -> Result -> map_err -> ctx.fail_and_return!
        ↓
action con contratto expects/promises
        ↓
pipeline dichiarativa: Organizer.steps
        ↓
effetti collaterali (Excel COM, SQLite, SFTP, mail) dentro le action
        ↓
check_result -> exit 0 / 2, rescue del controller -> exit 1
```

L'obiettivo è codice che mantenga l'espressività di Ruby riducendo ambiguità,
stato implicito e gestione dispersiva degli errori.
