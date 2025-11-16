from pathlib import Path
import json
import re

import pandas as pd
import streamlit as st
import leafmap.foliumap as leafmap
import altair as alt

st.set_page_config(page_title="Mapa Interativo de Denúncias", layout="wide")

alt.data_transformers.disable_max_rows()
# Customize the sidebar
markdown = """
Aplicação web para visualização e anáise geoespacial de denúncias de poluição sonora.

Powered by Coeficiência Acústica:
<https://www.coeficiencia.com.br>
"""

st.sidebar.header("Filtros")


def _extract_bairro(value: str) -> str:
    if not value:
        return ""
    value = str(value)
    if "-" in value:
        parts = value.split("-", 1)
        if len(parts) > 1:
            remainder = parts[1].strip()
            if remainder:
                bairro = remainder.split(",", 1)[0].strip()
                if bairro:
                    return bairro
    return ""


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    path = Path(__file__).resolve().parent.parent / "mga_denuncias_20-23.geojson"
    with open(path, encoding="utf-8") as f:
        geojson = json.load(f)

    records = []
    for feature in geojson.get("features", []):
        props = feature.get("properties", {}) or {}
        geometry = feature.get("geometry", {}) or {}
        coords = geometry.get("coordinates", [])
        if not coords or len(coords) < 2:
            continue
        record = props.copy()
        record["longitude"] = coords[0]
        record["latitude"] = coords[1]
        records.append(record)

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
    df = df.dropna(subset=["DataInclusao"]).copy()
    df["data"] = df["DataInclusao"].dt.date
    df["hora"] = df["DataInclusao"].dt.hour
    meses_pt = [
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]
    dias_pt = [
        "Segunda-feira",
        "Terça-feira",
        "Quarta-feira",
        "Quinta-feira",
        "Sexta-feira",
        "Sábado",
        "Domingo",
    ]
    df["mes_pt"] = df["DataInclusao"].dt.month.apply(
        lambda m: meses_pt[int(m) - 1] if pd.notna(m) else None
    )
    df["dia_semana_pt"] = df["DataInclusao"].dt.dayofweek.apply(
        lambda d: dias_pt[int(d)] if pd.notna(d) else None
    )
    df["hora_label"] = df["hora"].apply(
        lambda h: f"{int(h):02d}h" if pd.notna(h) else None
    )

    if "endereco_formatado" not in df.columns:
        df["endereco_formatado"] = ""
    df["endereco_formatado"] = df["endereco_formatado"].fillna("").astype(str)

    if "bairro_formatado" not in df.columns:
        df["bairro_formatado"] = df["endereco_formatado"].apply(_extract_bairro)
    df["bairro_formatado"] = (
        df["bairro_formatado"]
        .fillna(df.get("Bairro"))
        .fillna("")
        .astype(str)
    )
    return df



df = load_data()

if df.empty:
    st.warning("Nenhuma denúncia encontrada no arquivo GeoJSON fornecido.")
    st.stop()

bairro_choices = sorted(
    {valor for valor in df.get("bairro_formatado", pd.Series(dtype="object")) if valor}
)

min_date = df["data"].min()
max_date = df["data"].max()

date_range = st.sidebar.date_input(
    "Intervalo de datas",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
    format="DD/MM/YYYY",
)
if isinstance(date_range, tuple):
    start_date, end_date = date_range
else:
    start_date = date_range
    end_date = date_range

night_mode = st.sidebar.checkbox(
    "Período noturno (20h às 8h)", value=False, help="Seleciona automaticamente o período entre 20:00 e 08:00."
)
if night_mode:
    hour_range = None  # indicador de período especial
else:
    hour_range = st.sidebar.slider(
        "Horário (hora do dia)",
        0,
        23,
        (0, 23),
        help="Use o controle deslizante para definir um intervalo contínuo dentro do mesmo dia.",
    )

search_address = st.sidebar.text_input(
    "Buscar endereço",
    placeholder="Ex.: Avenida Brasil",
)

search_description = st.sidebar.text_input(
    "Buscar descrição",
    placeholder="Ex.: som alto",
)

search_bairro = st.sidebar.text_input(
    "Buscar bairro",
    placeholder="Ex.: Zona 8",
)

st.sidebar.markdown("---")
chart_dimension = st.sidebar.selectbox(
    "Agrupar histogramas por",
    options=[
        "endereco_formatado",
        "hora_label",
        "bairro_formatado",
        "mes_pt",
        "dia_semana_pt",
        "endereco_formatado",
    ],
    index=0,
)

pareto_mode = st.sidebar.radio(
    "Critério do gráfico (Pareto)",
    options=["Top N", "Acumulado (%)"],
    index=1,
)
if pareto_mode == "Top N":
    top_n = st.sidebar.slider("Quantidade (Top N)", 3, 30, 15, 1)
    pct_cutoff = None
else:
    pct_cutoff = st.sidebar.slider("Percentual acumulado (%)", 10, 100, 100, 5)
    top_n = None


filtered = df.copy()
filtered = filtered[
    (filtered["data"] >= start_date)
    & (filtered["data"] <= end_date)
]

if search_address:
    filtered = filtered[
        filtered.get("endereco_formatado", "")
        .astype(str)
        .str.contains(search_address, case=False, na=False)
    ]

pattern = None
if search_description:
    value = search_description.strip()
    if value:
        pattern = rf"\b{re.escape(value)}\b"
if pattern:
    filtered = filtered[
        filtered.get("Descrição", "")
        .astype(str)
        .str.contains(pattern, case=False, na=False, regex=True)
    ]
if search_bairro:
    filtered = filtered[
        filtered.get("bairro_formatado", "")
        .astype(str)
        .str.contains(search_bairro, case=False, na=False)
    ]

if night_mode:
    mask = (filtered["hora"] >= 20) | (filtered["hora"] <= 8)
    filtered = filtered[mask]
elif hour_range is not None:
    start_hour, end_hour = hour_range
    mask = (filtered["hora"] >= start_hour) & (filtered["hora"] <= end_hour)
    filtered = filtered[mask]

filtered = filtered.sort_values("DataInclusao", ascending=False)

st.title("Mapa Interativo de Denúncias de Poluição Sonora em Maringá")

st.caption(
    "Explore as denúncias geocodificadas em Maringá utilizando os filtros na barra lateral."
)


st.sidebar.title("Sobre")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

total_denuncias = len(df)
total_filtrado = len(filtered)
periodo_label = f"{start_date:%d/%m/%Y} - {end_date:%d/%m/%Y}"

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("Denúncias filtradas", f"{total_filtrado:,}")
metric_col2.metric("Denúncias totais", f"{total_denuncias:,}")
metric_col3.metric("Período selecionado", periodo_label)

dimension_col = chart_dimension
chart_df = pd.DataFrame()
chart_ready = False
categories_display: list[str] = []

if not filtered.empty and dimension_col in filtered.columns:
    work_df = filtered.copy()
    work_df[dimension_col] = work_df[dimension_col].fillna("Não informado")
    freq = (
        work_df.groupby(dimension_col, dropna=False)
        .size()
        .reset_index(name="contagem")
        .sort_values("contagem", ascending=False)
        .reset_index(drop=True)
    )
    total_freq = freq["contagem"].sum()
    if total_freq > 0:
        freq["percentual"] = freq["contagem"] / total_freq
        freq["percentual_acumulado"] = freq["percentual"].cumsum()

        if pareto_mode == "Top N":
            limite = min(top_n, len(freq))
            chart_df = freq.head(limite).copy()
        else:
            cutoff = (pct_cutoff or 100) / 100
            chart_df = freq[freq["percentual_acumulado"] <= cutoff].copy()
            if chart_df.empty:
                chart_df = freq.head(1).copy()

        if not chart_df.empty:
            chart_df["percentual"] = chart_df["percentual"] * 100
            chart_df["percentual_acumulado"] = chart_df["percentual_acumulado"] * 100
            categories_display = chart_df[dimension_col].astype(str).tolist()
            chart_ready = True

if not chart_ready:
    categories_display = []

if chart_ready:
    restrict_map = st.checkbox(
        "Mapa filtrado pelas categorias do gráfico",
        value=True,
        help="Quando marcado, o mapa mostra apenas os registros dos grupos exibidos no gráfico Pareto.",
    )
else:
    restrict_map = False

map_data = filtered.copy()
if chart_ready and restrict_map and categories_display:
    map_data = map_data[
        map_data[dimension_col].fillna("Não informado").astype(str).isin(categories_display)
    ]

map_col, table_col = st.columns((3, 2))

with map_col:
    options = list(leafmap.basemaps.keys())
    default_basemap = "OpenTopoMap"
    index = options.index(default_basemap) if default_basemap in options else 0
    basemap = st.selectbox("Mapa base", options, index, key="map_basemap")

    m = leafmap.Map(
        center=[map_data["latitude"].mean(), map_data["longitude"].mean()]
        if not map_data.empty
        else [-23.415367, -51.931343],
        zoom=12.5,
        locate_control=True,
        latlon_control=True,
        draw_export=True,
        minimap_control=True,
    )
    m.add_basemap(basemap)

    if map_data.empty:
        st.info("Ajuste os filtros para visualizar as denúncias no mapa.")
    else:
        popup_fields = [
            "Protocolo",
            "DataInclusao",
            "Descrição",
            "endereco_formatado",
        ]
        available_fields = [col for col in popup_fields if col in map_data.columns]
        if available_fields:
            m.add_points_from_xy(
                data=map_data,
                x="longitude",
                y="latitude",
                popup=available_fields,
                layer_name="Denúncias",
            )
        else:
            m.add_points_from_xy(
                data=map_data,
                x="longitude",
                y="latitude",
                popup=None,
                layer_name="Denúncias",
            )

    m.to_streamlit(height=620)

with table_col:
    st.subheader("Detalhes das denúncias exibidas no mapa")
    if map_data.empty:
        st.info("Sem dados para exibir com os filtros atuais.")
    else:
        display_columns = [
            "Protocolo",
            "DataInclusao",
            "Descrição",
            "endereco_formatado",
            "bairro_formatado",
        ]
        display_columns = [col for col in display_columns if col in map_data.columns]
        if not display_columns:
            st.info("As colunas esperadas não estão disponíveis nos dados.")
        else:
            st.dataframe(
                map_data[display_columns].head(500),
                hide_index=True,
                width="stretch",
            )
            st.caption("Mostrando até 500 registros mais recentes.")

st.markdown("### Histogramas interativos")

if not chart_ready:
    st.info("Sem dados para gerar histogramas com os filtros atuais.")
else:
    chart_render = chart_df.copy()
    chart_render["categoria"] = chart_render[dimension_col].astype(str)

    x_order = chart_render["categoria"].tolist()

    bars = (
        alt.Chart(chart_render)
        .mark_bar(color="#3B82F6")
        .encode(
            x=alt.X("categoria:N", sort=x_order, title=dimension_col),
            y=alt.Y("contagem:Q", title="Denúncias"),
            tooltip=[
                alt.Tooltip("categoria:N", title=dimension_col),
                alt.Tooltip("contagem:Q", title="Quantidade"),
                alt.Tooltip("percentual:Q", title="% Frequência", format=".1f"),
                alt.Tooltip(
                    "percentual_acumulado:Q",
                    title="% Acumulado",
                    format=".1f",
                ),
            ],
        )
    )

    line = (
        alt.Chart(chart_render)
        .mark_line(color="#F97316")
        .encode(
            x=alt.X("categoria:N", sort=x_order, title=dimension_col),
            y=alt.Y(
                "percentual_acumulado:Q",
                axis=alt.Axis(title="% acumulado (%)", format=".1f"),
            ),
            tooltip=[
                alt.Tooltip("categoria:N", title=dimension_col),
                alt.Tooltip(
                    "percentual_acumulado:Q",
                    title="% Acumulado",
                    format=".1f",
                ),
            ],
        )
    )

    points = (
        alt.Chart(chart_render)
        .mark_point(color="#F97316", size=60)
        .encode(
            x=alt.X("categoria:N", sort=x_order, title=dimension_col),
            y=alt.Y("percentual_acumulado:Q"),
            tooltip=[
                alt.Tooltip("categoria:N", title=dimension_col),
                alt.Tooltip(
                    "percentual_acumulado:Q",
                    title="% Acumulado",
                    format=".1f",
                ),
            ],
        )
    )

    histogram = (
        alt.layer(bars, line, points)
        .resolve_scale(y="independent")
        .properties(height=380)
    )

    st.altair_chart(histogram, width="stretch")
    st.caption(
        "O gráfico combina a frequência absoluta (barras) com o percentual acumulado (linha) para análise de Pareto."
    )

    resumo_cols = [
        dimension_col,
        "contagem",
        "percentual",
        "percentual_acumulado",
    ]
    resumo = chart_render[resumo_cols].copy()
    resumo["percentual"] = resumo["percentual"].round(1)
    resumo["percentual_acumulado"] = resumo["percentual_acumulado"].round(1)
    resumo = resumo.rename(
        columns={
            dimension_col: "Categoria",
            "contagem": "Denúncias",
            "percentual": "% Frequência",
            "percentual_acumulado": "% Acumulado",
        }
    )
    st.dataframe(resumo, hide_index=True, width="stretch")
