---
name: ruby
description: Gem consigliate per analisi dati in Ruby. Attiva quando si lavora con DataFrame, statistiche, machine learning, lettura/scrittura di file dati (CSV, Excel) in Ruby.
---

# Ruby — Analisi Dati

## Stack ufficiale (una gem per categoria)

| Categoria         | Gem                     | Versione stabile             | Note                                          |
| ----------------- | ----------------------- | ---------------------------- | --------------------------------------------- |
| DataFrame         | `polars-df`             | ✅ attivo 2025                | Binding Rust di Polars — veloce, API moderna  |
| Array numerici    | `numo-narray`           | ⚠️ stabile ma lento sviluppo | Base richiesta da Rumale                      |
| Statistiche       | `enumerable-statistics` | ✅ attivo                     | Estende Enumerable: mean, variance, std, ecc. |
| Machine Learning  | `rumale`                | ✅ v1.0.0 gen 2025            | scikit-learn API, richiede numo-narray        |
| Lettura Excel/CSV | `roo`                   | ✅ attivo                     | Legge xlsx, xls, CSV, ODS                     |

**Non usare**: Daru (fermo), Nyaplot (abbandonato), NMatrix (abbandonato).

## Gemfile minimo

```ruby
# analisi dati
gem "polars-df"
gem "enumerable-statistics"
gem "roo"

# machine learning (solo se necessario)
gem "numo-narray"
gem "rumale"
```

## Esempi rapidi

### DataFrame con Polars

```ruby
require "polars"

df = Polars.read_csv("data.csv")

# filtra, raggruppa, aggrega
df.filter(Polars.col("age") > 30)
  .group_by("city")
  .agg(Polars.col("salary").mean)
```

### Statistiche su array

```ruby
require "enumerable/statistics"

data = [10, 20, 30, 40, 50]
data.mean      # => 30.0
data.variance  # => 250.0
data.stdev     # => 15.81...
```

### Lettura Excel

```ruby
require "roo"

xlsx = Roo::Spreadsheet.open("report.xlsx")
sheet = xlsx.sheet(0)

sheet.each_row_streaming(offset: 1) do |row|
  puts row.map(&:value).inspect
end
```

### ML con Rumale

```ruby
require "numo/narray"
require "rumale"

x = Numo::DFloat[[1,2],[3,4],[5,6]]
y = Numo::Int32[0, 1, 1]

model = Rumale::LinearModel::LogisticRegression.new
model.fit(x, y)
model.predict(Numo::DFloat[[2,3]])
```

## Limiti da tenere presenti

- Non esiste un equivalente maturo di `matplotlib` — per visualizzazioni usare Python o output CSV + tool esterno.
- L'integrazione tra Polars e Rumale richiede conversione manuale (`to_a` → `Numo::NArray`).
- Per dataset molto grandi o analisi statistiche avanzate (scipy, statsmodels), Python rimane la scelta migliore.
