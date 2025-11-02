import streamlit as st
import leafmap.foliumap as leafmap

st.set_page_config(layout="wide")
st.title("Mapa de Calor de Denúncias")

st.sidebar.title("About")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

st.title("Clusters de Denúncias")

with st.expander("See source code"):
    with st.echo():
        
        m = leafmap.Map(center=[-23.415367,-51.931343], zoom=12)
        denuncias = "https://raw.githubusercontent.com/daSilvaGAC/streamlit-maps/refs/heads/main/mga_denuncias_20-23.csv"
        ## regions = "https://raw.githubusercontent.com/giswqs/leafmap/master/examples/data/us_regions.geojson"

        ## m.add_geojson(regions, layer_name="US Regions")
        m.add_heatmap(
            denuncias,
            latitude="latitude",
            longitude="longitude",
            value="pop_max",
            name="Heat map",
            radius=20,
        )

m.to_streamlit(height=500)