# Switchyard: Action e Context — riferimento API

API completa di `Switchyard::Action` (DSL delle action) e `Switchyard::Context` (busta dati mutabile della pipeline), verificata sul sorgente della gem (`lib/switchyard/action.rb`, `context.rb`, `context/key_verifier.rb`, `errors.rb`).

## Switchyard::Action

Definisce un singolo step di un workflow `Organizer`. Si usa con `extend` (la forma `include Switchyard::Action` è deprecata: funziona ancora ma emette un warning). Un'action riceve un `Context` mutabile e `execute` restituisce sempre quello stesso context.

```ruby
class AddTax
  extend Switchyard::Action

  expects :subtotal
  promises :total

  executed do |context|
    context.total = context.subtotal * 1.2
  end
end

result = AddTax.execute(:subtotal => 100)
result.total # => 120.0
```

### DSL (Action::Macros)

| Macro | Firma | Scopo |
|---|---|---|
| `expects` | `expects(*keys)` oppure `expects(key, :default => valore_o_lambda)` | Chiavi che DEVONO esistere nel context prima dell'esecuzione |
| `promises` | `promises(*keys)` | Chiavi che l'action DEVE aver scritto nel context a fine esecuzione (se ha successo) |
| `executed` | `executed do \|context\| ... end` | Corpo dell'action; genera il metodo di classe `execute(context = {})` |
| `rolled_back` | `rolled_back do \|context\| ... end` | Logica di compensazione; genera il metodo di classe `rollback(context)` |
| `expected_keys` | `expected_keys` | Introspezione: tutte le chiavi dichiarate con `expects` |
| `promised_keys` | `promised_keys` | Introspezione: tutte le chiavi dichiarate con `promises` |

### `expects` con default

Una chiave attesa può dichiarare un fallback `:default`, statico o callable (riceve l'input corrente):

```ruby
class GreetsSomeoneAction
  extend Switchyard::Action

  expects :name
  expects :greeting, :default => "Hello"
  expects :message,  :default => ->(ctx) { "#{ctx[:greeting]}, #{ctx[:name]}!" }

  executed do |context|
    puts context.message
  end
end

GreetsSomeoneAction.execute(:name => "Rick") # ⇒ "Hello, Rick!"
```

Regole verificate nell'implementazione (`expect_key_having_default?`):

- Il default vale per **una sola chiave per chiamata**: `expects :greeting, :default => "Hello"` (la forma riconosciuta è esattamente `[chiave, hash]`).
- Qualsiasi opzione diversa da `:default` solleva `UnusableExpectKeyDefaultError` **a definizione della classe** (messaggio: ``Specify defaults with a `default` key. You have <chiave>.``).
- I default vengono applicati solo alle chiavi mancanti (`missing_expected_keys` usa `context.key?`, che risolve anche gli alias: una chiave raggiungibile via alias è considerata presente e il suo default non scatta).
- I default sono applicati **prima** della verifica delle chiavi attese e anche quando l'action gira dentro un organizer (il context è già un `Context`).
- Applicazione in ordine di dichiarazione: un default lambda può leggere una chiave riempita da un default dichiarato prima (come `:message` sopra).

### `executed` — ciclo di vita di `execute`

`executed` genera il metodo di classe `execute(context = {})`, che accetta un `Hash` o un `Context` esistente. Sequenza reale:

1. Applica i default degli `expects` mancanti, poi converte l'input in `Context` via `Context.make` (se non lo è già).
2. Se `context.stop_processing?` (failure o skip già attivi) → **ritorna subito il context senza eseguire nulla**.
3. Imposta `context.current_action = self`.
4. `KeyVerifier.verify_keys`: chiavi riservate → chiavi attese → *corpo* → chiavi promesse (vedi sotto).
5. Dentro il corpo: registra gli accessor per `expected_keys + promised_keys`, poi in un `catch(:jump_when_failed)` invoca i `before_actions` dell'organizer, il blocco `executed`, i `after_actions`.
6. Ritorna sempre il `Context`.

### `rolled_back`

Genera il metodo di classe `rollback(context)`, chiamato dall'organizer **in ordine inverso di esecuzione** dopo un `Context#fail_with_rollback!` (a partire dall'action fallita, all'indietro). Dichiararlo è opzionale: se l'action non ha effetti persistenti, si omette.

```ruby
class SaveEntities
  extend Switchyard::Action
  expects :user

  executed do |context|
    context.user.save!
  end

  rolled_back do |context|
    context.user.destroy
  end
end
```

Invocare `rolled_back` due volte nella stessa classe solleva `RuntimeError` (``"`rolled_back` macro can not be invoked again"``).

### Ordine di verifica delle chiavi (Context::KeyVerifier)

`KeyVerifier.verify_keys(context, action) { corpo }` esegue, nell'ordine:

| Fase | Verifier | Quando | Eccezione |
|---|---|---|---|
| 1 | `ReservedKeysVerifier` | prima del corpo | `ReservedKeysInContextError` se `expects`/`promises` dichiarano una chiave riservata: `:message`, `:error_code`, `:current_action`, `:organized_by`, `:_aliases`, `:_before_actions`, `:_after_actions` |
| 2 | `ExpectedKeyVerifier` | prima del corpo (dopo i default) | `ExpectedKeysNotInContextError` se una chiave `expects` manca dal context |
| 3 | *(corpo dell'action)* | — | — |
| 4 | `PromisedKeyVerifier` | dopo il corpo | `PromisedKeysNotInContextError` se una chiave `promises` manca dal context |

Dettagli verificati:

- Ogni `verify` fa `return context if context.failure?`: su un context **fallito le verifiche non scattano** — in particolare le promises NON vengono controllate se l'action è fallita (con `fail!`, `fail_and_return!` o `fail_with_rollback!`).
- I controlli di presenza sono alias-aware (`context.key?` risolve gli alias).
- Il messaggio d'errore viene anche loggato con `Configuration.logger.error` prima del raise.
- C'è un **secondo** trigger di `ReservedKeysInContextError`, in `Context#define_accessor_methods_for_keys`: una chiave dichiarata che collide con un metodo esistente di `Hash`/`Context` (es. `expects :size`, `:count`, `:keys`) solleva l'eccezione invece di ombreggiare silenziosamente il metodo. Il rimedio suggerito dal messaggio: rinominare la chiave o accedervi via `ctx[:size]`.

## Switchyard::Context

`Context < Hash`: una busta dati mutabile che viaggia lungo la pipeline e traccia l'esito (`outcome`, un monad `Success`/`Failure` con `{message:, error:}`) accanto ai dati.

### Costruzione e accesso

| API | Firma | Comportamento |
|---|---|---|
| `Context.make` | `make(context = {})` | Da `Hash` crea un nuovo `Context`; un `Context` esistente è restituito as-is. In entrambi i casi consuma un'eventuale chiave `:_aliases` (la rimuove e chiama `assign_aliases`). Altri tipi → `ArgumentError` |
| accessor dinamici | `ctx.chiave` / `ctx.chiave = v` | Solo per le chiavi dichiarate in `expects`/`promises` (registrate via `define_accessor_methods_for_keys` + `method_missing`, niente singleton class). La **lettura delega a `fetch`**: chiave assente → `KeyError`. Chiavi non dichiarate → `NoMethodError` |
| `[]` / `[]=` | come `Hash` | Alias-aware: leggere/scrivere su un alias risolve alla chiave canonica (l'hash interno contiene solo le chiavi originali) |
| `fetch` | `fetch(key, ...)` | Contratto standard di `Hash#fetch`: `KeyError` senza default, **non scrive mai** nel context; alias-aware |
| `key?` | `key?(key)` (alias `has_key?`, `member?`, `include?`) | Alias-aware |
| `dig` | ereditato da `Hash` | **Non** overridato: non risolve gli alias sulla prima chiave |
| `add_to_context` | `add_to_context(values)` | `merge!` di un hash (usato da `Organizer.add_to_context`) |
| `assign_aliases` | `assign_aliases(:originale => :alias)` | Registra la mappa alias→canonico (risoluzione O(1)); ritorna `self` |
| `aliases` | `aliases` | Mappa alias corrente (`{}` se nessuna) |

Attributi: `outcome` (read-only — si cambia solo con `succeed!`/`fail!`), `current_action`, `organized_by` (nil fuori da un organizer; utile per decidere tra `fail!` e `fail_with_rollback!` quando l'action gira standalone).

### Esito e controllo del flusso

| API | Firma | Comportamento |
|---|---|---|
| `succeed!` | `succeed!(message = nil, options = {})` | `outcome = Success(message:)`; il messaggio passa dal `localization_adapter` |
| `fail!` | `fail!(message = nil, options_or_error_code = {})` | `outcome = Failure(message:, error:)`. Secondo argomento: hash con `:error_code` (l'hash del chiamante non viene mutato, viene fatto `dup`) **oppure** codice nudo (`fail!("msg", 42)`). Non interrompe il blocco: serve `next context` o `fail_and_return!` |
| `fail_and_return!` | `fail_and_return!(*args)` | `fail!(*args)` + `throw(:jump_when_failed)` → esce subito dal blocco (vedi sotto) |
| `fail_with_rollback!` | `fail_with_rollback!(message = nil, error_code = nil)` | `fail!` + `raise FailWithRollbackError`; l'organizer la cattura e lancia i `rollback` in ordine inverso. NB: firma posizionale, non hash |
| `skip_remaining!` | `skip_remaining!(message = nil)` | Context resta **successful**; salta le action rimanenti dello scope corrente. Scoped: `iterate`/`reduce_if`/`reduce_until` lo resettano al confine dello scope (il messaggio dell'esito è preservato) |
| `skip_all_remaining!` | `skip_all_remaining!(message = nil)` | Come sopra ma il flag non viene mai resettato: ferma anche gli scope esterni |
| `reset_skip_remaining!` | `reset_skip_remaining!` | Azzera solo il flag `skip_remaining` (uso interno di `ScopedReducable`), l'esito non cambia |

### Predicati e lettura dell'esito

| API | Ritorna |
|---|---|
| `success?` | `outcome.success?` |
| `failure?` | `outcome.failure?` |
| `skip_remaining?` | flag di `skip_remaining!` |
| `skip_all_remaining?` | flag di `skip_all_remaining!` |
| `stop_processing?` | `failure? \|\| skip_remaining? \|\| skip_all_remaining?` — il check unico usato dall'organizer (e da `execute`) a ogni confine di step |
| `message` | `outcome.value[:message]` (String o nil) |
| `error_code` | `outcome.value[:error]` (nil se non impostato) |

Esempio d'uso dei codici:

```ruby
context.fail!("Service call failed", error_code: 1001)
# ... a valle:
case result.error_code
when 1001 then retry_later
when 2001 then alert_ops_team
end
```

## Come `fail_and_return!` interrompe il flusso

Meccanismo esatto: `execute` avvolge `before_actions` + blocco `executed` + `after_actions` in `catch(:jump_when_failed)`. `fail_and_return!` fa `fail!(*args)` e poi `throw(:jump_when_failed)`: il controllo salta fuori dal `catch`, quindi

- il resto del blocco `executed` non viene eseguito;
- **anche gli `after_actions` dell'organizer vengono saltati**;
- la verifica delle promises non scatta (context in failure);
- `execute` ritorna comunque il context (fallito) e l'organizer salta gli step successivi via `stop_processing?`.

Non è un'eccezione: niente da rescueare, e non risale oltre il `catch` dell'action corrente.

## Eccezioni della gem (errors.rb)

Tutte `< StandardError`:

| Eccezione | Quando viene sollevata |
|---|---|
| `FailWithRollbackError` | Da `Context#fail_with_rollback!`. Dentro un organizer è catturata internamente e avvia la sequenza di rollback; **fuori** da un organizer (action standalone via `.execute`) risale al chiamante |
| `ExpectedKeysNotInContextError` | Prima del corpo: una chiave `expects` (senza default applicabile) manca dal context |
| `PromisedKeysNotInContextError` | Dopo il corpo di un'action **riuscita**: una chiave `promises` non è stata scritta nel context |
| `ReservedKeysInContextError` | (a) `expects`/`promises` dichiarano una chiave infrastrutturale (`:message`, `:error_code`, `:current_action`, `:organized_by`, `:_aliases`, `:_before_actions`, `:_after_actions`); (b) una chiave dichiarata collide con un metodo esistente di `Hash`/`Context` (es. `:size`) |
| `UnusableExpectKeyDefaultError` | A definizione della classe: l'opzione passata a `expects` non si chiama `:default` |

## Gotcha

- **Scrivere una chiave non dichiarata via accessor**: `ctx.foo = 1` con `:foo` non in `expects`/`promises` → `NoMethodError` (il `method_missing` delega a `Hash`). Via `ctx[:foo] = 1` funziona sempre, ma non soddisfa nessuna promise dichiarata altrove.
- **Leggere via accessor una chiave assente**: il reader delega a `fetch` → `KeyError` secco, non `nil`. Idem `ctx.fetch(:missing)` senza default (breaking change rispetto a light-service, che ritornava `nil`).
- **Promise mancante = eccezione, ma solo su successo**: se l'action finisce con successo senza aver scritto tutte le `promises` → `PromisedKeysNotInContextError`. Se l'action è fallita, il controllo è saltato: un'action fallita può legittimamente non produrre nulla.
- **`fail!` non esce dal blocco**: il codice dopo `fail!` continua a girare. Per uscire: `next context` oppure `fail_and_return!`.
- **`fail_and_return!` salta anche gli `after_actions`** dell'organizer (il `throw` scavalca `call_after_action`).
- **`fail_with_rollback!` standalone**: senza organizer l'eccezione `FailWithRollbackError` non viene catturata da nessuno. Pattern dal README: `context.organized_by.nil? ? context.fail! : context.fail_with_rollback!`.
- **Nomi di chiave che collidono con metodi di `Hash`**: `expects :size`, `:count`, `:keys`, ecc. → `ReservedKeysInContextError` al momento dell'esecuzione (non a definizione classe). Rinominare o usare `ctx[:size]`.
- **Default lambda: usare `ctx[:chiave]`, non `ctx.chiave`**: il callable riceve l'input grezzo, che può essere ancora un `Hash` puro (i default sono applicati prima della conversione in `Context`) e comunque privo degli accessor, registrati solo dopo.
- **Context già fermo = action non eseguita**: `execute` ritorna subito se `stop_processing?` è vero in ingresso; nemmeno `current_action` viene impostato.
- **`dig` non risolve gli alias** (non è overridato): con alias attivi usare `ctx[:alias]` / `ctx.fetch(:alias)` per il primo livello.
- **`skip_remaining!` è scoped**: dentro `iterate`/`reduce_if`/`reduce_until` esce solo dal sub-pipeline corrente; per fermare tutto usare `skip_all_remaining!`.
- **Alias e chiavi**: `ctx[:alias] = v` scrive sotto la chiave originale; `to_h` contiene solo le chiavi canoniche. Una chiave attesa raggiungibile via alias è considerata presente (niente `ExpectedKeysNotInContextError`, niente default).
- **`Context` è per-chiamata**: non condividere un context vivo tra thread; lo stato di classe (hook, alias, logger) è read-only a runtime, quindi chiamare lo stesso organizer da più thread è sicuro.
