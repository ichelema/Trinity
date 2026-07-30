# Switchyard::Organizer

Orchestratore di pipeline di action: si estende in una classe (`extend Switchyard::Organizer`), si dichiara la sequenza di step con `reduce` e i macro `reduce_*`, e si osserva/controlla l'esecuzione con hook e decorator. Fonte: docstring YARD in `lib/switchyard/organizer.rb` e `lib/switchyard/organizer/*.rb`.

## Flusso base

Non esiste un `call` di default: la convenzione è definire `self.call` a mano, con la lista di step in un metodo di classe (`steps` o `actions`).

```ruby
class CalculatePrices
  extend Switchyard::Organizer

  def self.call(params)
    with(params).reduce(steps)
  end

  def self.steps
    [
      ValidateInput,
      ApplyDiscount,
      ComputeTotal,
    ]
  end
end

result = CalculatePrices.call(:items => [...])
```

Firme reali (da `organizer.rb` / `with_reducer.rb`):

| Metodo | Firma | Semantica |
|---|---|---|
| `with` | `with(data = {}) → WithReducer` | Crea il `Context` (via `Context.make`), inietta aliases e hook di classe nelle chiavi riservate `:_aliases`, `:_before_actions`, `:_after_actions`, e restituisce un reducer (decorato col logger se configurato). |
| `reduce` (class method) | `reduce(*actions) → Context` | Scorciatoia per `with({}).reduce(actions)`. |
| `WithReducer#reduce` | `reduce(*actions) → Context` | Esegue gli step in sequenza (`actions.flatten!`, quindi array annidati sono ok). Solleva `RuntimeError` ("No action(s) were provided") se la lista è vuota. |
| `WithReducer#around_each` | `around_each(handler) → self` | Middleware attorno a ogni step (vedi sotto). |
| `log_with` | `log_with(logger)` | Logger custom per il singolo organizer (fallback: `Switchyard::Configuration.logger`). |

Ogni step può essere una classe che estende `Switchyard::Action`, un oggetto con `#call`, o un lambda: `invoke_action` prova `action.call(ctx)` e ripiega su `action.execute(ctx)`.

## Macro di riduzione

Tutti i macro restituiscono un lambda-step da inserire nella lista passata a `reduce`. Ogni wrapper inizia con `return ctx if ctx.stop_processing?` (context fallito o skip attivo → no-op).

| Macro | Firma | Semantica |
|---|---|---|
| `reduce_if` | `reduce_if(condition_block, steps)` | Esegue `steps` (in scoped reduce) solo se `condition_block.call(ctx)` è truthy. |
| `reduce_if_else` | `reduce_if_else(condition_block, if_steps, else_steps)` | Come `reduce_if` con ramo `else`. |
| `reduce_until` | `reduce_until(condition_block, steps)` | Loop post-condizione (`do...until`): esegue `steps` **almeno una volta**, ferma quando la condizione diventa `true` o `ctx.stop_processing?`. |
| `reduce_while` | `reduce_while(condition_block, steps)` | **Guardia per-step, passata singola**: itera `steps` una volta sola, valuta la condizione **prima di ogni step** e interrompe appena è falsa. NON ripete la lista (vedi Gotcha). |
| `reduce_case` | `reduce_case(:value => key, :when => {v => steps}, :else => steps)` | Dispatch su `ctx[key]`: match con `eql?` sulle chiavi di `:when`, fallback `:else`. Le tre keyword sono **obbligatorie** (`ArgumentError` altrimenti). |
| `execute` | `execute(code_block = nil, &block)` | Avvolge un lambda/blocco in uno step; il valore di ritorno del blocco è ignorato, lo step restituisce sempre `ctx`. |
| `iterate` | `iterate(collection_key, steps)` | Per ogni elemento di `ctx[collection_key]` imposta `ctx[chiave_singolare]` (singolarizzazione con `Dry::Inflector`, calcolata una volta) ed esegue `steps` in scoped reduce. |
| `with_callback` | `with_callback(action, steps)` | Callback in stile streaming/SAX: salva un lambda in `ctx[:callback]` che esegue `steps` in scoped reduce, poi chiama `action.execute(ctx)`; è la action a decidere quando/quante volte invocare `ctx.callback.call(ctx)`. Max 2 livelli di nesting. |
| `add_to_context` | `add_to_context(**args)` | Uno step `execute` per coppia chiave-valore: scrive il valore e registra l'accessor (`define_accessor_methods_for_keys`). |
| `add_aliases` | `add_aliases(args)` | Uno step `execute` che fa merge a runtime nella mappa alias del context (a differenza del macro di classe `aliases`, applicato da `with`). |

### Esempi (da docstring e README)

```ruby
reduce_if(->(ctx) { ctx.retrieved_items.empty? }, [NotifiesEngineeringTeamAction])

reduce_if_else(->(ctx) { ctx.paid? }, [SendReceipt], [SendInvoice])

reduce_until(->(ctx) { ctx[:invoices].empty? }, [ProcessNextInvoice])

reduce_while(->(ctx) { ctx[:number] < 3 }, [AddsOneAction, AddsTwoAction])
# number=0 → AddsOne (0<3), AddsTwo (1<3) → 3. Passata unica.

reduce_case :value => :status,
            :when => {
              :active   => [NotifiesUserAction],
              :archived => [ArchivesRecordAction]
            },
            :else => [RaisesUnknownStatusAction]

execute(->(c) { c[:some_values] = c.some_hash.values })
# oppure
execute { |c| c[:some_values] = c.some_hash.values }

iterate(:items, [ProcessItem])
# dentro ProcessItem → context.item (singolare automatico)

add_to_context :currency => "EUR", :locale => "it"
add_aliases :email => :mail
```

`with_callback` richiede una action-middleware che dichiari `expects :callback` e la invochi essa stessa (esempio adattato dallo spec di accettazione):

```ruby
class IterateCollectionAction
  extend Switchyard::Action
  expects :numbers, :callback
  promises :number

  executed do |ctx|
    ctx.numbers.each do |number|
      ctx.number = number
      ctx.callback.call(ctx)   # esegue gli steps wrappati per ogni item
    end
  end
end

with_callback(IterateCollectionAction, [IncrementCountAction, AddToTotalAction])
```

### Macro dichiarativi di classe (`Organizer::Macros`)

Da usare nel corpo della classe; valgono per ogni run (letti da `with`, mai azzerati — thread-safe).

| Macro | Semantica |
|---|---|
| `aliases(key_hash)` | Mappa alias chiavi del context (es. `aliases :user_email => :email`). |
| `before_actions(*logic)` / `after_actions(*logic)` | Proc (o array di proc) eseguiti prima/dopo **ogni** action; ricevono il context, action corrente in `ctx.current_action`. |
| `append_before_actions(action)` / `append_after_actions(action)` | Aggiungono un callback alla lista esistente. |
| `remove_before_actions(action)` | Rimuove un callback specifico. |

## Osservare l'esecuzione: `around_each` e log decorator

`around_each` imposta un middleware invocato attorno a **ogni** step; l'handler riceve il context e un blocco che deve chiamare per far girare la action:

```ruby
class LogDuration
  def self.call(context)
    start_time = Time.now
    result = yield           # esegue la action wrappata
    duration = Time.now - start_time
    Switchyard::Configuration.logger.info(
      :action   => context.current_action,
      :duration => duration
    )
    result
  end
end

with(:order => order).around_each(LogDuration).reduce(
  LooksUpTaxPercentageAction,
  CalculatesOrderTaxAction,
  ProvidesFreeShippingAction
)
```

Il default è `NOOP_AROUND_EACH_HANDLER = ->(_context, &block) { block.call }`.

**WithReducerLogDecorator**: applicato automaticamente da `WithReducerFactory.make` quando `organizer.logger` (via `log_with`) o `Switchyard::Configuration.logger` è impostato. Logga con prefisso `[Switchyard]`:

- a `with`: nome dell'organizer chiamato + chiavi presenti nel context (livello `info`);
- dopo ogni step riuscito: `executing <Action>`, le sue `expects:`/`promises:` (se dichiarate) e le chiavi del context (`info`);
- al primo failure: `:-((( <Action> has failed...` + `context message:` (livello `warn`);
- al primo skip (`skip_remaining?` o `skip_all_remaining?`): `;-) <Action> has decided to skip the rest of the actions` + messaggio (`info`).

Il flag `logged?` garantisce che failure/skip siano loggati **una sola volta** per run — dopo, il decorator smette di loggare qualsiasi step (`next context if logged?`).

## Composizione

- **Organizer annidati**: un organizer è uno step valido di un altro organizer, perché espone `self.call(ctx)` e `invoke_action` privilegia `#call`. Il context fluisce dentro e fuori (`Context.make` su un `Context` esistente lo riusa). Attenzione: l'organizer interno riassegna `ctx.organized_by` a sé stesso.
- **ScopedReducable** (`scoped_reduce(organizer, ctx, steps)`): usato da `ReduceIf`, `ReduceIfElse`, `ReduceUntil`, `ReduceCase`, `Iterate`, `WithCallback` per eseguire le sotto-pipeline. Resetta `skip_remaining` al confine di scope (prima e dopo la sotto-pipeline), a meno che il context sia `failure?` o `skip_all_remaining?`. Effetto: `skip_remaining!` dentro un costrutto esce solo dallo scope corrente (per `iterate`: dall'item corrente), poi il flusso esterno prosegue; il messaggio di esito impostato viene preservato.
- `ReduceWhile` non usa `scoped_reduce` ma resetta `skip_remaining` manualmente prima e dopo la (unica) passata: l'effetto scoped è lo stesso, la granularità è l'intero costrutto e non il singolo step.

## Failure, skip e rollback

`WithReducer#reduce` non salta nulla di per sé: la protezione è **distribuita**.

- `Action.execute` fa `return action_context if action_context.stop_processing?` prima di lavorare; `stop_processing?` = `failure? || skip_remaining? || skip_all_remaining?`.
- Ogni lambda-macro fa lo stesso guard in testa.
- Quindi dopo un `fail!` gli step restanti vengono comunque "attraversati" come no-op: l'`around_each` handler viene invocato lo stesso (è la action, dentro, a uscire subito), e il blocco di logging in `ensure` gira per ogni step.
- `skip_remaining!` marca l'esito `Success` e ferma lo scope corrente (resettato ai confini di `scoped_reduce`); `skip_all_remaining!` non viene **mai** resettato e ferma anche gli scope esterni, context finale comunque success.
- **Rollback**: se una action solleva `FailWithRollbackError` (via `fail_with_rollback!`), `reduce` la intercetta e chiama `reduce_rollback(actions, index)`: esegue in ordine inverso `action.rollback(context)` sulle action fino a quella fallita inclusa; le action senza metodo `rollback` sono saltate. L'indice del fallimento è tracciato nel reduce (non con `actions.index`), quindi il rollback è completo anche con la stessa classe duplicata nella pipeline.

## Gotcha

1. **`reduce_while` non è un loop.** Nonostante nome e docstring ("Repeats steps while..."), l'implementazione fa `Array(steps).each { |step| break unless condition_block.call(ctx); ... }`: passata singola sulla lista, condizione valutata prima di ogni step. Confermato dagli spec (`number=0` con `[AddsOne, AddsTwo]` → 3, non loop fino a 3+). Per ripetere davvero serve `reduce_until` (che però è post-condizione: gira **sempre almeno una volta**, anche se la condizione è già vera — e può andare in loop infinito se non diventa mai vera).
2. **`reduce_case` accetta solo `:value`, `:when`, `:else`** — tutte e tre obbligatorie, altrimenti `ArgumentError`. La docstring in `organizer.rb` (`:on => ...`, `:default => ...`) è obsoleta e non funziona. Il match usa `eql?`: `"pending"` non matcha `:pending` né `1` matcha `1.0`.
3. **La action di `with_callback` deve essere una `Switchyard::Action`**, non un proc: l'implementazione chiama `action.execute(ctx)` e passa il callback in `ctx[:callback]` (dichiararlo in `expects :callback`). L'esempio con lambda `->(ctx, &blk)` nelle docstring di `organizer.rb`/`with_callback.rb` non gira. Il nesting dei callback è limitato a 2 livelli (salvataggio/ripristino di `ctx[:callback]`).
4. **`around_each` gira anche sugli step saltati**: dopo un failure/skip l'handler viene ancora invocato per ogni step residuo (la action esce subito, ma il "before/after" del middleware sì che gira). Non misurarci side effect che presuppongono l'esecuzione reale.
5. **Log decorator muto dopo il primo failure/skip**: `logged?` blocca ogni log successivo del run, incluso l'eventuale rollback. Inoltre, con logger a livello > `info`, il log di skip esce prima di settare il flag (solo il failure logga a `warn`).
6. **`reduce` con lista vuota solleva** `RuntimeError` ("No action(s) were provided"): un metodo `steps` che restituisce `[]` per un ramo dati è un crash, non un no-op.
7. **Chiavi riservate**: `:_aliases`, `:_before_actions`, `:_after_actions` sono infrastruttura iniettata da `with` e non sono usabili in `expects`/`promises`.
8. **`iterate` singolarizza con `Dry::Inflector`**: con chiavi non-inglesi o irregolari verificare che il singolare sia quello atteso (es. `:items` → `ctx[:item]`); la collezione deve già esistere nel context.
9. **Organizer annidato sovrascrive `organized_by`**: dopo la chiamata interna il context risulta "organized by" l'organizer più interno che ha fatto `with`.

## Discrepanze docstring vs implementazione (riferimento rapido)

| Dove | Docstring | Implementazione reale |
|---|---|---|
| `ClassMethods#reduce_case` | kwargs `:on` + valori + `:default` | kwargs obbligatorie `:value`, `:when`, `:else` (`ReduceCase::Arguments`) |
| `ReduceWhile` / `ClassMethods#reduce_while` | "Repeats steps while..." (loop pre-condizione) | passata singola con guardia per-step (nessuna ripetizione) — il README ("while guard") e gli spec sono corretti |
| `ClassMethods#with_callback` / `WithCallback` | `action` come Proc `->(ctx, &blk)` | serve una Action con `.execute` che legge `ctx[:callback]` (il `@param action [Class]` in `with_callback.rb` è corretto, l'`@example` no) |
