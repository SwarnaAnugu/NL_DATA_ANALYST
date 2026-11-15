"""Turns a chart spec from chart_selector into an interactive Plotly figure.

Kept separate from the Streamlit app so it can be unit-tested without a UI."""
import pandas as pd
import plotly.express as px

HORIZONTAL_BAR_THRESHOLD = 8   # many categories -> horizontal bars keep labels readable
MAX_BARS = 20                  # more than this is unreadable; show the largest and say so


def _pretty(col: str) -> str:
    return col.replace("_", " ").strip().capitalize()


def build_figure(chart: dict, columns: list, rows: list):
    """Return a Plotly figure, or None if no chart should be drawn."""
    if chart.get("chart_type") not in ("bar", "line") or not rows:
        return None

    df = pd.DataFrame(rows, columns=columns)
    x, y, color = chart["x"], chart["y"], chart.get("color")
    is_line = chart["chart_type"] == "line"
    note = None

    df[x] = df[x].fillna("(none)").astype(str)             # NULL labels can't be plotted
    if color:
        df[color] = df[color].fillna("(none)").astype(str)
    if isinstance(y, list):                                # several measures -> long format, one series each
        df = df.melt(id_vars=[x], value_vars=y, var_name="measure", value_name="value")
        df["measure"] = df["measure"].map(_pretty)
        y, color = "value", "measure"

    labels = {x: _pretty(x), y: _pretty(y) if y != "value" else "Value"}
    if color and color != "measure":
        labels[color] = _pretty(color)
    palette = px.colors.qualitative.Safe

    if is_line:
        fig = px.line(df.sort_values(x), x=x, y=y, color=color, markers=True, labels=labels,
                      color_discrete_sequence=palette if color else ["#2563eb"])
    else:
        n_cats = df[x].nunique()
        if not color and len(df) > MAX_BARS:
            note = f"Top {MAX_BARS} of {len(df)} rows by {_pretty(y).lower()} (full data in the table below)"
            df = df.nlargest(MAX_BARS, y)
            n_cats = len(df)
        horizontal = n_cats > HORIZONTAL_BAR_THRESHOLD and not color
        kwargs = dict(color=color, barmode="group", labels=labels,
                      color_discrete_sequence=palette if color else ["#2563eb"])
        fig = (px.bar(df.sort_values(y), x=y, y=x, orientation="h", **kwargs) if horizontal
               else px.bar(df, x=x, y=y, **kwargs))

    n_bars = df[x].nunique()
    height = 60 + 26 * n_bars if (not is_line and not color and n_bars > HORIZONTAL_BAR_THRESHOLD) else 380
    fig.update_layout(margin=dict(l=10, r=10, t=30 if note else 10, b=10), height=height,
                      plot_bgcolor="rgba(0,0,0,0)", legend_title_text="",
                      title=dict(text=note, font=dict(size=13), x=0) if note else None)
    return fig
