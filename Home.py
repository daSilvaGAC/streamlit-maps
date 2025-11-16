from pathlib import Path
import json

import pandas as pd
import streamlit as st
import leafmap.foliumap as leafmap

st.set_page_config(layout="wide")

# Customize the sidebar
markdown = """
Aplicação web para visualização e anáise geoespacial de denúncias de poluição sonora.

Powered by Coeficiência Acústica:
<https://www.coeficiencia.com.br>
"""

st.sidebar.title("Sobre")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

# Customize page title
st.title("Aplicação para análise geoespacial de denúncias de poluição sonora")

st.markdown(
    """
    A Aplicação web para visualização e anáise geoespacial de denúncias de poluição sonora. Explore mapas interativos para avaliar denúncias de ruído no espaço e no tempo, integrar camadas ambientais e gerar produtos analíticos para apoiar a tomada de decisões. A aplicação também será utilizada para visualizar e registrar denúncias de poluição sonora.
    Powered by Coeficiência Acústica: <https://www.coeficiencia.com.br>
    """
)

# st.header("Instructions")

# markdown = """
#1. For the [GitHub repository](https://github.com/opengeos/streamlit-map-template) or [use it as a template](https://github.com/opengeos/streamlit-map-template/generate) for your own project.
#2. Customize the sidebar by changing the sidebar text and logo in each Python files.
#3. Find your favorite emoji from https://emojipedia.org.
#4. Add a new app to the `pages/` directory with an emoji in the file name, e.g., `1_🚀_Chart.py`.

#"""

# st.markdown(markdown)

st.set_page_config(layout="wide")

st.title("Clusters de Denúncias de Ruído em Maringá. Dados de 2021 a 2023")


@st.cache_data(show_spinner=False)
def load_geojson() -> pd.DataFrame:
    path = Path(__file__).resolve().parent / "mga_denuncias_20-23.geojson"
    if not path.exists():
        st.error("Arquivo mga_denuncias_20-23.geojson não encontrado.")
        return pd.DataFrame()
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    records = []
    for feature in data.get("features", []):
        props = feature.get("properties", {}) or {}
        coords = feature.get("geometry", {}).get("coordinates", [])
        if len(coords) >= 2:
            props["longitude"] = coords[0]
            props["latitude"] = coords[1]
            records.append(props)
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"]).copy()
    df["DataInclusao"] = pd.to_datetime(
        df.get("DataInclusao_BR", df.get("DataInclusao")),
        format="%H:%M:%S %d-%m-%Y",
        errors="coerce",
        dayfirst=True,
    )
    return df


df = load_geojson()
if df.empty:
    st.warning("Não há dados para exibir no mapa.")
else:
    m = leafmap.Map(center=[-23.415367, -51.931343], zoom=12)
    m.add_points_from_xy(
        df,
        x="longitude",
        y="latitude",
        popup=["Protocolo", "DataInclusao", "Descrição"],
        icon_names=["gear", "map", "leaf", "globe"],
        spin=True,
        add_legend=True,
    )
    m.to_streamlit(height=500)
