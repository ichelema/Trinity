# Result e Option in Switchyard

Reference dei tipi funzionali di `switchyard` (`Result`, `Option`, più i deprecati `Maybe`/`Null`): API verificata sul sorgente, con la semantica reale — che in più punti **non** segue le convenzioni dry-monads.

Sorgenti canonici: `lib/switchyard/functional/{result,option,monad,maybe,null}.rb`.

## Base comune: `Switchyard::Monad`

`Result` e `Option` sono enum (`Switchyard.enum`) i cui varianti includono il modulo `Switchyard::Monad`, che fornisce:

| Metodo | Firma | Semantica |
| --- | --- | --- |
| `initialize` | `new(init)` | "pure" con auto-join: se `init` è già un'istanza della **stessa classe**, viene spacchettato (`Success(Success(1))` → `Success(1)`) |
| `fmap` | `fmap(proc = nil, &block)` | applica il blocco al valore interno e riavvolge in `self.class.new(...)`. **Nessun controllo sul ramo**: eseguito sia su Success sia su Failure (Option lo ridefinisce, vedi sotto) |
| `bind` | `bind(proc = nil, &block)`, alias `>>=` | applica il blocco al valore interno; il ritorno **deve** essere un'istanza del tipo padre (es. un `Result` qualsiasi), altrimenti `NotMonadError`. **Nessun corto-circuito**: eseguito su entrambi i rami |
| `value` | `value` | valore interno (privato sulle varianti nullarie, es. `None`) |
| `to_s` | `to_s` | `value.to_s` (quindi `Success(1).to_s # => "1"`) |
| `==` | `==(other)` | stesso tipo **e** stesso valore interno |
| `inspect` | `inspect` | `"Success(42)"` ecc. |

## `Result` — `Success(:s)` / `Failure(:f)`

Monade railway: si incatena con `map`/`>>`, il primo `Failure` corto-circuita la catena.

### Tabella metodi (dal blocco `Switchyard.impl(Result)`)

| Metodo | Alias | Semantica reale |
| --- | --- | --- |
| `map(proc = nil, &block)` | `>>`, `and_then` | **MONADICO** (attenzione: non è il map funtoriale): `success? ? bind(...) : self`. Il blocco deve restituire un `Result`; su `Failure` non esegue e ritorna `self` |
| `map_err(proc = nil, &block)` | `or_else` | monadico **sul ramo errore**: `failure? ? bind(...) : self`. Il blocco riceve l'errore e deve restituire un `Result` |
| `fmap` | — (da `Monad`) | **funtoriale**: trasforma il valore e riavvolge nello **stesso** costruttore. Esegue anche su `Failure` (`Failure(1).fmap { \|v\| v + 1 } # => Failure(2)`) |
| `bind` | `>>=` (da `Monad`) | bind grezzo, **senza** corto-circuito: `Failure(1).bind { \|v\| Success(v - 1) } # => Success(0)`. Non è un alias di `map` |
| `pipe(proc = nil, &block)` | `<<` (deprecato) | side-effect: chiama il blocco passando **`self`** (l'intero `Result`, non il valore interno) e ritorna `self` invariato. Per logging/strumentazione |
| `success?` / `failure?` | — | predicati di ramo (`is_a?` sulla variante) |
| `or(other)` | — | disgiunzione: `self` su Success, `other` su Failure. `NotMonadError` se `other` non è un `Result` |
| `and(other)` | — | congiunzione: `other` su Success, `self` su Failure. Stesso controllo di tipo |
| `try(proc = nil, &block)` | `>=` (deprecato) | come `map`, ma un'eccezione (`StandardError`) sollevata dal blocco diventa `Failure(exception)` |
| `+(other)` | — | **deprecato** (warning): somma i valori se i rami coincidono, altrimenti ritorna il `Failure` |

```ruby
Success(1).map     { |n| Success(n + 1) }   # => Success(2)
Failure(0).map     { |v| Success(v + 1) }   # => Failure(0)   (corto-circuito)
Failure(1).map_err { |n| Success(n + 1) }   # => Success(2)

Success(1) >> ->(ctx) { Success(ctx + 1) } >> ->(ctx) { Success(ctx + 1) }  # => Success(3)

# Pipeline con side-effect (dal README):
Success(params) >>
  validate >>
  build_request << log >>
  send << log >>
  build_response
```

Nota sulla catena: ogni step di `>>` deve essere una funzione **unaria** che riceve il valore e ritorna un `Result`.

### `try!` per Result

Due forme equivalenti, entrambe catturano `StandardError`:

| Forma | Definizione | Ritorno |
| --- | --- | --- |
| `Switchyard::Result.try! { ... }` | metodo di classe in `result.rb` | `Success(valore del blocco)` oppure `Failure(eccezione)` |
| `try! { ... }` | `Switchyard::Prelude::Result#try!`, delega alla forma di classe | idem |

```ruby
include Switchyard::Prelude::Result

try! { 1 }            # => Success(1)
try! { raise "hell" } # => Failure(#<RuntimeError: hell>)
```

Diverso dall'istanza `Result#try`, che mappa un Result **già esistente** catturando le eccezioni del blocco.

### Costruttori del Prelude (`Switchyard::Prelude::Result`)

Definiti in `result.rb` — esattamente questi tre metodi:

| Metodo | Ritorno |
| --- | --- |
| `Success(s)` | `Switchyard::Result::Success.new(s)` |
| `Failure(f)` | `Switchyard::Result::Failure.new(f)` |
| `try! { ... }` | vedi sopra |

`Switchyard::Prelude` fa `include Result`, quindi `include Switchyard::Prelude` porta con sé `Success()`/`Failure()`/`try!`. Le action li hanno già (`base_class.extend Switchyard::Prelude::Result` in `action.rb`); il `Context` include sia il Prelude Result sia quello Option.

## `Option` — `Some(:s)` / `None()`

Valore opzionale senza informazione d'errore. `Some.new(nil)` solleva `ArgumentError` ("Some cannot wrap nil: use None instead").

### Metodi di classe

| Metodo | Semantica |
| --- | --- |
| `Option.some?(expr)` | `nil` → `None`, altrimenti `Some(expr)`. Nota: `Option.some?([]) # => Some([])` |
| `Option.any?(expr)` | `nil` **o** collezione vuota (`empty?`) → `None`, altrimenti `Some(expr)`. `Option.any?([]) # => None` |
| `Option.to_option(expr) { pred }` | helper `@api private` usato dai due sopra |
| `Option.try! { ... }` | eccezione (`StandardError`) → `None`; altrimenti ritorna **il valore grezzo del blocco, NON avvolto in `Some`** (vedi Gotcha) |

### Metodi d'istanza (dal blocco `impl(Option)` — dispatch diretto, non match engine, per performance)

| Metodo | Alias | Semantica reale |
| --- | --- | --- |
| `fmap { \|v\| ... }` | — | funtoriale **con corto-circuito** (override di `Monad#fmap`): `some? ? self.class.new(yield(@value)) : self`. `None.fmap { ... } # => None` |
| `map(&fn)` | — | monadico: `some? ? bind(&fn) : self`. Il blocco deve ritornare un `Option` (`Some(1).map { \|n\| None } # => None`) |
| `some?` / `none?` | `empty?` (di `none?`) | predicati di ramo |
| `value_or(n)` | — | valore interno su `Some`, fallback `n` su `None` |
| `value` | — (da `Monad`) | valore interno; **privato su `None`** (variante nullaria) → `None.value` solleva `NoMethodError` |
| `value_to_a` | — | **deprecato**: ritorna `@value` grezzo |
| `+(other)` | — | **deprecato** (warning): `None + x # => x`; `Some(a) + Some(b) # => Some(a + b)`; `Some(a) + None # => Some(a)`; `TypeError` se `other` non è `Option` |

```ruby
Some(1).fmap { |n| n + 1 }         # => Some(2)
None.fmap { |n| n + 1 }            # => None

Some(1).map  { |n| Some(n + 1) }   # => Some(2)
None.map     { |n| Some(n + 1) }   # => None

Some(1).value_or(2)                # => 1
None.value_or(0)                   # => 0
```

**Differenza chiave rispetto a Result**: su `Option`, `fmap` corto-circuita su `None`; su `Result`, `fmap` (ereditato da `Monad`) esegue il blocco anche su `Failure`. `map` è monadico su entrambi.

### Prelude Option (`Switchyard::Prelude::Option`)

| Nome | Tipo | Semantica |
| --- | --- | --- |
| `Some(s)` | metodo | `Switchyard::Option::Some.new(s)` |
| `None` | metodo (+ costante) | ritorna l'**istanza condivisa** `Prelude::Option::None` |
| `Option` | metodo (+ costante) | ritorna il modulo `Switchyard::Option` (per `ctx.Option.any?(...)` ecc.) |

Attenzione: a differenza di Result, questo modulo **non** è incluso automaticamente in `Switchyard::Prelude` — va incluso esplicitamente (`include Switchyard::Prelude::Option`). Nel `Context` delle action è già presente: `ctx.Some(...)`, `ctx.None`, `ctx.Option.any?(...)`.

## `Maybe` e `Null` (deprecati)

Entrambi in `maybe.rb`/`null.rb`, **non caricati di default**: servono `require 'switchyard/functional/maybe'`. Sono deprecati (emettono warning a runtime) in favore di `Switchyard::Option` — nel codice nuovo **non usarli**.

- `Maybe(obj)` — ritorna `Null.instance` se `obj.nil?`, altrimenti `obj` stesso (non avvolto). Monkey-patcha `Object` con `#null?` (sempre `false`) e `#some?` (sempre `true`).
- `Null` — NullObject singleton (`Null.instance`, `new` privato): inghiotte qualsiasi chiamata di metodo ritornando se stesso, `to_str` → `''`, `to_ary` → `[]`, `null?` → `true`, `some?` → `false`, `==` vero verso qualunque oggetto che risponde `null?` truthy. `Null.mimic(klass)` limita i metodi inghiottiti all'interfaccia di `klass`.

```ruby
require 'switchyard/functional/maybe'
Maybe(nil)   # => Null.instance
Maybe(42)    # => 42
```

## Gotcha

1. **`map` su Result è monadico, non funtoriale.** `Success(1).map { |n| n + 1 }` solleva `NotMonadError` perché il blocco non ritorna un `Result`. Per la trasformazione pura usa `fmap`.
2. **`bind` NON è un alias di `map` e non corto-circuita.** `Failure(1).bind { |v| Success(v - 1) } # => Success(0)`: esegue il blocco anche sul ramo errore. Gli alias di `map` sono solo `>>` e `and_then`.
3. **`fmap` su Result esegue anche su `Failure`** (`Failure(1).fmap { |v| v + 1 } # => Failure(2)`) e **riavvolge sempre nello stesso costruttore**: `Success(1).fmap { |_| Failure("x") } # => Success(Failure("x"))` — il join di `initialize` spacchetta solo la stessa classe (`Success(Success(1)) # => Success(1)`, ma `Success(Failure(1))` resta annidato). Se il blocco può fallire, usa `map` con un blocco che ritorna `Result`, non `fmap`.
4. **`Option.try!` non avvolge il successo.** Nonostante docstring e README dicano `Option.try! { 1 } # => Some(1)`, l'implementazione è `yield` nudo con `rescue → None.new`: su successo ritorna il valore grezzo del blocco. Affidabile solo se il blocco ritorna già un `Option`; per avvolgere un valore usa `Option.some?`/`Option.any?`.
5. **`pipe` riceve l'intero `Result`, non il valore interno** (`(proc || block).call(self)`), e viene eseguito su entrambi i rami. `<<` e `>=` sono deprecati (`pipe` e `try`).
6. **`nil`**: `Some(nil)` solleva `ArgumentError`; `Success(nil)`/`Failure(nil)` invece sono ammessi. Per convertire un possibile `nil` usa `Option.some?(expr)`; per trattare come assenti anche stringhe/collezioni vuote usa `Option.any?(expr)`.
7. **`Option.some?([]) # => Some([])`** — solo `any?` considera il vuoto come assenza.
8. **`None.value` solleva `NoMethodError`** (metodo privato sulla variante nullaria): usa `value_or(default)` o pattern matching.
9. **`or`/`and` validano il tipo**: passare qualcosa che non è un `Result` solleva `NotMonadError`, non ritorna un default.
10. **`+` è deprecato su entrambi** (Result e Option) ed emette warning: combina i valori esplicitamente.
