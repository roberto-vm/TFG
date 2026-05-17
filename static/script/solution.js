

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
  // Los navegadores, por norma general, intentar ser eficientes guardando
  // respuestas en cache para poder reutilizarlas. En nuestro, caso trabajamos
  // con un estado dinamico, por lo que evitamos que se guarde una respuesta
  // o se utilice una anterior.
  const r = await fetch("/api/state", { cache: "no-store" });
  //fetch() no lanza errores automaticos si hay un 404 o 500. Es decir,
  // el catch no se ejecuta para errores HTTP
  if (!r.ok) throw new Error("No se pudo leer el estado");
  return r.json();
}

async function runSolution($root) {
  const status = $root.querySelector("#solution-status");
  const out = $root.querySelector("#solution-output");
 // const values = $root.querySelector("#solution-values");

  if (!status || !out) return;

  //if (values) {
  //  values.textContent = "Valores de irradiancia no disponibles";
  //}

  status.textContent = "Comprobando datos…";
  // Al hacer un fetch en JS, recibes un objeto de tipo Response. Las
  // propiedades y los metodos mas comunes son:
  // -.ok. Devuelve True si el status HTTP se encuentra entre 200-299
  // -.json(). Convierte el cuerpo de la respuesta a un objeto JS
  // -.text(). Devuelve el BODY como un texto plano

  try {
    const state = await fetchState();
    if (!hasAllStateFields(state)) {
      status.textContent = "Imagen no disponible: faltan datos (GPS/FOV/IOP).";
      out.innerHTML = "<em>Completa las diapositivas de GPS, FOV e IOP y vuelve a intentarlo.</em>";
      return;
    }

    status.textContent = "Procesando en el servidor…";
    const resp = await fetch("/api/solution", { method: "POST" });
    if (!resp.ok) {
      const msg = await resp.text();
      status.textContent = "Imagen no disponible";
      out.innerHTML = `<em>${msg || "No se pudo generar la imagen."}</em>`;
      return;
    }

    const data = await resp.json();
    if (!data || !data.image) {
      status.textContent = "Imagen no disponible";
      out.innerHTML = "<em>Respuesta vacía.</em>";
      return;
    }

    const img = new Image();
    img.alt = "Imagen con la posición aproximada del sol";
    img.style.maxWidth = "100%";
    img.style.height = "auto";
    img.src = data.image; // data:image/png;base64,...

    out.innerHTML = "";
    // Trabajamos con un nodo real (DOM) o bien un objeto img,
    // no un string HTML
    out.appendChild(img);
    status.textContent = "Listo.";

    // 🔽 NUEVO BLOQUE DE IRRADIANCIA
    let values = document.createElement("div");
    values.id = "solution-values";
    values.style.marginTop = "10px";
    out.appendChild(values);

    // Comprobamos que los datos existen
    const irrSolar = data.irradiancia_solar;
    const irrHoy = data.irradiacion_hoy;
    const irrGlobal = data.irradiacion_global;


    // Mostramos los valores
    values.innerHTML = `
      <p><strong>Irradiancia solar:</strong> ${irrSolar ?? "N/D"} W/m²</p>
      <p><strong>Irradiación hoy:</strong> ${irrHoy ?? "N/D"} Wh/m²</p>
      <p><strong>Irradiación global:</strong> ${irrGlobal ?? "N/D"} Wh/m²</p>
    `;
  } catch (err) {
    console.error(err);
    const out = $root.querySelector("#solution-output");
    const status = $root.querySelector("#solution-status");
    if (status) status.textContent = "Imagen no disponible (error).";
    if (out) out.innerHTML = "<em>Ocurrió un error al calcular la solución.</em>";
  }
}

(function attachHandlers() {
  // Delegación global: funciona aunque el parcial se cargue dinámicamente
  document.addEventListener("click", (ev) => {
    if (ev.target && ev.target.id === "btn-run-solution") {
      //root es el contenedor (elemento padre) donde esta renderizado
      //el "partial" correspondiente o el bloque de la interfaz (slide de
      // solution)
      const root =
        ev.target.closest('[data-partial="solution"]') ||
        document.getElementById("solution-root") ||
        document.body;
      runSolution(root);
    }
  });

  // Si el parcial ya está en el DOM (por recarga en esa slide), no hacemos nada más:
  // el usuario pulsará el botón para ejecutar.
})();

