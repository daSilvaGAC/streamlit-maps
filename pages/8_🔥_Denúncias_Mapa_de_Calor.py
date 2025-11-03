from pathlib import Path

import pandas as pd
import streamlit as st
import leafmap.foliumap as leafmap
from folium.plugins import HeatMapWithTime

markdown = """
Powered by: <https://www.coeficiencia.com.br>
"""

st.sidebar.title("About")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

st.title("Mapa de Calor das Denúncias")

with st.expander("See source code"):
    with st.echo():
        data_path = Path(__file__).resolve().parent.parent / "mga_denuncias_20-23.csv"
        df = pd.read_csv(
            data_path,
            encoding="utf-8-sig",
            parse_dates=["DataInclusao"],
        )
        df = df.dropna(subset=["DataInclusao", "latitude", "longitude"]).copy()
        df = df.sort_values("DataInclusao")
        df["latitude"] = df["latitude"].astype(float)
        df["longitude"] = df["longitude"].astype(float)
        df["day"] = df["DataInclusao"].dt.floor("D")

        min_day = df["day"].min()
        max_day = df["day"].max()
        slider = st.slider(
            "Selecione o intervalo de datas",
            min_value=min_day.to_pydatetime(),
            max_value=max_day.to_pydatetime(),
            value=(min_day.to_pydatetime(), max_day.to_pydatetime()),
            format="DD/MM/YYYY",
        )
        start = pd.to_datetime(slider[0]).floor("D")
        end = pd.to_datetime(slider[1]).floor("D")

        df_window = df[(df["day"] >= start) & (df["day"] <= end)].copy()

        heat_data = []
        time_index = []
        accum = []
        if not df_window.empty:
            for day, group in df_window.groupby("day"):
                pts = group[["latitude", "longitude"]].values.tolist()
                accum.extend(pts)
                heat_data.append(accum.copy())
                time_index.append(day.strftime("%Y-%m-%d"))

        if heat_data:
            center_lat = df_window["latitude"].mean()
            center_lon = df_window["longitude"].mean()
        else:
            center_lat = df["latitude"].mean()
            center_lon = df["longitude"].mean()
            st.warning("Nenhuma denúncia encontrada no intervalo selecionado.")

        m = leafmap.Map(
            center=[center_lat, center_lon],
            zoom=12,
            tiles="OpenStreetMap",
        )

        if heat_data:
            HeatMapWithTime(
                heat_data,
                index=time_index,
                auto_play=True,
                max_opacity=0.8,
                radius=15,
                gradient=None,
                use_local_extrema=False,
            ).add_to(m)

m.to_streamlit(height=500)
