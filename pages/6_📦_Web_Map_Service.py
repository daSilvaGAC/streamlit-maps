import ast
import streamlit as st
import leafmap.foliumap as leafmap
from leafmap import common as cm  # <- get_wms_layers está aqui

st.set_page_config(layout="wide")

st.sidebar.title("About")
st.sidebar.info(
    "A Streamlit map template\n<https://github.com/opengeos/streamlit-map-template>"
)
st.sidebar.image("https://i.imgur.com/UbOXYAU.png")

@st.cache_data
def get_layers(url: str):
    return cm.get_wms_layers(url)

st.title("Web Map Service (WMS)")
st.markdown(
    """
This app demonstrates loading Web Map Service (WMS) layers. Enter a WMS URL and pick layers.
If needed, try a GetCapabilities URL like:
https://services.terrascope.be/wms/v2?SERVICE=WMS&REQUEST=GetCapabilities
"""
)

col_map, col_ctrl = st.columns([3, 1.3])
width, height = None, 600
layers = []
add_legend = False
legend_text = ""

# --------- Coluna de controles (direita) ---------
with col_ctrl:
    esa_landcover = "https://services.terrascope.be/wms/v2"
    url = st.text_input("Enter a WMS URL:", value=esa_landcover)

    options = []
    if url:
        try:
            options = get_layers(url)
        except Exception as e:
            st.error(f"Erro ao consultar camadas: {e}")

    default = "WORLDCOVER_2020_MAP" if url == esa_landcover else None
    layers = st.multiselect(
        "Select WMS layers to add to the map:",
        options,
        default=[default] if default in options else None,
    )

    add_legend = st.checkbox("Add a legend to the map", value=True)
    if default == "WORLDCOVER_2020_MAP":
        legend_text = str(leafmap.builtin_legends.get("ESA_WorldCover", {}))
    if add_legend:
        legend_text = st.text_area(
            "Legend as a dict {label: color}", value=legend_text or "", height=200
        )

# --------- Coluna do mapa (esquerda) ---------
with col_map:
    m = leafmap.Map(center=(20, 0), zoom=2)

    for lyr in layers or []:
        # Força PNG + transparente; muitos WMS exigem.
        m.add_wms_layer(
            url=url,
            layers=lyr,
            name=lyr,
            format="image/png",
            transparent=True,
            attribution=" ",
        )

    if add_legend and legend_text:
        try:
            legend_dict = ast.literal_eval(legend_text)
            if isinstance(legend_dict, dict) and legend_dict:
                m.add_legend(legend_dict=legend_dict)
        except Exception:
            st.warning("Legenda inválida. Use um dicionário Python, ex.: {'Classe A': '#ff0000'}")

    m.to_streamlit(width=width, height=height)
