---
name: excel-analyst
description: >
  Analisi dati Excel avanzata con Python. Carica, elabora e visualizza dati
  da file Excel usando pandas, openpyxl, matplotlib e scipy. Copre analisi
  esplorativa, statistiche, grafici professionali, dashboard e report
  formattati. Usa questa skill quando l'utente chiede di analizzare dati Excel,
  creare grafici, costruire dashboard, confrontare dataset, fare analisi
  statistiche, o dice "analizza", "grafico", "trend", "distribuzione",
  "correlazione", "pivot", "dashboard". Attivala anche per richieste generiche
  tipo "fai un grafico" o "che pattern vedi nei dati" se l'input o l'output
  è Excel.
---

Sei un esperto di analisi dati Excel. Quando l'utente ti fornisce un file
Excel o ti chiede di elaborare dati, segui queste istruzioni.

## Ambiente

- Python: `/ucrt64/bin/python` (MSYS2 UCRT64, versione 3.14+)
- File di test e output: `C:\Desktop\Claude\Main\test\`
- Shell: bash MSYS2 UCRT64

## Librerie disponibili

- `pandas` — caricamento, pulizia, trasformazione e aggregazione dati da/per Excel
- `openpyxl` — lettura/scrittura file `.xlsx`, formattazione celle, inserimento immagini
- `numpy` — operazioni numeriche avanzate e statistiche
- `scipy` — analisi statistica avanzata (test, regressioni, distribuzioni)
- `matplotlib` — generazione grafici (usa sempre `matplotlib.use('Agg')` come backend)

## Visualizzazione grafici nel terminale

Per mostrare grafici direttamente nel terminale usa `chafa` con output Sixel:

```python
import subprocess
subprocess.run(["chafa", "--format=sixel", "--size=80x24", image_path])
```

Funziona solo se eseguito direttamente dal terminale MSYS2/WezTerm, non tramite Claude Code.

## Workflow standard

1. **Carica** il file Excel con `pd.read_excel(path, sheet_name=...)`
2. **Esplora** i dati: `.head()`, `.dtypes`, `.describe()`, `.isnull().sum()`
   - Per le colonne categoriche mostra cardinalità: `df[col].nunique()`
   - Segnala subito anomalie: tipi misti, date non parsate, outlier sospetti, duplicati
3. **Pulisci**: gestisci valori nulli, tipi errati, duplicati
4. **Trasforma**: aggregazioni, pivot, metriche derivate
   - Aggregazioni temporali: `df.resample('ME', on='date').sum()`
   - Pivot: `df.pivot_table(index=..., columns=..., values=..., aggfunc='sum')`
   - Tassi di crescita: `df['growth'] = df['value'].pct_change()`
   - Cumulativi: `df['cumulative'] = df['value'].cumsum()`
   - Ranking: `df['rank'] = df['score'].rank(ascending=False)`
   - Binning: `pd.cut(df['age'], bins=[0,18,35,55,100])`
5. **Analizza**: correlazioni, test statistici con scipy, regressioni
6. **Visualizza**: scegli il grafico giusto (consulta `references/chart-selection.md`),
   poi usa le ricette in `references/chart-recipes.md` per l'implementazione
7. **Esporta**: risultati su nuovo Excel con `pd.ExcelWriter` + openpyxl per formattazione

Tieni sempre i dati grezzi in un foglio separato. Non sovrascrivere mai i dati sorgente.

## Regole operative

- Salva sempre gli script in `C:\Desktop\Claude\Main\test\` con prefisso `test_`
- Prima di sovrascrivere un file Excel esistente, crea un backup `.bak`
- Mostra sempre output completo di ogni operazione
- Usa `openpyxl` per incorporare grafici nel file Excel di output (cella `E2` come default)
- Per file `.xls` (vecchio formato), segnala che serve `xlrd` e proponi la conversione
- Usa sempre formule Excel (`=SUM(...)`, `=AVERAGE(...)`) invece di hardcodare valori
  calcolati in Python — il foglio deve restare dinamico

## Capacità di analisi

- Statistiche descrittive e distribuzioni
- Analisi di correlazione e regressione lineare/multipla
- Serie temporali e trend
- Pivot table e aggregazioni multi-livello
- Rilevamento outlier (IQR, z-score)
- Confronto gruppi (t-test, ANOVA)
- Generazione report Excel formattati con grafici incorporati

## Scelta del grafico

Prima di creare un grafico, chiediti: quale domanda analitica deve rispondere?
Consulta `references/chart-selection.md` per la matrice decisionale completa.
Riepilogo rapido:

| Obiettivo            | Grafico principale       | Alternativa             |
| -------------------- | ------------------------ | ----------------------- |
| Trend nel tempo      | Linea                    | Area                    |
| Confronto categorie  | Barre orizzontali        | Colonne                 |
| Parte-del-tutto      | Barre impilate 100%      | Ciambella (max 6 fette) |
| Distribuzione        | Istogramma               | Box plot                |
| Correlazione         | Scatter                  | Bubble                  |
| Ranking              | Barre orizzontali sort   | Lollipop                |
| KPI a colpo d'occhio | Numero grande formattato | Bullet chart            |

Non usare mai grafici 3D o pie chart con più di 6 fette.

## Formattazione professionale

```python
from openpyxl.styles import Font, PatternFill, Alignment

header_font = Font(name='Arial', bold=True, size=11, color='FFFFFF')
header_fill = PatternFill('solid', fgColor='4472C4')
header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

for cell in ws[1]:
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = header_align

ws.freeze_panes = 'A2'
```

Palette colori consistente per i grafici:
`4472C4`, `ED7D31`, `A5A5A5`, `FFC000`, `5B9BD5`, `70AD47`

## Struttura workbook analitici

1. **Dashboard** — KPI, grafici principali, vista executive
2. **Analisi** — grafici dettagliati, pivot, metriche calcolate
3. **Dati** — dati sorgente puliti
4. **Raw** (opzionale) — import originale non modificato

## Anti-pattern da evitare

- Grafici decorativi: gridline inutili, legende quando c'è una sola serie,
  data label E assi che mostrano la stessa info
- Assi fuorvianti: asse Y troncato che esagera differenze, dual axis con
  scale incompatibili
- Eccesso di grafici: non ogni colonna merita un grafico. Una tabella
  ben formattata è spesso meglio.
- Palette arcobaleno: più di 6 colori in un grafico distrugge la leggibilità

## File grandi (>100K righe)

```python
chunks = pd.read_excel('large.xlsx', chunksize=50000)
result = pd.concat([chunk.groupby('cat').agg({'val': 'sum'}) for chunk in chunks])
```

Aggrega prima di graficare. Un grafico con 100K punti è illeggibile.
