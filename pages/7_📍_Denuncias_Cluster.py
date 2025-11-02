import streamlit as st
import leafmap.foliumap as leafmap

st.set_page_config(layout="wide")

markdown = """
Denúncias de Poluição Sonora em Maringá 2020-2023
"""

st.sidebar.title("Sobre")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

st.title("Clusters de Denúncias")

with st.expander("See source code"):
    with st.echo():

        m = leafmap.Map(center=[-23.4205, -51.9333], zoom=4)
        denuncias = "https://raw.githubusercontent.com/daSilvaGAC/streamlit-maps/refs/heads/main/mga_denuncias_20-23.csv"
        # Centraliza o mapa no retângulo de Maringá e ajusta o zoom
        bounds = [[-23.466711, -52.006187], [-23.366526, -51.867485]]
        m.zoom_to_bounds(bounds)
        ## regions = "https://raw.githubusercontent.com/giswqs/leafmap/master/examples/data/us_regions.geojson"

        ## m.add_geojson(regions, layer_name="US Regions")
        m.add_points_from_xy(
            denuncias,
            x="longitude",
            y="latitude",
           ##  color_column="region",
            icon_names=["gear", "map", "leaf", "globe"],
            spin=True,
            add_legend=True,
        )

m.to_streamlit(height=500)