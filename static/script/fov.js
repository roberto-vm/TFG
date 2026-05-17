
document.addEventListener("click", async (e) => {
  // e (evento disparado). e.target es el elemento exacto
  // del DOM sobre el que se hizo click (en este caso concreto)
  if (e.target.id === "send-fov") {
    const input = document.querySelector("#input-fov");
    const val = parseFloat(input.value);
    if (isNaN(val) || val<0 || val>180){
      const output = document.querySelector("#output-fov");
      if (output)
          output.textContent = "Valor invalido de FOV.";
      return;
    }

    try {
      const resp = await fetch("/api/fov", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fov: val }),
      });
      await resp.json();
      window.refreshState();

      const output = document.querySelector("#output-fov");
      if (output)
          output.textContent= "Valor del FOV: " + val;
      //catch es capaz de abarcar cualquier error que se encuentre dentro de try.
      //Desde errores manuales, por motivos de invalidez del JSON, hasta errores
      //de red con fetch (no hay conexion, falla DNS, etc)
    } catch (err) {
      console.error("Error enviando FOV", err);
    }
  }
});