"""FlameAtlas slider frontend — calls the FastAPI /predict API.

Run:
    python -m src.api.app        # terminal 1 (API on :8000)
    streamlit run frontend/app.py  # terminal 2 (UI on :8501)
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API = os.getenv("FLAMEATLAS_API", "http://localhost:8000")

MATERIALS = {
    "sibal": "SIBAL cotton-fiberglass fabric",
    "pmma": "PMMA (acrylic)",
    "nomex": "Nomex aramid fabric",
}

OUTCOME_STYLE = {
    "spread": dict(name="Spread", symbol="circle", color="#D55E00"),
    "no_spread": dict(name="No spread", symbol="square", color="#0072B2"),
    "marginal_spread": dict(name="Marginal", symbol="diamond", color="#E69F00"),
}

st.set_page_config(page_title="FlameAtlas Explorer", layout="wide")
st.title("FlameAtlas")
st.caption(
    "Microgravity fire-safety explorer · NASA Space Apps 2026 · 'Flame in Freefall'"
)

# ---------- controls ----------
with st.sidebar:
    st.header("Habitat conditions")
    o2 = st.slider("Oxygen (% by volume)", 10.0, 40.0, 21.0, 0.1)
    pressure = st.slider("Pressure (kPa)", 30.0, 110.0, 101.3, 0.1)
    flow = st.slider("Airflow (cm/s)", 0.5, 60.0, 10.0, 0.1)
    material = st.selectbox(
        "Material",
        list(MATERIALS),
        format_func=lambda m: MATERIALS[m],
        index=0,
    )
    st.caption("Change a slider to re-predict.")

# ---------- call API ----------
try:
    resp = requests.post(
        f"{API}/predict",
        json={
            "oxygen_pct": o2,
            "pressure_kpa": pressure,
            "flow_cm_s": flow,
            "material": material,
        },
        timeout=15,
    )
    resp.raise_for_status()
    pred = resp.json()
except requests.RequestException:
    st.error(f"Cannot reach the FlameAtlas API at {API}.")
    st.code("python -m src.api.app", language="bash")
    st.stop()

# ---------- out-of-range guard ----------
if not pred.get("in_training_range"):
    st.error("⚠ Outside the published experimental envelope — no prediction returned.")
    st.warning(pred.get("explanation", ""))
    st.stop()

# ---------- prediction badge + probabilities ----------
status = pred["prediction"]
p = pred["probabilities"]
left, right = st.columns([3, 7])

with left:
    st.subheader("Prediction")
    if status == "spread":
        st.error(
            f"▲ SPREAD · Flame spreads in NASA tests\n\nP(spread) = {p['spread']:.2f}"
        )
    elif status == "marginal_spread":
        st.warning(
            f"◆ MARGINAL SPREAD · Near the burn boundary\n\nP(spread) = {p['spread']:.2f}"
        )
    else:
        st.success(
            f"● NO SPREAD · Self-extinguishes in NASA tests\n\n"
            f"P(no spread) = {p['no_spread']:.2f}"
        )

    st.markdown("**Model**")
    m = pred["model"]
    st.caption(
        f"{m['type']} · trained on {m['n_train']} tests · "
        f"CV accuracy {m['cv_accuracy']:.2f} · "
        f"features: {', '.join(m['features'])}"
    )

    st.markdown("**Class probabilities**")
    prob_df = pd.DataFrame(
        [
            {"regime": "No spread", "p": p["no_spread"]},
            {"regime": "Marginal spread", "p": p["marginal_spread"]},
            {"regime": "Spread", "p": p["spread"]},
        ]
    )
    fig_bar = go.Figure(
        go.Bar(
            x=prob_df["p"],
            y=prob_df["regime"],
            orientation="h",
            marker_color=["#0072B2", "#E69F00", "#D55E00"],
            text=prob_df["p"].round(2),
            textposition="outside",
        )
    )
    fig_bar.update_xaxes(range=[0, 1], title="Probability")
    fig_bar.update_yaxes(title="")
    fig_bar.update_layout(
        height=180, margin=dict(l=10, r=10, t=10, b=10), showlegend=False
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ---------- boundary plot + nearest experiments ----------
with right:
    st.subheader("Flammability boundary (O2 × airflow)")
    try:
        bresp = requests.get(
            f"{API}/boundary",
            params={"material": material, "pressure_kpa": pressure, "n": 160},
            timeout=30,
        )
        bresp.raise_for_status()
        b = bresp.json()
    except requests.RequestException:
        b = None

    if b:
        flows = np.array(b["flows"])
        o2s = np.array(b["o2s"])
        P = np.array(b["P_spread"])
        inside = np.array(b["inside"])

        fig = go.Figure()
        # Spread region (P >= 0.5)
        burn = np.where(np.isnan(P), np.nan, (P >= 0.5).astype(float))
        fig.add_trace(
            go.Heatmap(
                x=flows,
                y=o2s,
                z=burn,
                zmin=0,
                zmax=1,
                showscale=False,
                hoverinfo="skip",
                colorscale=[
                    [0, "rgba(0,0,0,0)"],
                    [1, "rgba(213,94,0,0.12)"],
                ],
                name="Spread region",
            )
        )
        # Untested shading outside envelope
        fig.add_trace(
            go.Heatmap(
                x=flows,
                y=o2s,
                z=np.where(inside, np.nan, 1.0),
                showscale=False,
                hoverinfo="skip",
                colorscale=[
                    [0, "rgba(71,84,103,0.18)"],
                    [1, "rgba(71,84,103,0.18)"],
                ],
                name="Untested",
                hovertemplate="No NASA tests here<extra></extra>",
            )
        )
        # Boundary contour at P = 0.5
        fig.add_trace(
            go.Contour(
                x=flows,
                y=o2s,
                z=P,
                contours=dict(start=0.5, end=0.5, size=1, coloring="lines"),
                line=dict(color="#101828", width=2),
                showscale=False,
                hoverinfo="skip",
                name="Boundary (P = 0.5)",
            )
        )
        # Real experiments overlaid
        exp_df = pd.DataFrame(b["experiments"])
        for outcome, style in OUTCOME_STYLE.items():
            sub = exp_df[exp_df.outcome == outcome]
            if sub.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=sub["x"],
                    y=sub["y"],
                    mode="markers",
                    name=style["name"],
                    marker=dict(
                        symbol=style["symbol"],
                        color=style["color"],
                        size=9,
                        line=dict(width=1, color="white"),
                    ),
                    customdata=sub[["report_id", "source_url"]].fillna(""),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        f"{style['name']}<br>"
                        "O2 %{y}% · flow %{x} cm/s<br>"
                        "<a href='%{customdata[1]}' target='_blank'>NTRS report</a>"
                        "<extra></extra>"
                    ),
                )
            )
        # Current habitat point
        fig.add_trace(
            go.Scatter(
                x=[flow],
                y=[o2],
                mode="markers",
                name="Your habitat",
                marker=dict(
                    symbol="star", size=18, color="#101828",
                    line=dict(width=1.5, color="white"),
                ),
                hovertemplate="Your habitat<br>O2 %{y}% · flow %{x} cm/s<extra></extra>",
            )
        )
        fig.update_xaxes(
            type="log",
            range=[np.log10(flows.min()), np.log10(flows.max())],
            title="Airflow speed (cm/s, log scale)",
        )
        fig.update_yaxes(
            range=[o2s.min(), o2s.max()], dtick=5, title="Oxygen (% by volume)"
        )
        fig.update_layout(
            height=520,
            margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor="white",
            legend=dict(orientation="h", y=-0.12),
        )
        fig.update_xaxes(showgrid=True, gridcolor="#EAECF0")
        fig.update_yaxes(showgrid=True, gridcolor="#EAECF0")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Nearest real experiments**")
    near = pred.get("nearest_experiments", [])
    if near:
        for e in near:
            st.markdown(
                f"- [{e['report_id']}]({e['source_url']}) · {e['outcome']} · "
                f"{e['oxygen_pct']}% O2, {e['flow_cm_s']} cm/s, {e['material']} "
                f"(distance {e['distance']:.2f})"
            )
    else:
        st.caption("No nearest experiments returned.")

with st.expander("About"):
    st.markdown(
        "- Data: curated microgravity combustion tests from NASA PSI / NTRS "
        "(BASS, BASS-II, Saffire, FLEX, SoFIE families).\n"
        "- Model: gradient-boosting classifier with honest stratified "
        "cross-validation.\n"
        "- Guard: conditions outside the training envelope return no prediction "
        "(never extrapolates).\n"
        "- Disclaimer: summarizes published NASA research; does not certify "
        "materials or replace NASA-STD-6001 testing."
    )
