from pathlib import Path
import json

import pandas as pd
import streamlit as st
import leafmap.foliumap as leafmap
import altair as alt

st.set_page_config(page_title="Mapa Interativo de Denúncias", layout="wide")

alt.data_transformers.disable_max_rows()

markdown = """
A Streamlit map template
<https://github.com/opengeos/streamlit-map-template>
"""

st.sidebar.title("About")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

st.sidebar.markdown("---")
st.sidebar.header("Filtros")


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
    df["data"] = df["DataInclusao"].dt.date
    df["hora"] = df["DataInclusao"].dt.hour
    return df


df = load_data()

if df.empty:
    st.warning("Nenhuma denúncia encontrada no arquivo GeoJSON fornecido.")
    st.stop()

min_date = df["data"].min()
max_date = df["data"].max()

date_range = st.sidebar.date_input(
    "Intervalo de datas",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
if isinstance(date_range, tuple):
    start_date, end_date = date_range
else:
    start_date = date_range
    end_date = date_range

hour_range = st.sidebar.slider("Horário (hora do dia)", 0, 23, (0, 23))

search_address = st.sidebar.text_input(
    "Buscar endereço",
    placeholder="Ex.: Avenida Brasil",
)

assuntos = sorted(df["Assunto"].dropna().unique().tolist())
selected_assuntos = st.sidebar.multiselect(
    "Assunto",
    assuntos,
)

bairros = sorted(df["Bairro"].dropna().unique().tolist())
selected_bairros = st.sidebar.multiselect("Bairro", bairros)

origens = sorted(df["Origem"].dropna().unique().tolist())
selected_origens = st.sidebar.multiselect("Origem", origens)

zonas = sorted(df["Zona"].dropna().unique().tolist())
selected_zonas = st.sidebar.multiselect("Zona", zonas)

st.sidebar.markdown("---")
chart_dimension = st.sidebar.selectbox(
    "Agrupar histogramas por",
    options=["Assunto", "Bairro", "Origem", "Zona", "Setor"],
    index=0,
)

filtered = df.copy()
filtered = filtered[
    (filtered["data"] >= start_date)
    & (filtered["data"] <= end_date)
    & (filtered["hora"] >= hour_range[0])
    & (filtered["hora"] <= hour_range[1])
]

if search_address:
    filtered = filtered[
        filtered.get("endereco_formatado", "")
        .astype(str)
        .str.contains(search_address, case=False, na=False)
    ]

if selected_assuntos:
    filtered = filtered[filtered["Assunto"].isin(selected_assuntos)]
if selected_bairros:
    filtered = filtered[filtered["Bairro"].isin(selected_bairros)]
if selected_origens:
    filtered = filtered[filtered["Origem"].isin(selected_origens)]
if selected_zonas:
    filtered = filtered[filtered["Zona"].isin(selected_zonas)]

filtered = filtered.sort_values("DataInclusao", ascending=False)

st.title("Interactive Map")

st.caption(
    "Explore as denúncias geocodificadas em Maringá utilizando os filtros na barra lateral."
)

total_denuncias = len(df)
total_filtrado = len(filtered)
periodo_label = f"{start_date:%d/%m/%Y} - {end_date:%d/%m/%Y}"

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("Denúncias filtradas", f"{total_filtrado:,}")
metric_col2.metric("Denúncias totais", f"{total_denuncias:,}")
metric_col3.metric("Período selecionado", periodo_label)

map_col, table_col = st.columns((3, 2))

with map_col:
    options = list(leafmap.basemaps.keys())
    default_basemap = "OpenTopoMap"
    index = options.index(default_basemap) if default_basemap in options else 0
    basemap = st.selectbox("Mapa base", options, index, key="map_basemap")

    m = leafmap.Map(
        center=[filtered["latitude"].mean(), filtered["longitude"].mean()]
        if not filtered.empty
        else [-23.415367, -51.931343],
        zoom=12.5,
        locate_control=True,
        latlon_control=True,
        draw_export=True,
        minimap_control=True,
    )
    m.add_basemap(basemap)

    if filtered.empty:
        st.info("Ajuste os filtros para visualizar as denúncias no mapa.")
    else:
        popup_fields = [
            "Protocolo",
            "DataInclusao",
            "Assunto",
            "Origem",
            "endereco_formatado",
        ]
        m.add_points_from_xy(
            data=filtered,
            x="longitude",
            y="latitude",
            popup=popup_fields,
            layer_name="Denúncias",
        )

    m.to_streamlit(height=620)

with table_col:
    st.subheader("Detalhes das denúncias filtradas")
    if filtered.empty:
        st.info("Sem dados para exibir com os filtros atuais.")
    else:
        display_columns = [
            "Protocolo",
            "DataInclusao",
            "Assunto",
            "Bairro",
            "Origem",
            "endereco_formatado",
        ]
        display_columns = [col for col in display_columns if col in filtered.columns]
        if not display_columns:
            st.info("As colunas esperadas não estão disponíveis nos dados.")
        else:
            st.dataframe(
                filtered[display_columns].head(500),
                use_container_width=True,
                hide_index=True,
            )
            st.caption("Mostrando até 500 registros mais recentes.")

st.markdown("### Histogramas interativos")

if filtered.empty:
    st.info("Sem dados para gerar histogramas. Ajuste os filtros.")
else:
    dimension_col = chart_dimension
    if dimension_col not in filtered.columns:
        st.warning("A coluna selecionada não está disponível nos dados filtrados.")
    else:
        chart_df = filtered.copy()
        chart_df[dimension_col] = chart_df[dimension_col].fillna("Não informado")
        chart_df = (
            chart_df.groupby(dimension_col, dropna=False)
            .size()
            .reset_index(name="contagem")
            .sort_values("contagem", ascending=False)
        )
        chart_df["percentual"] = chart_df["contagem"] / chart_df["contagem"].sum()
        chart_df["percentual_acumulado"] = chart_df["percentual"].cumsum()

        if chart_df.empty:
            st.info("A coluna selecionada não possui dados para os filtros atuais.")
        else:
            chart_df["percentual"] = chart_df["percentual"] * 100
            chart_df["percentual_acumulado"] = chart_df["percentual_acumulado"] * 100

            x_encoding = alt.X(
                f"{dimension_col}:N",
                sort=chart_df[dimension_col].tolist(),
                title=dimension_col,
            )

            bars = (
                alt.Chart(chart_df)
                .mark_bar(color="#3B82F6")
                .encode(
                    x=x_encoding,
                    y=alt.Y("contagem:Q", title="Denúncias"),
                    tooltip=[
                        alt.Tooltip(f"{dimension_col}:N", title=dimension_col),
                        alt.Tooltip("contagem:Q", title="Quantidade"),
                        alt.Tooltip(
                            "percentual:Q", title="% Frequência", format=".1f"
                        ),
                        alt.Tooltip(
                            "percentual_acumulado:Q",
                            title="% Acumulado",
                            format=".1f",
                        ),
                    ],
                )
            )

            line = (
                alt.Chart(chart_df)
                .mark_line(color="#F97316")
                .encode(
                    x=x_encoding,
                    y=alt.Y(
                        "percentual_acumulado:Q",
                        axis=alt.Axis(title="% acumulado", format=".0f%%"),
                    ),
                    tooltip=[
                        alt.Tooltip(f"{dimension_col}:N", title=dimension_col),
                        alt.Tooltip(
                            "percentual_acumulado:Q",
                            title="% Acumulado",
                            format=".1f",
                        ),
                    ],
                )
            )

            points = line.mark_point(size=60)

            histogram = (
                alt.layer(bars, line, points)
                .resolve_scale(y="independent")
                .properties(height=380)
            )

            st.altair_chart(histogram, use_container_width=True)
            st.caption(
                "O gráfico combina a frequência absoluta (barras) com o percentual acumulado (linha)."
            )
