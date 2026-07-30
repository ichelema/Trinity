# Sequencer, testing, configurazione e localizzazione

Reference per `in_sequence` (do-notation su Result), `Switchyard::Testing::ContextFactory`, `Switchyard::Configuration` e la risoluzione dei messaggi di `fail!`/`succeed!`.

## Sequencer (`in_sequence`) — do-notation su Result

`Switchyard::Sequencer` (portato dalla gem deterministic, MIT) fornisce `in_sequence`: un blocco in stile do-notation in cui ogni step restituisce un `Result`, la sequenza si interrompe al primo `Failure`, e i valori legati con `get`/`let` sono visibili per nome a tutti gli step successivi.

**Quando usarlo**: una pipeline `Success(x) >> m(:step1) >> m(:step2)` passa un solo valore di mano in mano. Quando uno step ha bisogno dei valori *intermedi* di più step precedenti, il chaining diventa scomodo: `in_sequence` li tiene tutti disponibili per nome.

```ruby
class DownloadRemit
  include Switchyard::Prelude

  def call(row)
    in_sequence do
      get(:url)      { extract_url(row) }        # lega il valore del Success a :url
      get(:file)     { fetch(url) }              # :url è disponibile qui
      let(:name)     { File.basename(url) }      # lega un valore semplice (non-Result)
      and_then       { validate(file) }          # step senza binding
      observe        { logger.info("got #{name}") } # side effect, valore ignorato
      and_yield      { Success(name) }           # risultato finale della sequenza
    end
  end
end
```

### DSL degli step

| Step | Firma | Il blocco deve restituire | Semantica |
|---|---|---|---|
| `get` | `get(name, &block)` | un `Result` | su `Success` lega il valore *scartocciato* a `name`; su `Failure` la sequenza si ferma e lo restituisce |
| `let` | `let(name, &block)` | un valore qualsiasi | lega il valore di ritorno così com'è (nessun unwrapping) |
| `and_then` | `and_then(&block)` | un `Result` | esegue lo step senza binding; un `Failure` corto-circuita |
| `observe` | `observe(&block)` | qualsiasi cosa | side effect: il valore di ritorno è ignorato, la sequenza prosegue |
| `and_yield` | `and_yield(&block)` | un `Result` | **obbligatorio, ultimo step**: il suo valore è il risultato dell'intero blocco `in_sequence` |

- `in_sequence` restituisce il `Result` di `and_yield` (o il primo `Failure` incontrato).
- Gli step sono lazy: i blocchi vengono eseguiti solo alla fine (`Sequencer#yield`), in ordine, e solo finché il risultato accumulato è `Success`. Anche il blocco di `let` e di `observe` non gira se uno step precedente è fallito.
- Definire uno step dopo `and_yield`, o chiamare `and_yield` due volte, solleva `Switchyard::Sequencer::InvalidSequenceError` (`'and_yield already called'`); ometterlo del tutto solleva `'and_yield not called'`.
- Ogni step senza blocco solleva `ArgumentError, 'no block given'`.
- I nomi legati sono risolti da un `OperationWrapper < SimpleDelegator` via `method_missing`: se il nome è tra i binding vince il valore legato, altrimenti la chiamata è delegata all'oggetto originale.

### Prelude

`include Switchyard::Prelude` espone come metodi locali:

| Helper | Provenienza | Cosa fa |
|---|---|---|
| `in_sequence` | `Prelude` include `Sequencer` | entra nel blocco do-notation |
| `Success(s)` / `Failure(f)` | `Prelude::Result` (incluso in `Prelude`) | costruttori di `Switchyard::Result::Success/Failure` |
| `try!(&)` | `Prelude::Result` | wrappa il blocco: eccezione → `Failure(errore)`, altrimenti `Success(valore)` |

`Some()`, `None()` e `Option()` stanno in `Switchyard::Prelude::Option`, che **non** è incluso in `Prelude`: va incluso esplicitamente (`include Switchyard::Prelude::Option`).

## Testing: `Switchyard::Testing::ContextFactory`

Non caricato dal require principale: serve `require 'switchyard/testing'`.

Per testare una action isolata serve un context realistico "già passato" dagli step precedenti. Costruirlo a mano è tedioso e rischia di divergere da ciò che le action a monte producono davvero. `ContextFactory` esegue l'organizer vero e **intercetta il context subito prima della action bersaglio** (hook before-action + `throw/catch`), restituendolo senza eseguire il resto della pipeline.

| API | Descrizione |
|---|---|
| `ContextFactory.make_from(organizer)` | crea la factory per l'organizer |
| `#for(action)` | imposta la action alla quale fermarsi (il context è catturato *prima* che esegua) |
| `#with(...)` | invoca `organizer.call(...)` inoltrando gli argomenti; restituisce il `Context` al punto di intercettazione |

Esempio RSpec (dal README):

```ruby
require "spec_helper"
require "switchyard/testing"

RSpec.describe ETL::SetsUpMappingsAction do
  let(:context) do
    Switchyard::Testing::ContextFactory
      .make_from(SomeOrganizer)          # esegue la pipeline reale
      .for(described_class)              # si ferma subito prima della nostra action
      .with(payload: File.read("spec/data/payload.json"))
  end

  it "sets up mappings correctly" do
    result = described_class.execute(context)
    expect(result).to be_success
  end
end
```

Il pattern di test resta: la action sotto test si esercita con `described_class.execute(context)`; l'organizer si testa "da fuori" con `call` verificando gli effetti sui dati. `ContextFactory` serve solo quando bisogna zoomare su una action in mezzo alla pipeline.

L'hook è per-chiamata: viene tolto sia dalla classe organizer (`remove_before_actions`, in `ensure`) sia dal context catturato (`ctx[:_before_actions].delete(hook)`), così riusare il context con `Action#execute` non lo ri-innesca.

## `Switchyard::Configuration`

Configurazione globale, accessor a livello di classe; impostarla al boot (es. initializer Rails), prima che giri qualsiasi action.

| Opzione | Default | Note |
|---|---|---|
| `Configuration.logger =` | `Logger.new(nil)` a livello `WARN` (logging spento) | usato da tutti gli organizer/action; `Logger.new(STDOUT)` per accenderlo, `Logger.new('/dev/null')` per silenziarlo. Override per singolo organizer: `log_with Logger.new("/my/special.log")` |
| `Configuration.localization_adapter =` | auto-selezione al primo accesso: `Switchyard::I18n::LocalizationAdapter` se la costante `::I18n` è caricata, altrimenti `Switchyard::LocalizationAdapter` (hash-based) | qualsiasi oggetto che risponde a `success` e `failure` |
| `Configuration.locale =` | `:en` | usato solo dall'adapter built-in (l'adapter I18n usa il locale di `::I18n`) |

```ruby
Switchyard::Configuration.logger = Rails.logger
Switchyard::Configuration.locale = :it
Switchyard::Configuration.localization_adapter = MyLocalizer.new
```

## Localizzazione dei messaggi

I `Symbol` passati a `fail!`/`succeed!` vengono risolti dall'adapter configurato; le stringhe passano invariate. Il testo risolto si legge poi da `result.message`.

**Adapter built-in** (`Switchyard::LocalizationAdapter`, nessuna dipendenza extra): cerca in `Switchyard::LocalizationMap.instance`, un `Hash` singleton da popolare a mano. Il lookup è:

```ruby
LocalizationMap.instance.dig(locale, :"<action_underscore>", :switchyard, :failures | :successes, chiave)
```

```ruby
Switchyard::LocalizationMap.instance[:en] = {
  :foo_action => {
    :switchyard => {
      :failures  => { :exceeded_api_limit => "Exceeded API limit" },
      :successes => { :api_call_ok => "All good" }
    }
  }
}
```

**Adapter I18n** (`Switchyard::I18n::LocalizationAdapter`): selezionato in automatico se l'app ha caricato la gem `i18n` (non è più dipendenza runtime della gem). Traduce con `::I18n.t(key, scope: "<action_underscore>.switchyard.failures|successes", **options)`; le opzioni extra di `fail!`/`succeed!` diventano variabili di interpolazione (`%{last_four}` nello YAML). Le classi annidate seguono l'underscore: `PaymentGateway::CaptureFunds` → scope `payment_gateway/capture_funds.switchyard.failures`.

**Adapter custom**: sottoclassare uno dei due e sovrascrivere il lookup (es. `i18n_scope_from_class(action_class, type)` per l'adapter I18n), poi assegnarlo a `Configuration.localization_adapter`.

## Gotcha

- **Blocchi `in_sequence` valutati con `instance_eval` sull'`OperationWrapper`**: `self` cambia. I metodi vengono delegati all'oggetto originale (SimpleDelegator) e le variabili locali della closure restano visibili, ma le **variabili di istanza** (`@ivar`) dentro gli step si risolvono contro il wrapper, non contro il tuo oggetto: usare metodi accessor, non `@ivar`.
- **Un binding fa ombra ai metodi**: se `get(:user)`/`let(:name)` usa un nome che coincide con un metodo dell'oggetto, negli step successivi vince il valore legato (i binding sono controllati prima della delega).
- **`get`/`and_then` esigono un `Result`**: se il blocco restituisce un valore semplice, la compilazione della pipeline chiama `.map` su di esso → `NoMethodError` a runtime. Per i valori semplici c'è `let`.
- **`observe` non cattura le eccezioni**: il valore di ritorno è ignorato, ma un `raise` nel blocco propaga fuori da `in_sequence`. Per side effect fallibili usare `and_then { try! { ... } }`.
- **`ContextFactory#with` non fallisce se la action bersaglio non viene mai raggiunta** (una action precedente fallisce o skippa, o la action non è nella pipeline): il `catch` restituisce semplicemente il risultato finale di `organizer.call`. Il test riceve un context "sbagliato" senza errori: verificare le precondizioni nel test.
- **Organizer con logica extra in `call`**: `with(...)` inoltra gli argomenti a `organizer.call`; se il `call` fa altro oltre a `with(ctx).reduce(actions)`, conviene un organizer test-only nello spec (vedi `spec/acceptance/testing/context_factory_spec.rb` della gem).
- **Chiave `:switchyard`, non `:light_service`**: il README (ereditato da light-service) mostra ancora `:light_service` nella `LocalizationMap` e negli scope I18n, ma l'implementazione usa `:switchyard` in entrambi gli adapter. Con `:light_service` il lookup restituisce `nil` (built-in) o solleva/produce "translation missing" (I18n).
- **Auto-selezione dell'adapter memoizzata**: `Configuration.localization_adapter` decide al **primo accesso** (`||=`). Se `i18n` viene caricata dopo, resta l'adapter built-in: caricare `i18n` prima, o assegnare l'adapter esplicitamente.
- **Interpolazione solo con l'adapter I18n**: l'adapter built-in usa le opzioni solo per il tipo (`:failures`/`:successes`) e ignora le variabili di interpolazione; il `dig` restituisce la stringa cruda.
- **`require 'switchyard/testing'` esplicito**: `ContextFactory` non è caricato da `require 'switchyard'` (il README mostra ancora il vecchio path `light-service/testing`).
