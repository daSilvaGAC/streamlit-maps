from pathlib import Path
import json

import pandas as pd
import streamlit as st
import leafmap.foliumap as leafmap

st.set_page_config(layout="wide")

markdown = """
Mapa de calor das denúncias de poluição sonora em Maringá.
"""

st.sidebar.title("Sobre")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

st.title("Heatmap das denúncias em Maringá")

data_path = Path(__file__).resolve().parent.parent / "mga_denuncias_20-23.geojson"
with open(data_path, encoding="utf-8") as f:
    geojson = json.load(f)

records = []
for feature in geojson.get("features", []):
    props = feature.get("properties", {}) or {}
    geom = feature.get("geometry", {}) or {}
    coords = geom.get("coordinates", [])
    if len(coords) < 2:
        continue
    record = props.copy()
    record["longitude"] = coords[0]
    record["latitude"] = coords[1]
    records.append(record)

df = pd.DataFrame(records)
df["DataInclusao"] = pd.to_datetime(
    df.get("DataInclusao_BR", df.get("DataInclusao")),
    format="%H:%M:%S %d-%m-%Y",
    errors="coerce",
    dayfirst=True,
)
df = df.dropna(subset=["latitude", "longitude"]).copy()
if df.empty:
    st.warning("Nenhuma denúncia encontrada.")
    st.stop()
df["value"] = 1

center_lat = df["latitude"].astype(float).mean()
center_lon = df["longitude"].astype(float).mean()
m = leafmap.Map(center=[center_lat, center_lon], zoom=12, tiles="OpenStreetMap")

m.add_heatmap(
    data=df,
    latitude="latitude",
    longitude="longitude",
    value="value",
    name="Mapa de calor",
    radius=20,
)
m.to_streamlit(height=700)
