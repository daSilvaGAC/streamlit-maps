import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import folium
from sklearn.cluster import KMeans, OPTICS
import matplotlib.pyplot as plt

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

st.set_page_config(layout="wide")

markdown = """
Denúncias de Poluição Sonora em Maringá 2020-2023
"""

st.sidebar.title("Sobre")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

st.title("Agrupamento de denúncias com OPTICS + K-Means")


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    data_path = Path(__file__).resolve().parents[1] / "mga_denuncias_20-23.csv"
    df = pd.read_csv(data_path)
    if "Descrição" in df.columns:
        df = df.rename(columns={"Descrição": "Descricao"})
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["DataInclusao"] = pd.to_datetime(
        df.get("DataInclusao_BR", df.get("DataInclusao")),
        format="%H:%M:%S %d-%m-%Y",
        errors="coerce",
        dayfirst=True,
    )
    df = df.dropna(subset=["latitude", "longitude"]).copy()
    df = df[df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)]
    return df


@st.cache_data(show_spinner=False)
def run_optics(points: pd.DataFrame, min_samples: int) -> np.ndarray:
    coords = points[["latitude", "longitude"]].to_numpy()
    coords_rad = np.radians(coords)
    optics = OPTICS(metric="haversine", min_samples=min_samples)
    return optics.fit_predict(coords_rad)


@st.cache_data(show_spinner=False)
def run_kmeans(points: pd.DataFrame, n_clusters: int) -> tuple[np.ndarray, float]:
    coords = points[["latitude", "longitude"]].to_numpy()
    model = KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)
    labels = model.fit_predict(coords)
    return labels, float(model.inertia_)


@st.cache_data(show_spinner=False)
def compute_wcss(points: pd.DataFrame, max_clusters: int) -> list[float]:
    values = points[["latitude", "longitude"]]
    wcss = []
    for k in range(1, max_clusters + 1):
        model = KMeans(n_clusters=k, n_init="auto", random_state=42)
        model.fit(values)
        wcss.append(float(model.inertia_))
    return wcss


df_raw = load_data()

st.sidebar.subheader("Parâmetros de agrupamento")
min_samples = st.sidebar.slider("Tamanho mínimo de cluster (OPTICS)", 5, 100, 15, 1)
cluster_count = st.sidebar.slider("Número de clusters (K-Means)", 2, 10, 4, 1)
sample_limit = st.sidebar.slider("Máximo de pontos exibidos no mapa", 200, 5000, 2000, 100)

st.write(
    f"Total de denúncias geocodificadas: **{len(df_raw):,}** "
    f"(após limpeza de coordenadas)."
)

with st.expander("Visualizar dados brutos"):
    st.dataframe(df_raw.head(1000))

optics_labels = run_optics(df_raw, min_samples)
df_optics = df_raw.copy()
df_optics["optics_cluster"] = optics_labels

df_clean = df_optics[df_optics["optics_cluster"] != -1].copy()

if df_clean.empty:
    st.warning("OPTICS marcou todos os pontos como ruído. Ajuste os parâmetros.")
    st.stop()

medians_by_optics = (
    df_clean.groupby("optics_cluster")[["latitude", "longitude"]]
    .median()
    .reset_index(drop=False)
    .rename(columns={"optics_cluster": "cluster"})
)

st.subheader("Centróides (medianas) encontrados pelo OPTICS")
st.dataframe(medians_by_optics)

if len(df_clean) < cluster_count:
    st.warning(
        "Há menos pontos limpos do que clusters solicitados. "
        "Reduza o número de clusters ou ajuste o parâmetro do OPTICS."
    )
    st.stop()

kmeans_labels, inertia = run_kmeans(df_clean, cluster_count)
df_clean["kmeans_cluster"] = kmeans_labels

st.subheader("Resultados do K-Means")
st.write(
    f"Inércia final (soma das distâncias quadráticas intra-cluster): "
    f"**{inertia:,.2f}**"
)

cluster_counts = (
    df_clean["kmeans_cluster"].value_counts()
    .sort_index()
    .rename_axis("cluster")
    .reset_index(name="quantidade")
)
st.dataframe(cluster_counts)

wcss = compute_wcss(df_clean, max_clusters=10)
ks = list(range(1, len(wcss) + 1))
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(ks, wcss, marker="o")
ax.set_xlabel("Número de clusters")
ax.set_ylabel("WCSS")
ax.set_title("Método do cotovelo (WCSS por K)")
ax.grid(True, linestyle="--", alpha=0.5)
st.pyplot(fig)

df_for_map = df_clean.copy()
df_for_map["cluster_name"] = (
    "Cluster " + (df_for_map["kmeans_cluster"] + 1).astype(str)
)

if len(df_for_map) > sample_limit:
    df_for_map = df_for_map.sample(sample_limit, random_state=42)

center = [
    df_for_map["latitude"].mean(),
    df_for_map["longitude"].mean(),
]

st.subheader("Mapa interativo dos clusters (K-Means após remoção de outliers)")
default_key = os.getenv("MAPTILER_KEY", "UYt1hZNFFGFt10Gokner")
maptiler_key = st.sidebar.text_input(
    "MapTiler API Key",
    value=default_key,
    help="Informe sua chave do MapTiler para carregar o mapa base.",
)

tile_layer = (
    f"https://api.maptiler.com/maps/streets-v2/256/{{z}}/{{x}}/{{y}}.png?key={maptiler_key}"
    if maptiler_key
    else "OpenStreetMap"
)

cluster_palette = [
    ("#3B82F6", "#93C5FD"),
    ("#EF4444", "#FCA5A5"),
    ("#10B981", "#6EE7B7"),
    ("#F97316", "#FDBA74"),
    ("#8B5CF6", "#C4B5FD"),
    ("#EC4899", "#F9A8D4"),
    ("#14B8A6", "#5EEAD4"),
    ("#FACC15", "#FDE68A"),
    ("#6366F1", "#A5B4FC"),
    ("#0EA5E9", "#7DD3FC"),
]

cluster_colors = {}
for idx, cluster_id in enumerate(sorted(df_for_map["kmeans_cluster"].unique())):
    base_idx = idx % len(cluster_palette)
    cluster_colors[cluster_id] = cluster_palette[base_idx]

cluster_map = folium.Map(location=center, zoom_start=12, tiles=None if maptiler_key else tile_layer)

if maptiler_key:
    folium.TileLayer(
        tiles=tile_layer,
        attr="&copy; MapTiler &copy; OpenStreetMap contributors",
        name="MapTiler Streets",
    ).add_to(cluster_map)

for cluster_id, group in df_for_map.groupby("kmeans_cluster"):
    border_color, fill_color = cluster_colors[cluster_id]
    label = f"Cluster {cluster_id + 1}"
    feature_group = folium.FeatureGroup(name=label)
    for _, row in group.iterrows():
        popup_text = (
            f"<b>Cluster:</b> {label}<br>"
            f"<b>Data:</b> {row['DataInclusao'].strftime('%d/%m/%Y %H:%M') if pd.notnull(row['DataInclusao']) else 'n/d'}<br>"
            f"<b>Endereço:</b> {row.get('endereco_completo', '')}"
        )
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=4,
            color=border_color,
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.8,
            weight=1,
            popup=popup_text,
        ).add_to(feature_group)
    feature_group.add_to(cluster_map)

folium.LayerControl(collapsed=False).add_to(cluster_map)

components.html(cluster_map._repr_html_(), height=600, scrolling=False)
