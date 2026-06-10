# Chart Selection Guide

Read this file when deciding which chart type to use. The decision depends on
two factors: what analytical question you're answering, and the shape of the data.

## Decision Matrix

### Comparison

**"How do values compare across categories?"**

| Data shape                      | Chart                             | Notes                           |
| ------------------------------- | --------------------------------- | ------------------------------- |
| Few categories (<8), one metric | Horizontal bar, sorted descending | Default choice for comparison   |
| Few categories, 2-3 metrics     | Grouped bar/column                | Keep groups ≤3 series           |
| Many categories (8-20)          | Horizontal bar                    | Never vertical with long labels |
| Two items to compare            | Paired bar or bullet chart        | Highlight the delta             |
| Ranking                         | Horizontal bar, sorted            | Add rank numbers if useful      |

### Time series

**"How does a value change over time?"**

| Data shape                    | Chart                                           | Notes                                          |
| ----------------------------- | ----------------------------------------------- | ---------------------------------------------- |
| Single metric, continuous     | Line chart                                      | Connect points, no markers unless <15 points   |
| Single metric, show magnitude | Area chart                                      | Use sparingly, only when area matters          |
| 2-4 metrics, same scale       | Multi-line chart                                | Distinguish with color, not line style         |
| Metrics with different scales | Dual-axis line (use cautiously)                 | Label axes clearly, warn about perception risk |
| Discrete periods (quarters)   | Column chart                                    | Vertical bars imply sequence                   |
| Trend + target                | Line + horizontal reference line                | Annotate the target value                      |
| Year-over-year comparison     | Multi-line, one per year, same x-axis (Jan-Dec) | Color current year prominently                 |

### Part-of-whole

**"What proportion does each part contribute?"**

| Data shape              | Chart                         | Notes                                          |
| ----------------------- | ----------------------------- | ---------------------------------------------- |
| 2-5 categories          | Donut chart                   | Never pie. Always sort largest first clockwise |
| 6+ categories           | Stacked horizontal bar (100%) | Group small categories into "Other"            |
| Over time               | Stacked area or stacked bar   | Show composition shift                         |
| Two levels of hierarchy | Treemap                       | Only if tooling supports it                    |

### Distribution

**"How is the data spread?"**

| Data shape              | Chart                                | Notes                                       |
| ----------------------- | ------------------------------------ | ------------------------------------------- |
| Single variable         | Histogram                            | Choose bin count: sqrt(n) as starting point |
| Compare distributions   | Side-by-side histograms or box plots | Box plots more compact                      |
| Outlier detection       | Box plot                             | Shows median, quartiles, outliers clearly   |
| Frequency of categories | Bar chart, sorted by frequency       | Pareto if showing cumulative %              |

### Relationship

**"Are two variables related?"**

| Data shape                       | Chart                                     | Notes                                     |
| -------------------------------- | ----------------------------------------- | ----------------------------------------- |
| Two numeric variables            | Scatter plot                              | Add trendline if correlation is the story |
| Two numeric + one size dimension | Bubble chart                              | Max 3 dimensions, label bubbles           |
| Two numeric + one category       | Scatter with color-coded groups           | Keep groups ≤6                            |
| Correlation matrix               | Heatmap (conditional formatting in Excel) | Use diverging color scale                 |

### KPIs and Summaries

**"What's the current status at a glance?"**

| Data shape               | Chart                                                   | Notes                        |
| ------------------------ | ------------------------------------------------------- | ---------------------------- |
| Single key number        | Large formatted number in merged cell                   | Add comparison context below |
| Metric vs target         | Bullet chart or progress bar via conditional formatting | Show gap clearly             |
| Status across categories | Conditional formatting (green/yellow/red)               | Use sparingly, 3 levels max  |
| Multiple KPIs            | Dashboard layout with small multiples                   | Consistent sizing            |

## Color Palettes

### Default professional palette (qualitative)

For categorical data where categories have no natural order:

```
4472C4  (blue)
ED7D31  (orange)
A5A5A5  (gray)
FFC000  (gold)
5B9BD5  (light blue)
70AD47  (green)
```

### Sequential palette (single hue, ordered data)

For data with natural low-to-high ordering:

```
DEEBF7 → 9ECAE1 → 4292C6 → 08519C  (blue gradient)
FEE5D9 → FCAE91 → FB6A4A → CB181D  (red gradient)
```

### Diverging palette (positive/negative, above/below average)

For data centered around a meaningful midpoint:

```
D73027 → FC8D59 → FEE08B → D9EF8B → 91CF60 → 1A9850
(red → yellow → green)
```

### Traffic light (use only for status indicators)

```
C00000  (red — critical/below target)
FFC000  (amber — warning/at risk)
70AD47  (green — on track/above target)
```

## Typography in Charts

- Title: Arial 12pt bold
- Axis titles: Arial 10pt
- Axis labels: Arial 9pt
- Data labels: Arial 8pt
- Legend: Arial 9pt
- Avoid rotating axis labels more than 45°. If labels don't fit, switch to
  horizontal bars or abbreviate the labels.
