import os
import json
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

st.title("Agrupamento de denúncias com OPTICS + K-Means")


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    data_path = Path(__file__).resolve().parents[1] / "mga_denuncias_20-23.geojson"
    with open(data_path, encoding="utf-8") as f:
        geojson = json.load(f)

    records = []
    for feature in geojson.get("features", []):
        properties = feature.get("properties", {}) or {}
        geometry = feature.get("geometry", {}) or {}
        coordinates = geometry.get("coordinates", [])
        if not coordinates or len(coordinates) < 2:
            continue
        record = properties.copy()
        record["longitude"] = coordinates[0]
        record["latitude"] = coordinates[1]
        records.append(record)

    df = pd.DataFrame(records)
    if df.empty:
        return df

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

if df_raw.empty:
    st.warning("Nenhum dado válido foi encontrado no arquivo GeoJSON.")
    st.stop()

st.sidebar.subheader("Parâmetros de agrupamento")
st.sidebar.markdown(
    """
    **Como ajustar os agrupamentos**

    - `Tamanho mínimo de cluster (OPTICS)`: aumente para ignorar ruídos isolados.
    - `Número de clusters (K-Means)`: teste diferentes agrupamentos esperados.
    - `Máximo de pontos`: reduz a amostra exibida no mapa para manter fluidez.
    """
)
min_samples = st.sidebar.slider("Tamanho mínimo de cluster (OPTICS)", 5, 100, 15, 1)
cluster_count = st.sidebar.slider("Número de clusters (K-Means)", 2, 10, 4, 1)
sample_limit = st.sidebar.slider("Máximo de pontos exibidos no mapa", 200, 5000, 2000, 100)

optics_labels = run_optics(df_raw, min_samples)
df_optics = df_raw.copy()
df_optics["optics_cluster"] = optics_labels

df_clean = df_optics[df_optics["optics_cluster"] != -1].copy()

if df_clean.empty:
    st.warning("OPTICS marcou todos os pontos como ruído. Ajuste os parâmetros.")
    st.stop()

optics_cluster_count = df_clean["optics_cluster"].nunique()
highlight_optics = st.sidebar.slider(
    "Centróides OPTICS destacados",
    1,
    min(10, optics_cluster_count if optics_cluster_count > 0 else 1),
    min(5, optics_cluster_count if optics_cluster_count > 0 else 1),
    1,
)

medians_by_optics = (
    df_clean.groupby("optics_cluster")
    .agg(
        latitude=("latitude", "median"),
        longitude=("longitude", "median"),
        quantidade=("latitude", "size"),
    )
    .reset_index(drop=False)
    .rename(columns={"optics_cluster": "cluster"})
)

if len(df_clean) < cluster_count:
    st.warning(
        "Há menos pontos limpos do que clusters solicitados. "
        "Reduza o número de clusters ou ajuste o parâmetro do OPTICS."
    )
    st.stop()

kmeans_labels, inertia = run_kmeans(df_clean, cluster_count)
df_clean["kmeans_cluster"] = kmeans_labels

optics_to_kmeans = (
    df_clean.groupby("optics_cluster")["kmeans_cluster"]
    .agg(lambda s: s.value_counts().idxmax())
)

cluster_counts = (
    df_clean["kmeans_cluster"].value_counts()
    .sort_index()
    .rename_axis("cluster")
    .reset_index(name="quantidade")
)
cluster_centroids = (
    df_clean.groupby("kmeans_cluster")
    .agg(
        latitude=("latitude", "mean"),
        longitude=("longitude", "mean"),
        quantidade=("latitude", "size"),
    )
    .reset_index(drop=False)
)

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

default_key = os.getenv("MAPTILER_KEY", "UYt1hZNFFGFt10Gokner")
maptiler_key = default_key
st.sidebar.caption("Mapa base carregado com a chave padrão configurada para o MapTiler.")

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
for idx, cluster_id in enumerate(sorted(df_clean["kmeans_cluster"].unique())):
    base_idx = idx % len(cluster_palette)
    cluster_colors[cluster_id] = cluster_palette[base_idx]

centroids_display = medians_by_optics.sort_values("quantidade", ascending=False).reset_index(drop=True)
centroids_display["cluster_kmeans"] = centroids_display["cluster"].map(optics_to_kmeans).fillna(-1).astype(int)
centroids_display["cor_legenda"] = centroids_display["cluster_kmeans"].map(
    lambda c: cluster_colors.get(c, ("#1F2937", "#9CA3AF"))[1]
)

st.markdown("### Mapa interativo dos agrupamentos")
st.markdown(
    "Visualize a distribuição espacial dos clusters em Maringá. "
    "O mapa usa OPTICS para remover ruídos antes de aplicar o K-Means, "
    "destacando em cores distintas as áreas de maior concentração de denúncias. "
    "Os centróides OPTICS mais relevantes (configurados na barra lateral) aparecem maiores."
)

cluster_map = folium.Map(location=center, zoom_start=12.5, tiles=None if maptiler_key else tile_layer)

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

max_optics_count = centroids_display["quantidade"].max()
min_optics_count = centroids_display["quantidade"].min()


def scale_radius(count: int, highlight: bool) -> float:
    if max_optics_count == min_optics_count:
        return 14.0 if highlight else 8.0
    norm = (count - min_optics_count) / (max_optics_count - min_optics_count)
    if highlight:
        return 12.0 + norm * 8.0
    return 5.0 + norm * 4.0


centroid_layer = folium.FeatureGroup(name="Centróides (OPTICS)", show=True)
for idx, row in centroids_display.iterrows():
    highlight = idx < highlight_optics
    border_color, fill_color = cluster_colors.get(row["cluster_kmeans"], ("#1F2937", "#9CA3AF"))
    popup = (
        f"<b>Cluster:</b> {row['cluster'] + 1}<br>"
        f"<b>Cluster K-Means predominante:</b> {row['cluster_kmeans'] + 1 if row['cluster_kmeans'] >= 0 else 'n/d'}<br>"
        f"<b>Denúncias no cluster:</b> {int(row['quantidade']):,}<br>"
        f"<b>Latitude:</b> {row['latitude']:.6f}<br>"
        f"<b>Longitude:</b> {row['longitude']:.6f}"
    )
    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=scale_radius(int(row["quantidade"]), highlight),
        color=border_color,
        weight=3 if highlight else 1,
        fill=True,
        fill_color=fill_color,
        fill_opacity=0.95 if highlight else 0.75,
        popup=popup,
    ).add_to(centroid_layer)
centroid_layer.add_to(cluster_map)

kmeans_centroid_layer = folium.FeatureGroup(name="Centróides (K-Means)", show=True)
for _, row in cluster_centroids.iterrows():
    cluster_id = int(row["kmeans_cluster"])
    border_color, fill_color = cluster_colors.get(cluster_id, ("#1F2937", "#9CA3AF"))
    popup = (
        f"<b>Cluster K-Means:</b> {cluster_id + 1}<br>"
        f"<b>Denúncias no cluster:</b> {int(row['quantidade']):,}<br>"
        f"<b>Latitude:</b> {row['latitude']:.6f}<br>"
        f"<b>Longitude:</b> {row['longitude']:.6f}"
    )
    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=10,
        color=border_color,
        weight=4,
        fill=True,
        fill_color=fill_color,
        fill_opacity=0.6,
        popup=popup,
    ).add_to(kmeans_centroid_layer)
kmeans_centroid_layer.add_to(cluster_map)

folium.LayerControl(collapsed=False).add_to(cluster_map)

components.html(cluster_map._repr_html_(), height=600, scrolling=False)

st.markdown("### Indicadores gerais")
st.markdown(
    "Use estes indicadores para conferir o tamanho da base e o volume de pontos "
    "que passaram pelos filtros de qualidade antes do agrupamento."
)
col_total, col_clean = st.columns(2)
col_total.metric("Denúncias geocodificadas", f"{len(df_raw):,}")
col_clean.metric("Pontos após OPTICS", f"{len(df_clean):,}")

## with st.expander("Visualizar dados brutos"):
    ## st.dataframe(df_raw.head(1000))

st.markdown("### Centróides identificados pelo OPTICS")
st.markdown(
    "Cada centróide representa a mediana de latitude/longitude de um cluster detectado pelo OPTICS. "
    "A coluna de cor indica como o agrupamento aparece no mapa e serve de legenda."
)
centroids_table = centroids_display.copy()
centroids_table["Cluster OPTICS"] = centroids_table["cluster"] + 1
centroids_table["Cluster K-Means predominante"] = centroids_table["cluster_kmeans"]
centroids_table.loc[centroids_table["Cluster K-Means predominante"] >= 0, "Cluster K-Means predominante"] += 1
centroids_table.loc[centroids_table["Cluster K-Means predominante"] < 0, "Cluster K-Means predominante"] = None
centroids_table = centroids_table.rename(
    columns={
        "quantidade": "Total de denúncias (OPTICS)",
        "cor_legenda": "Cor (legenda)",
        "latitude": "Latitude",
        "longitude": "Longitude",
    }
)[
    [
        "Cluster OPTICS",
        "Cluster K-Means predominante",
        "Total de denúncias (OPTICS)",
        "Latitude",
        "Longitude",
        "Cor (legenda)",
    ]
]
st.dataframe(centroids_table, use_container_width=True)

st.markdown("### Centróides identificados pelo K-Means")
st.markdown(
    "Cada centróide do K-Means representa o centro geométrico de um agrupamento "
    "após a remoção de ruídos, usando as cores do próprio cluster."
)
kmeans_table = cluster_centroids.copy()
kmeans_table["Cluster K-Means"] = kmeans_table["kmeans_cluster"] + 1
kmeans_table = kmeans_table.rename(
    columns={
        "quantidade": "Total de denúncias (K-Means)",
        "latitude": "Latitude",
        "longitude": "Longitude",
    }
)[
    [
        "Cluster K-Means",
        "Total de denúncias (K-Means)",
        "Latitude",
        "Longitude",
    ]
]
st.dataframe(kmeans_table, use_container_width=True)

st.markdown("### O que é o K-Means?")
st.markdown(
    "K-Means é um algoritmo de agrupamento que separa os pontos em grupos ao minimizar a distância "
    "entre amostras e seus centróides. Após remover ruídos com OPTICS, aplicamos o K-Means para reforçar "
    "padrões de concentração das denúncias."
)

st.markdown("### Resultados do K-Means")
st.markdown(
    "A tabela abaixo mostra quantos registros ficaram em cada cluster final. "
    "Use os controles na barra lateral para testar novos cenários."
)
st.write(
    f"Inércia final (soma das distâncias quadráticas intra-cluster): "
    f"**{inertia:,.2f}**"
)
st.dataframe(cluster_counts, use_container_width=True)

st.markdown("### Como interpretar os resultados")
st.markdown(
    """
    - Clusters maiores podem indicar áreas com maior reincidência de denúncias.
    - Uma inércia menor sugere grupos mais compactos; valores altos podem apontar dispersão.
    - Reajuste os parâmetros para verificar se os agrupamentos permanecem estáveis.
    """
)

wcss = compute_wcss(df_clean, max_clusters=10)
ks = list(range(1, len(wcss) + 1))
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(ks, wcss, marker="o")
ax.set_xlabel("Número de clusters")
ax.set_ylabel("WCSS")
ax.set_title("Método do cotovelo (WCSS por K)")
ax.grid(True, linestyle="--", alpha=0.5)
st.markdown(
    "O gráfico do método do cotovelo ajuda a encontrar um número adequado de clusters: "
    "procure pelo ponto onde a queda de WCSS começa a se estabilizar."
)
st.pyplot(fig)
