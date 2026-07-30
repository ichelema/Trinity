---
name: ruby
description: >
  Scrivi, analizza e rifattorizza codice Ruby usando lo stile funzionale
  pragmatico basato su Switchyard: pipeline dichiarative di action
  (Organizer + steps), contratti expects/promises, errori come valori con try!
  e fail_and_return!, immutabilità selettiva (Hamster, IceNine, freeze) e
  separazione fra logica pura ed effetti collaterali. Usa questa skill quando
  crei o modifichi action, organizer, controller, concern o model in Ruby,
  quando devi decidere come propagare un errore, gestire nil, comporre
  operazioni fallibili, o valutare se introdurre un'astrazione. Attivala
  anche per service object, refactoring verso pattern funzionali, o quando
  il progetto usa switchyard.
---

# Pragmatic Functional Ruby

## Obiettivo

Codice Ruby prevedibile ed esplicito nella gestione degli errori, che resti
idiomatico e leggibile.

Lo scopo **non** è imitare Haskell. Lo scopo è usare tecniche funzionali dove
rendono il codice più testabile e componibile, e lasciare imperativo tutto il
resto.

> Ruby funzionale pragmatico basato su pipeline di action, tipi espliciti per
> successo e fallimento, e immutabilità selettiva.

Mai descriverlo come "programmazione funzionale pura".

---

## Stack di riferimento

La gem monadica è `switchyard`, usata come default in tutti i progetti.
Per i casi in cui Switchyard non è presente (script isolati, test veloci,
spike), usa plain Ruby con pattern Result minimali.

| Ambito         | Strumento                                   |
| -------------- | ------------------------------------------- |
| Gem funzionale | `switchyard`                                |
| Immutabilità   | `hamster`, `ice_nine`                       |
| Test           | `rspec`, `simplecov`, `simplecov-cobertura` |
| Lint           | `rubocop`, `rubocop-performance`            |

Prima di scrivere codice, verifica la versione Ruby del progetto nel `Gemfile`
o `.ruby-version`. Non proporre costrutti che non esistono nella versione in
uso (ad esempio `Data.define` richiede Ruby 3.2+).

---

## API reali di `Result` (leggi prima di scrivere una pipeline)

Questo è il punto in cui è più facile sbagliare: Switchyard **non** segue la
convenzione `dry-monads`.

| Metodo su `Result`      | Semantica reale                                                         | Alias                    |
| ----------------------- | ----------------------------------------------------------------------- | ------------------------ |
| `map`                   | **monadico** — il blocco DEVE restituire un `Result`                    | `>>`, `and_then`, `bind` |
| `map_err`               | monadico sul ramo di errore — il blocco DEVE restituire un `Result`     | `or_else`                |
| `pipe`                  | esegue il blocco per effetto collaterale e restituisce `self` invariato | `<<`                     |
| `fmap`                  | funtoriale (da `Monad`), riavvolge il valore                            | —                        |
| `match`                 | pattern matching esaustivo                                              | —                        |
| `success?` / `failure?` | predicati                                                               | —                        |
| `value`                 | estrae il valore grezzo                                                 | —                        |

Regole che ne discendono:

1. **Su `Result` usa `map` / `>>`, non `bind`.** Sono lo stesso metodo; `map`
   e `>>` sono la forma idiomatica.
2. **Non usare `fmap` su `Result`.** Se il blocco restituisce un `Failure`,
   `fmap` lo incapsula in `Success(Failure(...))` e la pipeline non
   short-circuita. `fmap` è sicuro solo su `Option`.
3. Ogni funzione concatenata deve restituire un `Result`. Mai `nil`, mai un
   valore nudo.

Forma canonica della pipeline:

```ruby
ctx.filtered = Success(ctx.items) \
           >> method(:validate) \
           >> method(:transform) \
           >> method(:enrich)
ctx.fail_and_return!(ctx.filtered.value) if ctx.filtered.failure?
```

```text
Input -> Success -> Success -> Success
             \
              Failure -----------------> Failure
```

Non aggiungere controlli manuali intermedi: il `Result` short-circuita da solo.

---

## Pattern matching

Le enum di Switchyard **non definiscono `deconstruct` / `deconstruct_keys`**: il
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
  Failure()                         { |f| handle_error(f) }
end
```

Le variabili nella guardia prendono il nome degli argomenti del blocco.

---

## Errori previsti come valori

### Regola

- Errore **previsto** di dominio → `Failure` / `ctx.fail_and_return!`.
- Errore **eccezionale** (bug, invariante violata) → eccezione Ruby, gestita
  dal `rescue` del controller/entry point.

Non usare eccezioni come controllo di flusso. Non usare booleani quando il
chiamante deve conoscere il motivo del fallimento.

### `try!` invece di `rescue`

Nelle action **non scrivere mai un `rescue` nudo**. `try!` cattura
`StandardError` e lo trasforma in `Failure(exception)`:

```ruby
try! do
  ctx.result = compute(ctx.input)
end.map_err do |err|
  ctx.fail_and_return!(
    {message: "Descrizione leggibile di cosa è andato storto",
     detail: err.message,
     location: "#{__FILE__}:#{__LINE__}"}
  )
end
```

### Forma dell'errore

Quando l'errore deve essere loggato o mostrato all'utente, l'hash ha
**sempre** tre chiavi:

| Chiave      | Contenuto                                                  |
| ----------- | ---------------------------------------------------------- |
| `:message`  | messaggio leggibile per l'utente finale                    |
| `:detail`   | `err.message` dell'eccezione originale (per debug/verbose) |
| `:location` | `"#{__FILE__}:#{__LINE__}"`                                |

Non perdere la causa originale. Non mettere in `:message` dettagli tecnici
che l'utente non può usare.

Per errori di validazione o configurazione, il messaggio indica cosa
controllare e dove.

### Nota sul meccanismo

`ctx.fail_and_return!` internamente interrompe il flusso con un throw. È il
meccanismo del framework, non una violazione della regola "niente eccezioni per
il flusso": dal punto di vista dell'action è una `return` che porta con sé
l'errore.

---

## Quando applicare pattern funzionali

**Applica quando:**

- l'operazione può fallire in modi diversi e il chiamante deve distinguerli;
- ci sono più passi sequenziali dove ogni passo può fallire;
- il codice mescola logica di dominio ed effetti collaterali;
- `nil` sta nascondendo un caso di dominio significativo.

**Usa plain Ruby quando:**

- il metodo è una trasformazione pura senza casi di errore;
- un semplice `if`/`unless` basta a gestire il caso limite;
- l'operazione ha un solo modo di fallire e un `raise` è sufficiente;
- stai scrivendo un helper breve che non viene composto con altri;
- è uno script isolato o uno spike dove Switchyard non è presente.

Non riscrivere codice imperativo funzionante solo per renderlo funzionale.

---

## Anatomia di una action

Template completo. Rispettalo: l'ordine dei blocchi è parte dello stile.

```ruby
#!/usr/bin/env ruby
# warn_indent: true
# frozen_string_literal: true

module MyModule
  ##
  # Descrizione di cosa fa l'action
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
    #   extend Switchyard::Action
    extend Switchyard::Action

    expects :some_input
    promises :some_output

    # @!method MyAction(ctx)
    #
    #   @!scope class
    #
    #   @param ctx [Switchyard::Context]
    #
    #   @expects some_input [Hash] Descrizione
    #
    #   @promises some_output [Array] Descrizione
    #
    #   @example some_output
    #       # dump reale del dato, non inventato
    #
    #   @return [Switchyard::Context, Switchyard::Context.fail_and_return!]
    executed do |ctx|
      try! do
        ctx.some_output = compute(ctx.some_input)
      end.map_err do |err|
        ctx.fail_and_return!(
          {message: "Messaggio leggibile che dice cosa controllare",
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

Regole:

- header a tre righe (`#!/usr/bin/env ruby`, `warn_indent`, `frozen_string_literal`);
- gli helper sono **metodi di classe** (`def self.x`), dichiarati
  `private_class_method` in fondo;
- `expects` / `promises` sono il contratto: se un dato serve allo step
  successivo passa dal `ctx`, altrimenti resta una variabile locale;
- documentazione YARD con `@example` contenente **dump reali** dei dati.

---

## La pipeline sta nell'Organizer

Il Railway di Switchyard non è una catena di `>>`: è l'array `.steps`.

```ruby
class ProcessData
  extend Switchyard::Organizer

  def self.call(params)
    with(params: params).reduce(steps)
  end

  def self.steps
    # rubocop:disable Layout/ExtraSpacing
    [
      ValidateInput, # E:[params]          P:[validated]
      FetchData,     # E:[validated]       P:[raw_data]
      Transform,     # E:[raw_data]        P:[result]
    ]
    # rubocop:enable Layout/ExtraSpacing
  end

  private_class_method :steps
end
```

Ogni riga porta il commento `E:[expects] P:[promises]` allineato. Se aggiungi
uno step, aggiorna anche il commento e il blocco YARD sopra `.steps`.

---

## Immutabilità selettiva

Congela quello che protegge il modello, non tutto.

| Cosa                               | Come                                                 |
| ---------------------------------- | ---------------------------------------------------- |
| Costanti di dominio                | `STATI = %w[attivo sospeso chiuso].freeze`           |
| Stringhe                           | `# frozen_string_literal: true` in testa a ogni file |
| Parametri di input letti una volta | `Hamster::Hash[...]`                                 |
| Dataset letto e mai mutato         | `IceNine.deep_freeze!(...)`                          |

Non congelare: connessioni, handle di file, socket, oggetti di librerie
esterne, o accumulatori che vengono riempiti in un ciclo.

`freeze` è superficiale: per una struttura annidata serve `IceNine.deep_freeze!`,
e ha un costo. Applicalo dove il dato è grande e condiviso fra step, non ovunque.

---

## Context: mutabile per scelta

Il `ctx` di Switchyard è mutabile e va bene così.

```ruby
ctx.results ||= []
```

Regole:

- il context appartiene a **una sola esecuzione** dell'organizer;
- non condividerlo fra thread;
- un'action non conserva il context in una variabile di classe;
- metti nel context solo ciò che serve a uno step successivo — le
  trasformazioni locali restano variabili locali.

Non copiare il context a ogni step per simulare immutabilità. Mai
`Marshal.load(Marshal.dump(context))`.

---

## Functional core, imperative shell

Tieni pura la logica di calcolo:

```ruby
def self.calcola_media_ponderata(valori, pesi)
  valori.zip(pesi)
    .reduce(0) { |sum, (v, p)| sum + v * p } / pesi.sum.to_f
end
```

Il chaining con `.then` è lo stile idiomatico per trasformazioni pure in
più passaggi:

```ruby
def self.prepara_dati(raw)
  raw
    .select { |r| r[:attivo] }            # [{id: 1, attivo: true, val: 10}, ...]
    .group_by { |r| r[:categoria] }       # {"A" => [...], "B" => [...]}
    .transform_values { |rows| rows.sum { |r| r[:val] } }  # {"A" => 42, "B" => 18}
end
```

Sono effetti collaterali: database, filesystem, rete, API esterne, email,
log, ora corrente, casualità. Vivono nelle action, ai bordi della pipeline,
mai dentro un helper di calcolo.

---

## Option

`Option` / `Some` / `None` esistono in Switchyard.

Usali quando l'assenza è un esito **normale**, non un errore:

- `Option` quando l'assenza è un esito normale;
- `Result` quando il chiamante deve sapere **perché** è fallito;
- su `Option`, `fmap` è funtoriale e `map` è monadico (stessa inversione
  di `Result`);
- `Option.some?(expr)`, `Option.any?(expr)` per convertire da `nil`.

Non usare `Failure(:not_found)` per un'assenza attesa.

---

## Stile del codice

### Guard clause

```ruby
def self.filter_attivi(items)
  return Success(items) if items.empty?
  try! do
    items.select { |row| row[:attivo] }
  end.map_err { Failure("Errore nel filtraggio") }
end
```

### Metodi

Estrai un metodo quando rappresenta un concetto del dominio, riduce
complessità reale o elimina duplicazione sostanziale. Non frammentare in
metodi di una riga privi di significato.

### Commenti

Commenta in italiano, spesso con la forma del dato inline.
Non ripulire commenti esistenti mentre fai altro.

### Metaprogrammazione

Non nascondere controllo di flusso, dipendenze o gestione errori dietro
una DSL. Giustificata solo per eliminare duplicazione meccanica massiccia
(loader, autoload).

---

## Verifica del lavoro

```bash
bundle exec rubocop
```

```bash
bundle exec rspec
```

Se la modifica tocca una pipeline, verifica anche con un'esecuzione reale
(il comando dipende dal progetto).

Se aggiungi logica di calcolo pura e complessa, proponi un test rspec in
`spec/` — ma dichiaralo come aggiunta, non darlo per scontato.

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

Altri anti-pattern:

- `rescue` nudo dentro un'action al posto di `try!`;
- errore passato a `fail_and_return!` come stringa quando serve l'hash a tre chiavi;
- `fmap` su un `Result`;
- `case/in` su `Success`/`Failure` (le enum Switchyard non hanno `deconstruct`);
- dato messo nel `ctx` che nessuno step successivo legge;
- action che restituisce a volte un valore, a volte `nil`, a volte un `Result`.

---

## Processo di analisi e refactoring

1. identifica input, output ed effetti collaterali dell'action;
2. distingui errori previsti da errori eccezionali;
3. verifica se `nil` o booleani stanno nascondendo uno stato di dominio;
4. controlla che ogni `rescue` sia un `try!`;
5. verifica che l'hash di errore abbia le tre chiavi;
6. controlla la coerenza fra `expects`/`promises` e il commento `E:[] P:[]`
   nei `steps`;
7. separa il calcolo puro dagli effetti collaterali;
8. valuta se il dato nel `ctx` serve davvero;
9. proponi **la modifica minima** che migliora il design.

---

## Criteri decisionali

Prima di introdurre un'astrazione:

1. riduce complessità reale?
2. rende gli errori più espliciti?
3. migliora la composizione?
4. elimina stato implicito?
5. resta idiomatica in Ruby e coerente con il resto del progetto?
6. si spiega con un esempio breve?
7. il beneficio supera il costo di manutenzione?

Se le prime cinque risposte sono deboli, usa la soluzione più semplice.

---

## Regole per l'assistente

Quando generi o modifichi codice:

- non sostituire tutto con monadi;
- non imporre immutabilità totale;
- non usare `fmap` su `Result`, né `case/in` sulle enum Switchyard;
- non toccare commenti o formattazione adiacenti alla modifica;
- non dichiarare miglioramenti prestazionali senza misurarli.

Quando proponi una soluzione:

1. mostra il contratto (`expects` / `promises`) prima del codice;
2. spiega il percorso `Success` e quello `Failure`;
3. evidenzia gli effetti collaterali;
4. indica dove hai inserito lo step nella `steps` dell'organizer;
5. verifica che il codice sia Ruby valido per la versione del progetto;
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
effetti collaterali (DB, API, filesystem, email) dentro le action
        ↓
gestione esito finale nel controller/entry point
```

L'obiettivo è codice che mantenga l'espressività di Ruby riducendo ambiguità,
stato implicito e gestione dispersiva degli errori.
