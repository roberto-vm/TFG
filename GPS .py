import streamlit as st

st.title("Obtener Geolocalización en Streamlit")

html_code = """
<script>
    function getLocation() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    document.getElementById("coords").innerText = 
                        "Lat: " + position.coords.latitude + 
                        ", Lon: " + position.coords.longitude;
                },
                (error) => {
                    document.getElementById("coords").innerText = "Error: " + error.message;
                }
            );
        } else {
            document.getElementById("coords").innerText = "Geolocalización no es soportada en este navegador.";
        }
    }
    window.onload = getLocation;
</script>
<div id="coords">Obteniendo ubicación...</div>
"""

st.components.v1.html(html_code)
