import streamlit as st
import leafmap.foliumap as leafmap

markdown = """
Powered by: <https://www.coeficiencia.com.br>
"""

st.sidebar.title("About")
st.sidebar.info(markdown)
logo = "https://i.imgur.com/UbOXYAU.png"
st.sidebar.image(logo)

st.title("Heatmap")

with st.expander("See source code"):
    with st.echo():
        filepath = "https://raw.githubusercontent.com/daSilvaGAC/streamlit-maps/refs/heads/main/mga_denuncias_20-23.csv"
        m = leafmap.Map(center=[-23.415367,-51.931343], zoom=4)
        m.add_heatmap(
            filepath,
            latitude="latitude",
            longitude="longitude",
            value="pop_max",
            name="Heat map",
            radius=20,
        )

m.to_streamlit(height=500)