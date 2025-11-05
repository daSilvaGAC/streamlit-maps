import streamlit as st
import leafmap.foliumap as leafmap

st.set_page_config(layout="wide")

# Customize the sidebar
markdown = """
Aplicação web para visualização e anáise geoespacial de denúncias de poluição sonora.

Powered by Coeficiência Acústica:
<https://www.coeficiencia.com.br>
"""

st.sidebar.title("Sobre")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

# Customize page title
st.title("Geospatial Acoustics Applications")

st.markdown(
    """
    A Aplicação web para visualização e anáise geoespacial de denúncias de poluição sonora. Explore mapas interativos para avaliar denúncias de ruído no espaço e no tempo, integrar camadas ambientais e gerar produtos analíticos para apoiar a tomada de decisões. A aplicação também será utilizada para visualizar e registrar denúncias de poluição sonora.
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

st.title("Clusters de Denúncias de Ruído em Maringá. Dados de 2021 a 2023")

m = leafmap.Map(center=[-23.415367, -51.931343], zoom=12)
denuncias = "https://raw.githubusercontent.com/daSilvaGAC/streamlit-maps/refs/heads/main/mga_denuncias_20-23.csv"

m.add_points_from_xy(
    denuncias,
    x="longitude",
    y="latitude",
    icon_names=["gear", "map", "leaf", "globe"],
    spin=True,
    add_legend=True,
)

m.to_streamlit(height=500)
