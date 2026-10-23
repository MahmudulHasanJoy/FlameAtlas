"""FlameAtlas practice prototype: the Flammability Map only.

Run from this folder:  streamlit run app.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core

DATA = Path(__file__).parent / "data" / "sibal_bass_table71.csv"
SOURCE_URLS = {"NTRS-20210011385": "https://ntrs.nasa.gov/citations/20210011385"}
SOURCE_TITLES = {"NTRS-20210011385": "Burning and Suppression of Solids-II (BASS-II) Summary Report, NASA/TM-20210011385"}

MATERIALS = {
    "sibal": "SIBAL cotton-fiberglass fabric",
    "pmma_slab": "PMMA (acrylic) slab",
    "nomex": "Nomex aramid fabric",
}

PRESETS = {
    "ISS cabin (101.3 kPa, 21% O2)": (21.0, 101.3),
    "Exploration 10.2 psia (70.3 kPa, 26.5% O2)": (26.5, 70.3),
    "Exploration 8.2 psia (56.5 kPa, 34% O2)": (34.0, 56.5),
}

OUTCOME_STYLE = {  # docs/04-DRD.md section 4.2
    "burned": dict(name="Burned", symbol="circle", color="#D55E00"),
    "self_extinguished": dict(name="Self-extinguished", symbol="square", color="#0072B2"),
    "no_ignition": dict(name="No ignition", symbol="x", color="#595959"),
}


@st.cache_data
def load_records() -> pd.DataFrame:
    df = pd.read_csv(DATA, dtype={"exclude_from_fit": str, "pressure_reported": str})
    df["exclude_from_fit"] = df["exclude_from_fit"].str.lower() == "true"
    return df


@st.cache_resource
def boundary_for(material_id: str, variant: str, direction: str):
    df = load_records()
    group = df[(df.material_id == material_id) & (df.sample_variant == variant) & (df.flow_direction == direction)]
    return core.fit_boundary(group)


def status_box(status: str, p: float | None) -> None:
    if status == core.DANGER:
        st.error(f"**▲ DANGER · Burns in NASA tests**  \nBurn probability {p:.2f} at these conditions.")
    elif status == core.MARGINAL:
        st.warning(
            f"**◆ MARGINAL · Near the burn boundary**  \nBurn probability {p:.2f}. "
            "Small changes in oxygen or airflow could let it burn."
        )
    elif status == core.SELF_EXTINGUISHES:
        st.success(
            f"**● SELF-EXTINGUISHES · Went out in NASA tests**  \nBurn probability {p:.2f}. "
            "This is not a safety certification."
        )
    elif status == core.UNTESTED:
        st.info("**? UNTESTED · No NASA tests near these conditions**  \nNearest tests are listed below. Do not assume this is safe.")
    else:
        st.info("**? NOT ENOUGH DATA · Showing nearest tests only**  \nToo few tests to estimate a boundary for this material.")


def build_figure(records: pd.DataFrame, model, o2: float, flow: float) -> go.Figure:
    fig = go.Figure()
    if model is not None:
        flows, o2s, P, inside = core.boundary_grid(model)
        burn = np.where(np.isnan(P), np.nan, (P >= 0.5).astype(float))
        fig.add_trace(go.Heatmap(x=flows, y=o2s, z=burn, zmin=0, zmax=1, showscale=False, hoverinfo="skip",
                                 colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(213,94,0,0.12)"]], name="Burn region"))
        fig.add_trace(go.Heatmap(x=flows, y=o2s, z=np.where(inside, np.nan, 1.0), showscale=False,
                                 colorscale=[[0, "rgba(71,84,103,0.18)"], [1, "rgba(71,84,103,0.18)"]],
                                 hovertemplate="No NASA tests here<extra></extra>", name="Untested"))
        fig.add_trace(go.Contour(x=flows, y=o2s, z=P, contours=dict(start=0.5, end=0.5, size=1, coloring="lines"),
                                 line=dict(color="#101828", width=2), colorscale=[[0, "#101828"], [1, "#101828"]],
                                 showscale=False, hoverinfo="skip",
                                 name="Burn boundary (P = 0.5)", showlegend=True))
    for outcome, style in OUTCOME_STYLE.items():
        for excluded in (False, True):
            sub = records[(records.outcome == outcome) & (records.exclude_from_fit == excluded)]
            if sub.empty:
                continue
            symbol = style["symbol"] + ("-open" if excluded else "")
            fig.add_trace(go.Scatter(
                x=np.maximum(sub.flow_cm_s, core.MIN_FLOW), y=sub.o2_pct, mode="markers",
                name=style["name"] + (" (not used in fit)" if excluded else ""),
                marker=dict(symbol=symbol, color=style["color"], size=11, line=dict(width=1, color="white")),
                customdata=sub[["record_id", "test_label", "experiment", "sample_variant", "exclude_reason"]].fillna(""),
                hovertemplate=("<b>%{customdata[1]}</b> (%{customdata[2]})<br>" + style["name"] +
                               "<br>O2 %{y}% · flow %{x} cm/s<br>%{customdata[3]}<br>%{customdata[4]}"
                               "<br>Click for evidence<extra></extra>"),
            ))
    fig.add_trace(go.Scatter(x=[flow], y=[o2], mode="markers", name="Your habitat",
                             marker=dict(symbol="star", size=20, color="#101828", line=dict(width=1.5, color="white")),
                             hovertemplate="Your habitat<br>O2 %{y}% · flow %{x} cm/s<extra></extra>"))
    fig.update_xaxes(type="log", range=[np.log10(core.MIN_FLOW), np.log10(60)],
                     tickvals=[0.5, 1, 2, 5, 10, 20, 50], title="Airflow speed past the material (cm/s, log scale)")
    fig.update_yaxes(range=[10, 40], dtick=5, title="Oxygen (% by volume)")
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white",
                      legend=dict(orientation="h", y=-0.18), clickmode="event+select")
    fig.update_xaxes(showgrid=True, gridcolor="#EAECF0")
    fig.update_yaxes(showgrid=True, gridcolor="#EAECF0")
    return fig


def evidence(record: pd.Series) -> None:
    with st.container(border=True):
        st.markdown(f"**{record.experiment} · {record.source_id} · {record.source_locator}**")
        st.caption("Transcribed from the source; awaiting verification by the Data and Science Lead.")
        rows = {
            "Material": f"{MATERIALS[record.material_id]} ({record.sample_variant})",
            "Conditions": f"{record.o2_pct}% O2 · {record.flow_cm_s} cm/s {record.flow_direction} flow · "
                          f"{record.pressure_kpa} kPa (ISS nominal, not stated in source) · microgravity",
            "Outcome": record.outcome.replace("_", " ") + (f" ({record.extinction_mode})" if isinstance(record.extinction_mode, str) else ""),
            "Notes": record.notes,
            "Source": f"[{SOURCE_TITLES[record.source_id]}]({SOURCE_URLS[record.source_id]})",
        }
        for label, value in rows.items():
            left, right = st.columns([1, 4])
            left.markdown(f"**{label}**")
            right.markdown(value)


st.set_page_config(page_title="FlameAtlas prototype", layout="wide")
st.title("FlameAtlas")
st.caption("Know what burns before you fly.")
st.info(
    "Practice prototype for NASA Space Apps 2026. It shows one real NASA data set: 48 test results transcribed "
    "from Table 7.1 of the BASS-II Summary Report (NTRS 20210011385). These values have not yet been hand-checked "
    "by the team. Evidence cards and Ask FlameAtlas are planned for the hackathon build."
)

records_all = load_records()
left, right = st.columns([3, 7], gap="large")

with left:
    material = st.selectbox("Material", list(MATERIALS), format_func=MATERIALS.get)
    mat_records = records_all[records_all.material_id == material]
    variants = sorted(mat_records.sample_variant.unique(), reverse=True)
    variant = st.selectbox("Sample", variants) if variants else None
    preset = st.selectbox("Habitat preset", list(PRESETS))
    preset_o2, preset_p = PRESETS[preset]
    o2 = st.slider("Oxygen (% by volume)", 10.0, 40.0, preset_o2, 0.1, key=f"o2-{preset}")
    flow = st.slider("Airflow (cm/s)", 0.5, 60.0, 10.0, 0.1, key=f"flow-{preset}")
    pressure = st.number_input("Pressure (kPa)", 30.0, 110.0, preset_p, 0.1, key=f"p-{preset}")
    direction = st.radio("Flow direction", ["concurrent", "opposed"], horizontal=True,
                         help="Concurrent: air moves the same way the flame spreads. Opposed: air moves against it.")

with right:
    if mat_records.empty:
        st.info(f"No NASA tests for {MATERIALS[material]} are loaded in this prototype yet. This is a research gap "
                "until the hackathon data set is built.")
        st.stop()
    group = mat_records[(mat_records.sample_variant == variant) & (mat_records.flow_direction == direction)]
    if group.empty:
        other = "opposed" if direction == "concurrent" else "concurrent"
        st.info(f"NASA tested this sample only in {other} flow in this data set. Switch flow direction to see it.")
        st.stop()

    model = boundary_for(material, variant, direction)
    status, p = core.classify_habitat(model, o2, flow)
    status_box(status, p)
    tested_p = core.pressure_mismatch(group, pressure)
    if tested_p is not None:
        st.warning(f"NASA tested this material at about {tested_p:.0f} kPa. Your habitat is at {pressure:.0f} kPa. "
                   "Lower pressure and higher oxygen can change flammability.")
    st.caption("Map shows microgravity tests only.")
    if model is None:
        st.caption("Not enough tests to draw a boundary: " + core.sufficiency_problem(core.fit_rows(group)) + ".")

    event = st.plotly_chart(build_figure(group, model, o2, flow), on_select="rerun", selection_mode="points",
                            key="map", width="stretch")

    st.markdown("**Nearest NASA tests**")
    near = core.nearest_tests(group, o2, flow, pressure)
    st.dataframe(
        near[["test_label", "experiment", "flow_cm_s", "o2_pct", "outcome", "distance"]].rename(columns={
            "test_label": "Test", "experiment": "Experiment", "flow_cm_s": "Flow (cm/s)", "o2_pct": "O2 (%)",
            "outcome": "Outcome", "distance": "Distance"}).round({"Distance": 2}),
        hide_index=True, width="stretch")

    picked = [pt for pt in (event.selection.points if event else []) if pt.get("customdata")]
    if picked:
        rid = picked[0]["customdata"][0]
        evidence(group[group.record_id == rid].iloc[0])
    else:
        st.caption("Click a dot on the map to see where it comes from.")

with st.expander("About this prototype"):
    st.markdown(
        f"- **Data:** {len(records_all)} test results, 1 material, 1 NASA source (BASS and BASS-II on the ISS, "
        "flat SIBAL fabric in concurrent flow).\n"
        "- **Method:** each row of the source table is turned into one record per stated airflow, following "
        "`docs/05-data-spec.md`. The boundary is a logistic regression on oxygen and log airflow, drawn only "
        "inside the range of real tests (`docs/06-ai-rag-spec.md`).\n"
        "- **Disclaimer:** FlameAtlas summarizes published NASA research for exploration and education. It does "
        "not certify materials and does not replace NASA-STD-6001 testing.\n"
        "- **Credits:** NASA Technical Reports Server (NTRS), NASA Physical Sciences Informatics (PSI), "
        "NASA Space Apps Challenge 2026."
    )
