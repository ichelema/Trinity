# Chart Recipes (openpyxl)

Read this file when building charts. Each recipe is a self-contained pattern.
Adapt data ranges to your actual sheet layout.

## Setup (common to all recipes)

```python
from openpyxl.chart import (
    BarChart, BarChart3D, LineChart, AreaChart, PieChart,
    ScatterChart, Reference, Series
)
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.chart.text import RichText
from openpyxl.drawing.text import Paragraph, ParagraphProperties, CharacterProperties, Font as DrawingFont
from openpyxl.utils import get_column_letter

# Consistent color palette
COLORS = ['4472C4', 'ED7D31', 'A5A5A5', 'FFC000', '5B9BD5', '70AD47']

def style_chart(chart, title, x_label=None, y_label=None, width=18, height=10):
    """Apply consistent professional styling to any chart."""
    chart.width = width
    chart.height = height
    chart.title = title
    chart.style = 10
    if x_label:
        chart.x_axis.title = x_label
    if y_label:
        chart.y_axis.title = y_label
    chart.legend.position = 'b'  # bottom legend

def apply_colors(chart, colors=COLORS):
    """Apply palette to all series."""
    for i, s in enumerate(chart.series):
        s.graphicalProperties.solidFill = colors[i % len(colors)]
```

## Bar Chart (Horizontal) — Comparison / Ranking

Data layout: A=categories, B=values (sorted descending in the sheet).

```python
chart = BarChart()
chart.type = "bar"        # horizontal
chart.grouping = "clustered"
style_chart(chart, "Revenue by Region", y_label="Region", x_label="Revenue ($K)")

data = Reference(ws, min_col=2, max_col=2, min_row=1, max_row=ws.max_row)
cats = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
apply_colors(chart)

# Data labels on bars
chart.series[0].dLbls = DataLabelList()
chart.series[0].dLbls.showVal = True
chart.series[0].dLbls.numFmt = '#,##0'

chart.legend = None  # single series, legend is redundant
ws.add_chart(chart, "D2")
```

## Column Chart (Vertical) — Time-based Comparison

Data layout: A=periods, B..N=metrics. Row 1 has headers.

```python
chart = BarChart()
chart.type = "col"
chart.grouping = "clustered"
style_chart(chart, "Quarterly Revenue", x_label="Quarter", y_label="Revenue ($K)")

data = Reference(ws, min_col=2, max_col=4, min_row=1, max_row=ws.max_row)
cats = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
apply_colors(chart)

chart.y_axis.numFmt = '#,##0'
ws.add_chart(chart, "F2")
```

## Stacked Bar (100%) — Part-of-Whole

```python
chart = BarChart()
chart.type = "bar"
chart.grouping = "percentStacked"
style_chart(chart, "Revenue Mix by Region", y_label="Region")

data = Reference(ws, min_col=2, max_col=5, min_row=1, max_row=ws.max_row)
cats = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
apply_colors(chart)

chart.x_axis.numFmt = '0%'
ws.add_chart(chart, "G2")
```

## Line Chart — Trend Over Time

Data layout: A=dates, B..N=series. Row 1 has headers.

```python
chart = LineChart()
style_chart(chart, "Monthly Active Users", x_label="Month", y_label="Users")

data = Reference(ws, min_col=2, max_col=3, min_row=1, max_row=ws.max_row)
cats = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)

# Style lines
for i, s in enumerate(chart.series):
    s.graphicalProperties.line.solidFill = COLORS[i]
    s.graphicalProperties.line.width = 22000  # EMUs, ~2pt
    s.smooth = False  # straight segments, not curved

chart.y_axis.numFmt = '#,##0'
chart.x_axis.tickLblPos = 'low'
ws.add_chart(chart, "D2")
```

## Combo Chart — Line + Bar (e.g., revenue bars + margin line)

```python
bar = BarChart()
bar.type = "col"
bar.grouping = "clustered"
style_chart(bar, "Revenue & Margin Trend", x_label="Quarter")

bar_data = Reference(ws, min_col=2, max_col=2, min_row=1, max_row=ws.max_row)
cats = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
bar.add_data(bar_data, titles_from_data=True)
bar.set_categories(cats)
bar.series[0].graphicalProperties.solidFill = COLORS[0]
bar.y_axis.title = "Revenue ($K)"
bar.y_axis.numFmt = '#,##0'

line = LineChart()
line_data = Reference(ws, min_col=3, max_col=3, min_row=1, max_row=ws.max_row)
line.add_data(line_data, titles_from_data=True)
line.series[0].graphicalProperties.line.solidFill = COLORS[1]
line.series[0].graphicalProperties.line.width = 22000
line.y_axis.title = "Margin %"
line.y_axis.numFmt = '0.0%'
line.y_axis.axId = 200  # secondary axis

bar += line  # merge into combo
ws.add_chart(bar, "E2")
```

## Scatter Plot — Correlation

Data layout: A=x values, B=y values. Row 1 has headers.

```python
chart = ScatterChart()
style_chart(chart, "Price vs Volume", x_label="Price ($)", y_label="Volume")

xvals = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
yvals = Reference(ws, min_col=2, min_row=2, max_row=ws.max_row)
series = Series(yvals, xvals, title="Products")
series.graphicalProperties.line.noFill = True  # dots only
series.marker.symbol = 'circle'
series.marker.size = 5
series.marker.graphicalProperties.solidFill = COLORS[0]
chart.series.append(series)

# Add trendline
from openpyxl.chart.trendline import Trendline
series.trendline = Trendline(trendlineType='linear', dispRSqr=True, dispEq=True)

ws.add_chart(chart, "D2")
```

## Donut Chart — Part-of-Whole (few categories)

Max 6 slices. Sort data largest-to-smallest before charting.

```python
from openpyxl.chart import PieChart

chart = PieChart()
chart.style = 10
chart.title = "Market Share"
chart.width = 12
chart.height = 10

data = Reference(ws, min_col=2, max_col=2, min_row=1, max_row=ws.max_row)
cats = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)

# Convert to donut
from openpyxl.chart import DoughnutChart
chart = DoughnutChart()
chart.title = "Market Share"
chart.width = 12
chart.height = 10
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)

# Data labels showing percentage
chart.series[0].dLbls = DataLabelList()
chart.series[0].dLbls.showPercent = True
chart.series[0].dLbls.showVal = False
chart.series[0].dLbls.showCatName = True

ws.add_chart(chart, "D2")
```

## Histogram — Distribution

Build the histogram in pandas, write bins to Excel, then chart as column:

```python
import numpy as np

# Compute histogram bins
counts, bin_edges = np.histogram(df['value'], bins='auto')
bin_labels = [f"{bin_edges[i]:.0f}-{bin_edges[i+1]:.0f}" for i in range(len(counts))]

# Write to a sheet
hist_ws = wb.create_sheet("Distribution")
hist_ws.append(["Bin", "Count"])
for label, count in zip(bin_labels, counts):
    hist_ws.append([label, int(count)])

# Chart as column with no gap
chart = BarChart()
chart.type = "col"
chart.grouping = "clustered"
style_chart(chart, "Value Distribution", x_label="Range", y_label="Frequency")
chart.gapWidth = 0  # no gap between bars = histogram look

data = Reference(hist_ws, min_col=2, max_col=2, min_row=1, max_row=len(counts)+1)
cats = Reference(hist_ws, min_col=1, min_row=2, max_row=len(counts)+1)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
chart.series[0].graphicalProperties.solidFill = COLORS[0]
chart.legend = None

hist_ws.add_chart(chart, "D2")
```

## Area Chart — Trend with Magnitude

```python
chart = AreaChart()
chart.grouping = "standard"
style_chart(chart, "Cumulative Sales", x_label="Month", y_label="Sales ($K)")

data = Reference(ws, min_col=2, max_col=2, min_row=1, max_row=ws.max_row)
cats = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)

chart.series[0].graphicalProperties.solidFill = COLORS[0]
chart.series[0].graphicalProperties.line.solidFill = COLORS[0]

ws.add_chart(chart, "D2")
```

## Conditional Formatting as Heatmap

For matrix-style data (e.g., correlation matrix, monthly performance grid):

```python
from openpyxl.formatting.rule import ColorScaleRule

# Apply 3-color scale: red → yellow → green
ws.conditional_formatting.add(
    f"B2:{get_column_letter(ws.max_column)}{ws.max_row}",
    ColorScaleRule(
        start_type='min', start_color='F8696B',
        mid_type='percentile', mid_value=50, mid_color='FFEB84',
        end_type='max', end_color='63BE7B'
    )
)
```

## KPI Card Pattern

For dashboard summary cells:

```python
from openpyxl.styles import Font, Alignment, PatternFill

# Merge cells for the card
ws.merge_cells('A1:C3')
cell = ws['A1']
cell.value = 1247500
cell.number_format = '$#,##0'
cell.font = Font(name='Arial', size=24, bold=True, color='2F5496')
cell.alignment = Alignment(horizontal='center', vertical='center')

# Label above the number
ws.merge_cells('A4:C4')
label = ws['A4']
label.value = "Total Revenue"
label.font = Font(name='Arial', size=9, color='808080')
label.alignment = Alignment(horizontal='center')

# Comparison line
ws.merge_cells('A5:C5')
delta = ws['A5']
delta.value = "+12.3% vs prior quarter"
delta.font = Font(name='Arial', size=9, color='70AD47')
delta.alignment = Alignment(horizontal='center')
```
