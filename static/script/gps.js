
document.addEventListener("click", (e) => {
  if (e.target.id === "get-gps") {
    if (!navigator.geolocation) {
      const geo = document.querySelector("#geo");
      if (geo) geo.textContent = "Geolocalización no soportada.";
      return;
    }

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const latitude=pos.coords.latitude;
        const longitude=pos.coords.longitude;
        try {
          const resp = await fetch("/api/gps", {
            // Los datos enviados al servidor seran procesados o modificados
            method: "POST",
            // El servidor ha de saber como interpretar el body (en json).
            // Sin dicho header se podria tratar como texto plano
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ latitud: latitude, longitud: longitude }),
          });
          await resp.json();
          await window.refreshState?.();

          const geo = document.querySelector("#geo");
          if (geo) geo.textContent="Lat: " + latitude +", Lon: " + longitude;
        } catch (e) {
          console.error("Error enviando GPS", e);
        }
      },
      (err) => {
        const geo = document.querySelector("#geo");
        if (geo) geo.textContent = "Error obteniendo ubicación: " + err.message;
      }
    );
  }
});