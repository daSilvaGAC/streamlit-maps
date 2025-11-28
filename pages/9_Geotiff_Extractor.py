"""
Ferramenta para extrair camadas geoespaciais em GeoTIFF a partir de fontes já
disponíveis no ecossistema leafmap/geemap. O objetivo é preparar, numa mesma
projeção e resolução, variáveis que alimentam modelos acústicos semelhantes ao
pipeline descrito por Mennitt et al. (2014).

Fluxo:
1. Defina a área de interesse (Marigá por padrão ou outra bbox).
2. Selecione as camadas desejadas (uso do solo, altitude, NDVI etc.).
3. Exporte cada layer como GeoTIFF já recortado para a área escolhida.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict

import ee
import geemap
import streamlit as st

st.set_page_config(page_title="GeoTIFF Extractor", layout="wide")

st.title("GeoTIFF Extractor – preparação de camadas geoespaciais")
st.markdown(
    """
Ferramenta para reunir variáveis baseadas em satélites/cartas (uso do solo,
altimetria, NDVI etc.) antes de integrar os monitoramentos acústicos. Utilize
os controles na barra lateral para definir a área de interesse e exportar os
rasters em GeoTIFF.
"""
)

try:
    ee.Initialize()
    st.success("✅ Conectado ao Google Earth Engine.")
except Exception as exc:
    st.warning(
        "Não foi possível autenticar no Earth Engine automaticamente. "
        "Execute `earthengine authenticate` no terminal ou configure as "
        "variáveis de ambiente de serviço antes de prosseguir."
    )
    st.stop()


DEFAULT_BBOX = (-51.98, -23.52, -51.82, -23.32)  # Maringá aprox.


def get_bbox_from_inputs() -> ee.Geometry.BBox:
    col1, col2 = st.sidebar.columns(2)
    min_lon = col1.number_input("Min lon", value=DEFAULT_BBOX[0], format="%.5f")
    max_lon = col2.number_input("Max lon", value=DEFAULT_BBOX[2], format="%.5f")
    min_lat = col1.number_input("Min lat", value=DEFAULT_BBOX[1], format="%.5f")
    max_lat = col2.number_input("Max lat", value=DEFAULT_BBOX[3], format="%.5f")
    return ee.Geometry.BBox(min_lon, min_lat, max_lon, max_lat)


@st.cache_data(show_spinner=False)
def _get_layer_configs() -> Dict[str, Dict[str, Callable]]:
    def _worldcover(year: int) -> ee.Image:
        return (
            ee.ImageCollection("ESA/WorldCover/v200")
            .filter(ee.Filter.eq("MAP_YEAR", year))
            .first()
        )

    def _srtm(_: int) -> ee.Image:
        return ee.Image("USGS/SRTMGL1_003")

    def _ndvi(year: int) -> ee.Image:
        collection = ee.ImageCollection("MODIS/006/MOD13A2").filterDate(
            f"{year}-01-01", f"{year}-12-31"
        )
        return collection.select("NDVI").median()

    def _nightlights(year: int) -> ee.Image:
        collection = ee.ImageCollection(
            "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG"
        ).filterDate(f"{year}-01-01", f"{year}-12-31")
        return collection.select("avg_rad").median()

    def _human_mod(_: int) -> ee.Image:
        return ee.Image("CSP/ERGo/1_0/GlobalHumanModification")

    return {
        "worldcover": {
            "label": "Uso do solo (ESA WorldCover)",
            "image_fn": _worldcover,
            "scale": 10,
            "years": list(range(2020, 2023)),
        },
        "srtm": {
            "label": "Altimetria (SRTM 30m)",
            "image_fn": _srtm,
            "scale": 30,
            "years": [2000],
        },
        "ndvi": {
            "label": "NDVI (MODIS 1km, mediana anual)",
            "image_fn": _ndvi,
            "scale": 500,
            "years": list(range(2015, 2024)),
        },
        "nightlights": {
            "label": "Luzes noturnas (VIIRS)",
            "image_fn": _nightlights,
            "scale": 500,
            "years": list(range(2012, 2024)),
        },
        "human_mod": {
            "label": "Intensidade antrópica (Global Human Modification)",
            "image_fn": _human_mod,
            "scale": 1000,
            "years": [2016],
        },
    }


def export_layer(
    layer_key: str,
    year: int,
    geometry: ee.Geometry,
    out_dir: Path,
) -> Path:
    configs = _get_layer_configs()
    cfg = configs[layer_key]
    image = cfg["image_fn"](year)
    clipped = image.clip(geometry)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = out_dir / f"{layer_key}_{year}.tif"
    geemap.ee_export_image(
        clipped,
        filename=str(filename),
        scale=cfg["scale"],
        region=geometry,
        file_per_band=False,
    )
    return filename


st.sidebar.header("Passo 1 – Área de interesse")
roi_geom = get_bbox_from_inputs()

preview = geemap.Map(center=[-23.42, -51.93], zoom=10)
preview.add_basemap("HYBRID")
preview.add_roi(roi_geom, layer_name="Área selecionada")
preview.to_streamlit(height=400)

st.sidebar.header("Passo 2 – Camadas para exportar")
configs = _get_layer_configs()
layer_options = {cfg["label"]: key for key, cfg in configs.items()}
selected_labels = st.sidebar.multiselect(
    "Escolha as camadas",
    options=list(layer_options.keys()),
    default=list(layer_options.keys())[:2],
)
selected_layers = [layer_options[label] for label in selected_labels]

year_inputs = {}
for key in selected_layers:
    cfg = configs[key]
    years = cfg["years"]
    if len(years) == 1:
        year_inputs[key] = years[0]
    else:
        year_inputs[key] = st.sidebar.selectbox(
            f"Ano para {cfg['label']}",
            options=years,
            index=len(years) - 1,
        )

output_dir = Path(
    st.sidebar.text_input(
        "Diretório de saída",
        value=str(Path("geotiff_camadas").resolve()),
    )
)

st.sidebar.header("Passo 3 – Exportar GeoTIFFs")
if st.sidebar.button("Exportar camadas selecionadas"):
    if not selected_layers:
        st.warning("Selecione ao menos uma camada.")
    else:
        with st.spinner("Exportando camadas..."):
            for layer in selected_layers:
                year = year_inputs[layer]
                try:
                    path = export_layer(layer, year, roi_geom, output_dir)
                    st.success(f"{configs[layer]['label']} ({year}) → {path}")
                except Exception as exc:
                    st.error(f"Falha ao exportar {configs[layer]['label']}: {exc}")
        st.info("Processo concluído.")
