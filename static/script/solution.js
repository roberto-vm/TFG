function hasAllStateFields(state) {
  let isReady = true;

  Object.entries(state).forEach(([k, v]) => {
    if (!isReady) return;

    if (k === "iop_image_ok") {
      if (v !== true) {
        isReady = false;
      }
    } else {
      if (v === null || v === undefined || v === "") {
        isReady = false;
      }
    }
  });

  return isReady;
}

async function fetchState() {
  const r = await fetch("/api/state", { cache: "no-store" });

  if (!r.ok) throw new Error("No se pudo leer el estado");

  return r.json();
}

async function runSolution($root) {
  const status = $root.querySelector("#solution-status");
  const out = $root.querySelector("#solution-output");
  const iterations = $root.querySelector("#solution-iterations");

  if (!status || !out || !iterations) return;

  status.textContent = "Comprobando datos…";
  iterations.innerHTML = "";

  try {
    const state = await fetchState();

    if (!hasAllStateFields(state)) {
      status.textContent = "Imagen no disponible: faltan datos (GPS/FOV/IOP).";
      out.innerHTML =
        "<em>Completa las diapositivas de GPS, FOV e IOP y vuelve a intentarlo.</em>";
      iterations.innerHTML = "";
      return;
    }

    status.textContent = "Procesando en el servidor…";

    const resp = await fetch("/api/solution", { method: "POST" });

    if (!resp.ok) {
      const msg = await resp.text();
      status.textContent = "Imagen no disponible";
      out.innerHTML = `<em>${msg || "No se pudo generar la imagen."}</em>`;
      iterations.innerHTML = "";
      return;
    }

    const data = await resp.json();

    if (!data || !data.image) {
      status.textContent = "Imagen no disponible";
      out.innerHTML = "<em>Respuesta vacía.</em>";
      iterations.innerHTML = "";
      return;
    }

    const img = new Image();
    img.alt = "Imagen con la posición aproximada del sol";
    img.style.maxWidth = "100%";
    img.style.height = "auto";
    img.src = data.image;

    out.innerHTML = "";
    out.appendChild(img);

    const values = document.createElement("div");
    values.id = "solution-values";
    values.style.marginTop = "10px";
    out.appendChild(values);

    const irrSolar = data.irradiancia_solar;
    const irrHoy = data.irradiacion_hoy;
    const irrGlobal = data.irradiacion_global;
    const duracionHoy = data.duracion_hoy_min;
    const diasSol = data.dias_sol_entra_imagen;

    values.innerHTML = `
     <p>
       <strong>Irradiancia solar:</strong><br>
       ${irrSolar ?? "N/D"} W/m²
     </p>

     <p>
       <strong>Irradiación hoy:</strong><br>
       ${irrHoy ?? "N/D"} Wh/m²<br>
       <small>Tiempo con el Sol en la imagen: ${duracionHoy ?? "N/D"} min</small>
     </p>

     <p>
       <strong>Irradiación global:</strong><br>
       ${irrGlobal ?? "N/D"} Wh/m²<br>
       <small>${diasSol ?? "N/D"} días con Sol en la imagen</small>
     </p>
     `;

    const datosIteracionesHoy = data.datos_iteraciones_hoy || {};

    const filas = Object.entries(datosIteracionesHoy)
      .map(([iteracion, dato]) => {
        const u = Number(dato.u_i);
        const v = Number(dato.v_i);

        return `
          <tr>
            <td style="padding:6px;border-bottom:1px solid #ddd;">${iteracion}</td>
            <td style="padding:6px;border-bottom:1px solid #ddd;">${dato.t_i ?? "N/D"}</td>
            <td style="padding:6px;border-bottom:1px solid #ddd;">${Number.isFinite(u) ? u.toFixed(2) : "N/D"}</td>
            <td style="padding:6px;border-bottom:1px solid #ddd;">${Number.isFinite(v) ? v.toFixed(2) : "N/D"}</td>
            <td style="padding:6px;border-bottom:1px solid #ddd;">${dato.is_blue ? "SI" : "NO"}</td>
          </tr>
        `;
      })
      .join("");

    iterations.innerHTML = `
      <h4 style="margin:0 0 8px 0;">Datos de iteraciones del día de la foto</h4>

      ${
        filas
          ? `
            <div style="overflow-x:auto;background:#fff;border:1px solid #ddd;">
              <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
                <thead>
                  <tr>
                    <th style="text-align:left;padding:6px;border-bottom:1px solid #ccc;">Iteración</th>
                    <th style="text-align:left;padding:6px;border-bottom:1px solid #ccc;">t_i</th>
                    <th style="text-align:left;padding:6px;border-bottom:1px solid #ccc;">u_i</th>
                    <th style="text-align:left;padding:6px;border-bottom:1px solid #ccc;">v_i</th>
                    <th style="text-align:left;padding:6px;border-bottom:1px solid #ccc;">Obstaculo</th>
                  </tr>
                </thead>
                <tbody>
                  ${filas}
                </tbody>
              </table>
            </div>
          `
          : `<p class="text-muted">No hay iteraciones disponibles para el día de la foto.</p>`
      }
    `;

    status.textContent = "Listo.";
  } catch (err) {
    console.error(err);

    status.textContent = "Imagen no disponible (error).";
    out.innerHTML = "<em>Ocurrió un error al calcular la solución.</em>";
    iterations.innerHTML = "";
  }
}

(function attachHandlers() {
  document.addEventListener("click", (ev) => {
    if (ev.target && ev.target.id === "btn-run-solution") {
      const root =
        ev.target.closest('[data-partial="solution"]') ||
        document.getElementById("solution-root") ||
        document.body;

      runSolution(root);
    }
  });
})();

