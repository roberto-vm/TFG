// Navegacion entre slides
function showSlide(index) {
  const slides = document.querySelectorAll(".slide");
  slides.forEach((s, i) => {
    s.style.display = i === index ? "block" : "none";
  });
  // Mostrar la diapositiva en la que nos encontramos
  document.querySelector("#slide-indicator").textContent =
    `${index + 1} / ${slides.length}`;

  // Actualizacion de botones prev/next
  document.querySelector("#prev-slide").disabled = index === 0;
  document.querySelector("#next-slide").disabled = index === slides.length - 1;
}

function initDeck() {
  const slides = document.querySelectorAll(".slide");
  if (!slides.length) return;

  let current = 0;
  showSlide(current);

  const prevBtn = document.querySelector("#prev-slide");
  const nextBtn = document.querySelector("#next-slide");

  prevBtn.addEventListener("click", () => {
    if (current > 0) {
      current--;
      showSlide(current);
    }
  });

  nextBtn.addEventListener("click", () => {
    if (current < slides.length - 1) {
      current++;
      showSlide(current);
    }
  });
}

// Refresca y actualiza el estado desde el servidor
async function refreshState() {
  try {
    const resp = await fetch("/api/state");
    const data = await resp.json();
    const stateDiv = document.querySelector("#state");
    if (stateDiv) {
      stateDiv.innerHTML = `
        <div>latitud: ${data.latitud ?? "—"}</div>
        <div>longitud: ${data.longitud ?? "—"}</div>
        <div>fov: ${data.fov ?? "—"}</div>
        <div>instant: ${data.iop_instant ?? "—"}</div>
        <div>ancho: ${data.iop_width ?? "—"}</div>
        <div>alto: ${data.iop_height ?? "—"}</div>
        <div>inclinación (pitch): ${data.iop_pitch ?? "—"}</div>
        <div>orientación (heading): ${data.iop_heading ?? "—"}</div>
        <div>imagen: ${data.iop_image_ok ? "ok" : "—"}</div>
      `;
    }
  } catch (e) {
    console.error("Error refrescando estado", e);
  }
}

// Cargar parciales en las slides
async function loadPartials() {
  const placeholders = document.querySelectorAll("[data-partial]");
  //for ... of es el ideal. .forEach() no espera a que termine el await,
  //esto significa que todas las peticiones se lanzarian a la vez
  for (let el of placeholders) {
    //.getAttribute()-> metodo estandar del DOM que sirve para leer
    //cualqier atributo HTML de un elemento
    const name = el.getAttribute("data-partial");
    const resp = await fetch(`/partials/${name}`);
    el.innerHTML = await resp.text();
  }
}
//El codigo depende del DOM (por elementos como .slide). Si se
// intentara acceder a ellos antes de que existan en la pagina, daria error.
window.addEventListener('DOMContentLoaded',async() => {
  await loadPartials();
  initDeck();
  refreshState();
});

// Exposicion del refreshState global
window.refreshState = refreshState;
