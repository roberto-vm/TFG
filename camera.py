import streamlit as st

st.title("Acceso a la Cámara en Streamlit")

html_code = """
<script>
    function startCamera() {
        let video = document.getElementById("videoElement");

        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })  // Cámara trasera
                .then(function(stream) {
                    video.srcObject = stream;
                })
                .catch(function(error) {
                    document.getElementById("camera_status").innerText = "Error: " + error.message;
                });
        } else {
            document.getElementById("camera_status").innerText = "El acceso a la cámara no es compatible con este navegador.";
        }
    }
</script>

<button onclick="startCamera()">Activar Cámara</button>
<p id="camera_status">Presiona el botón para activar la cámara...</p>
<video id="videoElement" width="300" height="200" autoplay playsinline></video>
"""

st.components.v1.html(html_code)

