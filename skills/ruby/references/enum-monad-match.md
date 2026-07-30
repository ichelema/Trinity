# Enum algebrici, Monad e DSL `match`

Reference per il layer funzionale di Switchyard: definire ADT custom con `Switchyard.enum`, pattern matching esaustivo con `#match`, e il modulo `Monad` da cui `Result` e `Option` ereditano `fmap`/`bind`.

## `Switchyard.enum` / EnumBuilder

`Switchyard.enum` costruisce un tagged union: una classe contenitore con una sottoclasse per variante. Le varianti si dichiarano chiamando il loro nome come metodo nel blocco, con i nomi degli argomenti come simboli:

```ruby
Threenum = Switchyard::enum {
            Nullary()
            Unary(:a)
            Binary(:a, :b)
           }

Threenum.variants                      # => [:Nullary, :Unary, :Binary]
```

Tre arità, tre comportamenti distinti (mixin `Nullary`, unario, `Binary` in `EnumBuilder::DataType`):

| Arità | Mixin | `value` | Reader generati |
|---|---|---|---|
| 0 argomenti | `Nullary` | `nil`, **privato** (`n.value` → `NoMethodError`) | nessuno |
| 1 argomento | (unario) | il valore stesso | uno col nome dell'argomento (es. `u.a`) |
| 2+ argomenti | `Binary` | `Hash` `{arg => valore}` | uno per argomento |

Costruzione — ogni variante è sia una costante (`Threenum::Unary`) sia un factory method di classe (`Threenum.Unary(1)`):

```ruby
n = Threenum.Nullary                   # => Threenum::Nullary.new()
u = Threenum.Unary(1)                  # u.value => 1, u.a => 1
b = Threenum::Binary(2, 3)             # b.value => { a: 2, b: 3 }
```

Vincoli verificati nel sorgente (`EnumBuilder`):

- `:value` è **riservato** come nome di argomento → `ArgumentError`.
- Ridefinire una variante già esistente → `ArgumentError, "variant X is already defined for this enum"`.
- `Binary#initialize` accetta posizionali (`Rect(10, 20)`) **o** un singolo hash; numero di argomenti sbagliato → `ArgumentError`.

### `Switchyard.impl` — metodi condivisi

`Switchyard.impl(EnumType) { ... }` esegue il blocco con `class_eval` su **ogni** classe variante, per aggiungere metodi comuni:

```ruby
Switchyard::impl(Threenum) {
  def sum
    match {
      Nullary() {        0 }
      Unary()   { |u|    u }
      Binary()  { |a, b| a + b }
    }
  end
}
```

È esattamente così che `Result` e `Option` ottengono `map`, `success?`, `value_or`, ecc.

## Il DSL `match`

Due forme equivalenti: metodo d'istanza (`obj.match { ... }`) o di classe (`Enum.match(obj) { ... }`). Ogni clausola è il nome di una variante con un blocco; i valori interni vengono **spacchettati** e passati come argomenti del blocco:

```ruby
Threenum::Unary(5).match {
  Nullary() {        0 }
  Unary()   { |u|    u }
  Binary()  { |a, b| a + b }
}                                      # => 5
```

Semantica verificata in `enum.rb` (`self.match`):

- **Esaustività**: *tutte* le varianti devono comparire come clausole. Il check avviene **prima** di valutare qualsiasi ramo; se manca una variante viene sollevato `Switchyard::Enum::MatchError` (`"Match is non-exhaustive, [...] not covered"`). Nota: il README lo chiama `NoMatchError`, ma la classe reale è `Enum::MatchError`.
- **Nessun ramo default**: non esiste `else`/`_` come clausola — l'esaustività si ottiene elencando ogni variante (eventualmente con blocco a zero parametri).
- **Ordine**: vince la **prima** clausola del tipo giusto la cui guardia (se presente) passa. L'ordine conta.
- **Parametri del blocco**: o nessuno, o esattamente tanti quanti gli argomenti della variante (altrimenti `MatchError, "Pattern (...) must match (...)"`). Solo parametri nominati `:req`/`:opt`: splat, keyword o parametri anonimi → `ArgumentError`. Si può usare `_` per i valori che non interessano.
- **Se tutte le guardie falliscono** sui rami del tipo giusto: `Enum::MatchError, "No match could be made"`.
- **`self` nei rami**: il blocco è valutato con `instance_exec` sul receiver del binding del chiamante (`block.binding.receiver`), quindi `self` è l'oggetto che racchiude la chiamata a `match`, **non** la variante. Per restituire l'oggetto matchato serve un riferimento esterno (forma `Enum.match(t) { ... }` o una variabile).

### Guardie con `where { ... }`

La guardia si passa come argomento della clausola. Le variabili disponibili nella guardia prendono **i nomi dei parametri del blocco** di quella clausola: il matcher costruisce uno `Struct.new(*nomi_parametri)` riempito con i valori della variante e valuta la guardia con `instance_exec` su quello Struct.

```ruby
Threenum::Unary(5).match {
  Nullary() {     0 }
  Unary()   { |u| u }
  Binary(where { a.is_a?(Integer) && b.is_a?(Integer) }) { |a, b| a + b }
  Binary()  { |a, b| raise "Expected a, b to be numbers" }
}                                      # => 5
```

Conseguenze pratiche (verificate nell'implementazione di `guard_context`):

- dentro `where { ... }`, `self` è lo Struct, **non** il contesto chiamante: per chiamare metodi dello scope esterno serve un receiver esplicito;
- le variabili locali esterne restano visibili per closure (es. `where { n > 0 }` con `n` parametro del metodo che contiene il `match`);
- la guardia riceve anche l'oggetto variante come argomento del blocco (`guard_ctx.instance_exec(obj, &guard)`), quindi `where { |o| ... }` dà accesso all'intera variante;
- una "guardia" che non è un `Proc` viene silenziosamente ignorata (trattata come assente).

Esempio canonico dal README (linked list):

```ruby
def drop(n)
  match {
    Cons(where { n > 0 }) { |h, t| t.drop(n - 1) }
    Cons()                { |_, _| self }
    Nil() { raise EmptyListError }
  }
end
```

## `case/in` nativo: funziona (ed è preferito nei hot path)

Ogni variante include `AnyEnum`, che definisce **sia** `deconstruct` **sia** `deconstruct_keys`:

| Metodo | Nullary | Unaria | Binary |
|---|---|---|---|
| `deconstruct` | `[]` | `[value]` | `value.values` |
| `deconstruct_keys` | `{}` | `{ nome_arg => value }` | `value.dup` (hash per nome) |

Quindi il pattern matching nativo di Ruby è pienamente supportato:

```ruby
case result
in Switchyard::Result::Success[value] then value
in Switchyard::Result::Failure[error] then handle(error)
end
```

Il README (sezione "Upgrading to 6.0") raccomanda esplicitamente `case/in` (o `success?`/`value`) al posto del DSL `match` nei percorsi caldi: è circa **due ordini di grandezza più veloce** (il DSL fa introspezione dei parametri, check di esaustività e `instance_eval` a ogni chiamata).

## Il modulo `Monad`

`Switchyard::Monad` è incluso in `AnyEnum`, quindi **ogni** variante di ogni enum (incluse `Success`/`Failure`, `Some`/`None`) lo eredita. Definisce anche `Monad::NotMonadError`.

| Metodo | Firma | Semantica | Alias |
|---|---|---|---|
| `initialize` | `(init)` | `pure`: avvolge `init` evitando il double-wrap via `join` (`Success(Success(1)) == Success(1)`) | — |
| `join` | `(other)` | collassa `M[M[A]]` → `M[A]` se `other` è della **stessa classe** | — |
| `fmap` | `(proc = nil, &block)` | functor map: applica la funzione al valore interno e ri-avvolge nella **stessa classe** (`self.class.new(...)`) | — |
| `bind` | `(proc = nil, &block)` | bind monadico: la funzione riceve il valore interno e **deve** restituire un'istanza della stessa famiglia di monade (check sulla superclasse), altrimenti `NotMonadError` | `>>=` |
| `value` | `()` | il valore interno (privato nelle varianti Nullary) | — |
| `to_s` | `()` | `value.to_s` | — |
| `==` | `(other)` | stesso tipo **e** stesso valore (usa il reader protetto `monad_value`) | — |
| `inspect` | `()` | `"Success(42)"` ecc. | — |

### Cosa aggiungono/sovrascrivono Result e Option (via `impl`)

`Result` **non** sovrascrive `fmap`/`bind`: aggiunge i metodi branch-aware sopra di essi.

| Metodo Result | Semantica | Alias |
|---|---|---|
| `map` | `bind` solo se `success?`, altrimenti `self` (short-circuit) | `>>`, `and_then` |
| `map_err` | `bind` solo se `failure?`, altrimenti `self` | `or_else` |
| `try` | come `map`, ma le eccezioni diventano `Failure(e)` | `>=` (deprecato) |
| `pipe` | side-effect sul Result intero, ritorna `self` | `<<` (deprecato) |
| `and` / `or` | congiunzione/disgiunzione tra Result (altro tipo → `NotMonadError`) | — |
| `success?` / `failure?` | test del tipo | — |
| `Result.try!` | classe: blocco → `Success(valore)` o `Failure(eccezione)` | `try!` nel `Prelude::Result` |

`Option` invece **sovrascrive** `fmap` (no-op su `None`) e aggiunge:

| Metodo Option | Semantica | Alias |
|---|---|---|
| `fmap` | `Some`: trasforma e ri-avvolge; `None`: ritorna `self` | — |
| `map` | `bind` solo se `some?`, altrimenti `self` | — |
| `some?` / `none?` | test del tipo | `empty?` (di `none?`) |
| `value_or(n)` | valore interno o fallback | — |
| `Option.some?` / `Option.any?` / `Option.try!` | coercizioni di classe (`nil`/vuoto/eccezione → `None`) | — |

Deprecati con warning: `Result#+`, `Option#+`, `Result#<<`, `Result#>=`, `Option#value_to_a`, `Maybe`/`Null`.

## Gotcha

- **Nome dell'eccezione**: il README parla di `NoMatchError`, ma la classe reale è `Switchyard::Enum::MatchError`. Non esiste alcuna costante `NoMatchError` nel codice.
- **`fmap`/`bind` base sono ciechi al ramo**: su `Result`, `Failure(1).fmap { |v| v + 1 }` → `Failure(2)` e `Failure(1).bind { |v| Success(v - 1) }` → `Success(0)` (esempio dal README stesso). Per lo short-circuit railway usare `map`/`map_err` (o `fmap` di `Option`, che è sovrascritto).
- **Init Binary con hash: le chiavi sono ignorate**. `Binary#initialize` fa `args.zip(init[0].values)`: conta l'**ordine di inserzione** dell'hash, non i nomi. `Rect(height: 20, width: 10)` produce `width: 20, height: 10`. Con l'hash, rispettare l'ordine di dichiarazione degli argomenti.
- **Esaustività prima di tutto**: `MatchError` scatta anche se una clausola avrebbe matchato, se un'altra variante non è coperta. Niente ramo `else`.
- **`self` nel ramo ≠ variante**: è il receiver del contesto chiamante; per usare l'oggetto matchato passare per la forma `Enum.match(obj)` o una variabile esterna.
- **`self` nella guardia = Struct**: chiamate a metodi dello scope esterno senza receiver esplicito falliscono (o peggio, colpiscono lo Struct); le locali funzionano per closure.
- **`Nullary#value` è privato**: `Threenum.Nullary.value` → `NoMethodError`; per l'uguaglianza tra monadi esiste il reader protetto `monad_value`.
- **`Some(nil)` solleva `ArgumentError`** ("use None instead"): l'assenza si esprime con `None`, non con `Some(nil)`.
- **Parametri del blocco `match`**: vietati splat/kwargs/parametri anonimi (`ArgumentError` a runtime); se dichiarati, il loro numero deve coincidere con l'arità della variante.
- **Performance**: il DSL `match` costa ~100x rispetto a `case/in`; nei hot path preferire `case/in` o i predicati (`success?`, `some?`).
