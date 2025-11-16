from __future__ import annotations

from pathlib import Path
import json
import re
from collections import Counter

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


CUSTOM_RULES_KEY = "custom_rules"


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


def _ensure_session_state() -> None:
    if CUSTOM_RULES_KEY not in st.session_state:
        st.session_state[CUSTOM_RULES_KEY] = []


def _match_rule(row: pd.Series, rule: dict) -> bool:
    if not rule:
        return False
    context = (row.get("fonte_contexto") or "").strip()
    audio = (row.get("fonte_audio") or "").strip()
    horarios = row.get("fonte_horario") or []
    tokens = row.get("descricao_tokens") or []
    token_set = set(tokens)

    contexts = rule.get("contexts") or []
    if contexts and context not in contexts:
        return False

    audios = rule.get("audios") or []
    if audios and audio not in audios:
        return False

    rule_tokens = rule.get("tokens") or []
    if rule_tokens and not set(rule_tokens).issubset(token_set):
        return False

    rule_times = rule.get("times") or []
    if rule_times:
        if not horarios:
            return False
        if not set(rule_times).intersection(set(horarios)):
            return False

    return True


def apply_custom_rules(data: pd.DataFrame, rules: list[dict]) -> pd.DataFrame:
    if data.empty:
        data = data.copy()
        data["custom_rules"] = [[] for _ in range(len(data))]
        data["custom_rules_label"] = ""
        return data

    if not rules:
        result = data.copy()
        result["custom_rules"] = [[] for _ in range(len(result))]
        result["custom_rules_label"] = ""
        return result

    def _aggregate(row: pd.Series) -> list[str]:
        labels: list[str] = []
        for rule in rules:
            name = rule.get("name")
            if not name:
                continue
            if _match_rule(row, rule):
                labels.append(name)
        return labels

    result = data.copy()
    result["custom_rules"] = result.apply(_aggregate, axis=1)
    result["custom_rules_label"] = result["custom_rules"].apply(
        lambda labels: ", ".join(labels)
    )
    return result


def build_pareto_dataframe(data: pd.DataFrame, column: str) -> pd.DataFrame:
    if data.empty or column not in data.columns:
        return pd.DataFrame()
    freq = (
        data[column]
        .fillna("Não informado")
        .astype(str)
        .value_counts()
        .reset_index()
        .rename(columns={"index": column, column: "Denúncias"})
    )
    freq["Denúncias"] = pd.to_numeric(freq["Denúncias"], errors="coerce").fillna(0)
    total = freq["Denúncias"].sum()
    if total == 0:
        return pd.DataFrame()
    freq["% Frequência"] = freq["Denúncias"] / total * 100
    freq["% Acumulado"] = freq["% Frequência"].cumsum()
    return freq


def render_pareto_chart(data: pd.DataFrame, column: str, title: str) -> None:
    freq = build_pareto_dataframe(data, column)
    if freq.empty:
        st.info(f"Sem dados suficientes para {title}.")
        return

    freq["categoria"] = freq[column].astype(str)
    order = freq["categoria"].tolist()

    bars = (
        alt.Chart(freq)
        .mark_bar(color="#10B981")
        .encode(
            x=alt.X("categoria:N", sort=order, title=column),
            y=alt.Y("Denúncias:Q"),
            tooltip=[
                alt.Tooltip("categoria:N", title=column),
                alt.Tooltip("Denúncias:Q"),
                alt.Tooltip("% Frequência:Q", format=".1f"),
                alt.Tooltip("% Acumulado:Q", format=".1f"),
            ],
        )
    )

    line = (
        alt.Chart(freq)
        .mark_line(color="#EF4444")
        .encode(
            x=alt.X("categoria:N", sort=order),
            y=alt.Y("% Acumulado:Q"),
        )
    )

    points = (
        alt.Chart(freq)
        .mark_point(color="#EF4444")
        .encode(
            x=alt.X("categoria:N", sort=order),
            y=alt.Y("% Acumulado:Q"),
        )
    )

    chart = alt.layer(bars, line, points).resolve_scale(y="independent").properties(
        width="container", height=380
    )
    st.subheader(title)
    st.altair_chart(chart, width="stretch")
    st.dataframe(freq, use_container_width=True, hide_index=True)


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

    if "descricao_tokens" not in df.columns:
        df["descricao_tokens"] = [[] for _ in range(len(df))]
    df["descricao_tokens"] = df["descricao_tokens"].apply(
        lambda value: value if isinstance(value, list) else []
    )

    if "fonte_horario" not in df.columns:
        df["fonte_horario"] = [[] for _ in range(len(df))]
    df["fonte_horario"] = df["fonte_horario"].apply(
        lambda value: value
        if isinstance(value, list)
        else ([] if not value or pd.isna(value) else [str(value)])
    )

    if "endereco_formatado" not in df.columns:
        df["endereco_formatado"] = ""
    df["endereco_formatado"] = df["endereco_formatado"].fillna("").astype(str)

    if "bairro_formatado" not in df.columns:
        df["bairro_formatado"] = df["endereco_formatado"].apply(_extract_bairro)
    df["bairro_formatado"] = (
        df["bairro_formatado"].fillna(df.get("Bairro")).fillna("").astype(str)
    )

    for col in ["fonte_contexto", "fonte_audio", "Tipo de Fonte"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    df["Tipo de Fonte"] = df["Tipo de Fonte"].replace("", "indefinido")
    df["descricao_tokens_text"] = df["descricao_tokens"].apply(
        lambda tokens: ", ".join(tokens)
    )

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
    return df



df = load_data()

if df.empty:
    st.warning("Nenhuma denúncia encontrada no arquivo GeoJSON fornecido.")
    st.stop()

token_counter: Counter[str] = Counter()
for tokens in df["descricao_tokens"]:
    token_counter.update(tokens)
token_choices = [token for token, _ in token_counter.most_common(300)]

type_options = sorted(
    {label for label in df.get("Tipo de Fonte", pd.Series(dtype="object")).unique() if label}
)
context_options = sorted(
    {
        ctx
        for ctx in df.get("fonte_contexto", pd.Series(dtype="object")).unique()
        if ctx
    }
)
audio_options = sorted(
    {
        aud
        for aud in df.get("fonte_audio", pd.Series(dtype="object")).unique()
        if aud
    }
)
time_options = sorted(
    {
        item
        for horarios in df.get("fonte_horario", pd.Series(dtype="object"))
        for item in (horarios or [])
        if item
    }
)

bairro_choices = sorted(
    {valor for valor in df.get("bairro_formatado", pd.Series(dtype="object")) if valor}
)

_ensure_session_state()
custom_rules = st.session_state[CUSTOM_RULES_KEY]

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

st.sidebar.subheader("Filtros NLP")
selected_types = st.sidebar.multiselect(
    "Tipo de Fonte (NLP)",
    options=type_options,
)
selected_contexts = st.sidebar.multiselect(
    "Contextos (fonte_contexto)",
    options=context_options,
)
selected_audios = st.sidebar.multiselect(
    "Modalidades (fonte_audio)",
    options=audio_options,
)
selected_times = st.sidebar.multiselect(
    "Horários inferidos",
    options=time_options,
)
selected_tokens = st.sidebar.multiselect(
    "Tokens obrigatórios (top 300)",
    options=token_choices,
    help="Filtra apenas denúncias que contenham todos os tokens selecionados.",
)

if custom_rules:
    selected_custom_rules = st.sidebar.multiselect(
        "Regras personalizadas",
        options=[rule["name"] for rule in custom_rules],
        help="Filtra apenas as denúncias associadas às regras selecionadas.",
    )
else:
    selected_custom_rules = []

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

if selected_types:
    filtered = filtered[
        filtered.get("Tipo de Fonte", "")
        .astype(str)
        .isin(selected_types)
    ]

if selected_contexts:
    filtered = filtered[
        filtered.get("fonte_contexto", "")
        .astype(str)
        .isin(selected_contexts)
    ]

if selected_audios:
    filtered = filtered[
        filtered.get("fonte_audio", "")
        .astype(str)
        .isin(selected_audios)
    ]

if selected_times:
    filtered = filtered[
        filtered.get("fonte_horario", []).apply(
            lambda horarios: bool(set(horarios or []).intersection(selected_times))
        )
    ]

if selected_tokens:
    required_tokens = set(selected_tokens)
    filtered = filtered[
        filtered["descricao_tokens"].apply(
            lambda tokens: required_tokens.issubset(set(tokens))
        )
    ]

filtered = apply_custom_rules(filtered, custom_rules)

if selected_custom_rules:
    selected_set = set(selected_custom_rules)
    filtered = filtered[
        filtered["custom_rules"].apply(
            lambda labels: bool(set(labels).intersection(selected_set))
        )
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
            "Tipo de Fonte",
            "fonte_contexto",
            "fonte_audio",
            "bairro_formatado",
            "custom_rules_label",
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
            "Tipo de Fonte",
            "fonte_contexto",
            "fonte_audio",
            "fonte_horario",
            "custom_rules_label",
        ]
        display_columns = [col for col in display_columns if col in map_data.columns]
        if not display_columns:
            st.info("As colunas esperadas não estão disponíveis nos dados.")
        else:
            st.dataframe(
                map_data[display_columns].head(500),
                use_container_width=True,
                hide_index=True,
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
    st.dataframe(resumo, use_container_width=True, hide_index=True)

st.markdown("## Classificações NLP")
render_pareto_chart(filtered, "Tipo de Fonte", "Pareto - Tipo de Fonte")
render_pareto_chart(filtered, "fonte_contexto", "Pareto - Contexto (fonte_contexto)")
render_pareto_chart(filtered, "fonte_audio", "Pareto - Modalidade (fonte_audio)")

st.markdown("### Cruzamento contexto × áudio")
if filtered.empty:
    st.info("Sem dados para gerar o cruzamento com os filtros atuais.")
else:
    cross_df = (
        filtered.groupby(["fonte_contexto", "fonte_audio"])
        .size()
        .reset_index(name="Denúncias")
        .sort_values("Denúncias", ascending=False)
    )
    if cross_df.empty:
        st.info("Sem combinações disponíveis.")
    else:
        top_cross = cross_df.head(30)
        heatmap = (
            alt.Chart(top_cross)
            .mark_rect()
            .encode(
                x=alt.X("fonte_contexto:N", title="Contexto", sort="-y"),
                y=alt.Y("fonte_audio:N", title="Modalidade", sort="-x"),
                color=alt.Color("Denúncias:Q", scale=alt.Scale(scheme="viridis")),
                tooltip=[
                    alt.Tooltip("fonte_contexto:N", title="Contexto"),
                    alt.Tooltip("fonte_audio:N", title="Modalidade"),
                    alt.Tooltip("Denúncias:Q"),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(heatmap, width="stretch")
        st.dataframe(cross_df, use_container_width=True, hide_index=True)

st.markdown("## Regras personalizadas (tokens + contexto)")
with st.expander("Criar/editar regras"):
    with st.form("custom_rule_form", clear_on_submit=True):
        rule_name = st.text_input("Nome da regra")
        form_contexts = st.multiselect(
            "Contextos desejados",
            options=context_options,
            help="O registro precisa corresponder a pelo menos um dos contextos.",
        )
        form_audios = st.multiselect(
            "Modalidades desejadas",
            options=audio_options,
            help="O registro precisa corresponder a pelo menos uma modalidade.",
        )
        form_tokens = st.multiselect(
            "Tokens obrigatórios",
            options=token_choices,
            help="Todos os tokens selecionados precisam estar presentes na denúncia.",
        )
        form_times = st.multiselect(
            "Horários inferidos desejados",
            options=time_options,
        )
        submitted = st.form_submit_button("Adicionar regra")
        if submitted:
            if not rule_name:
                st.warning("Informe um nome para a regra.")
            else:
                new_rule = {
                    "name": rule_name,
                    "contexts": form_contexts,
                    "audios": form_audios,
                    "tokens": form_tokens,
                    "times": form_times,
                }
                st.session_state[CUSTOM_RULES_KEY].append(new_rule)
                st.success(f"Regra '{rule_name}' adicionada.")
                st.experimental_rerun()

if custom_rules:
    st.markdown("### Regras ativas")
    for idx, rule in enumerate(custom_rules):
        cols = st.columns((3, 3, 3, 1))
        cols[0].markdown(f"**{rule.get('name')}**")
        cols[1].markdown(f"Contextos: {', '.join(rule.get('contexts') or ['-'])}")
        cols[2].markdown(f"Modalidades: {', '.join(rule.get('audios') or ['-'])}")
        if cols[3].button("Remover", key=f"remove_rule_{idx}"):
            st.session_state[CUSTOM_RULES_KEY].pop(idx)
            st.experimental_rerun()

    st.markdown("### Downloads")
    rules_payload = json.dumps(custom_rules, ensure_ascii=False, indent=2)
    st.download_button(
        "Baixar regras em JSON",
        data=rules_payload,
        file_name="regras_personalizadas.json",
        mime="application/json",
    )
else:
    st.info("Nenhuma regra personalizada configurada até o momento.")

st.markdown("### Ocorrências com regras personalizadas")
if filtered.empty:
    st.info("Sem dados para exibir.")
else:
    matches_df = filtered[filtered["custom_rules_label"] != ""].copy()
    if matches_df.empty:
        st.info("Nenhuma denúncia corresponde às regras atuais.")
    else:
        st.dataframe(
            matches_df[
                [
                    "Protocolo",
                    "DataInclusao",
                    "Descrição",
                    "Tipo de Fonte",
                    "fonte_contexto",
                    "fonte_audio",
                    "fonte_horario",
                    "custom_rules_label",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
