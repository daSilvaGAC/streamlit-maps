import streamlit as st
import leafmap.foliumap as leafmap

st.set_page_config(layout="wide")

# Customize the sidebar
markdown = """
Application for geospatial acoustic visualization, powered by Coeficiência Acústica:
<https://www.coeficiencia.com.br>
"""

st.sidebar.title("About")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

# Customize page title
st.title("Geospatial Acoustics Applications")

st.markdown(
    """
    Application for geospatial acoustic visualization and analysis. Explore interactive maps to assess noise levels in space and time, integrate environmental layers, and generate analytical products to support decision-making. The application will also be used to visualize and log complaints of noise pollution.
    
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

markdown = """
Denúncias de Poluição Sonora em Maringá 2020-2023
"""

st.sidebar.title("Sobre")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

st.title("Noise Complaints Clusters")

m = leafmap.Map(center=[-23.415367, -51.931343], zoom=12)
denuncias = "mga_denuncias_20-23.csv"

m.add_points_from_xy(
    denuncias,
    x="longitude",
    y="latitude",
    icon_names=["gear", "map", "leaf", "globe"],
    spin=True,
    add_legend=True,
)

m.to_streamlit(height=500)
