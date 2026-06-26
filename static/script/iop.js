let iopStream = null;
let iopSensorsOn = false;

let lastPitch = null;
let lastHeading = null;
let stableHeading = null;

let rafPending = false;

// Offset SOLO para pitch
const PITCH_OFFSET = -90;

// Normaliza un angulo para que siempre quede en el rango de 0 a 360 grados
// Convierte valores negativos o mayores a 360° en su equivalente circular positivo
function normalizeDeg(x) { return ((x % 360) + 360) % 360; }
//Normaliza un angulo para que quede en el rango de -180 a 180 grados
function normalizeAngle(angle) { return ((angle + 180) % 360 + 360) % 360 - 180; }

function angleDiff(a, b) { return normalizeAngle(a - b); }

// Obtiene el angulo de rotacion de la pantalla del dispositivo movil
function getScreenAngle() {
  // screen.orientation.angle -> devuelve 0, 90, 180, 270. No todos los
  // navegadores lo soportan bien (especialmente iOS).
  // window.orientation -> usados en moviles antiguos / Safari. Puede
  // devolver (0, 90, -90, 180)
  const so = screen.orientation && typeof screen.orientation.angle === "number"
    ? screen.orientation.angle
    : (typeof window.orientation === "number" ? window.orientation : 0);
  return so || 0;
}

function computeHeadingFromEvent(e) {
  // Uso de la brujula nativa de IOS. Como referencia tomamos
  // el rumbo respecto al norte real. Si la precision es poco fiable
  // el valor se desprecia.
  const acc = e.webkitCompassAccuracy;
  if (typeof e.webkitCompassHeading === "number") {
    if (typeof acc === "number" && acc > 50) return null; // precisión pobre
    return normalizeDeg(e.webkitCompassHeading);
  }
  // Si no usa los sensores genericos.
  if (e.absolute === true && typeof e.alpha === "number") {
    // Corrige el heading segun la orientacion del movil
    const a = normalizeDeg(e.alpha - getScreenAngle());
    return normalizeDeg(360 - a);
  }
  return null;
}
//
function stabilizeHeading(newHeading, pitch) {

  if (stableHeading === null) {
    stableHeading = newHeading;
    return stableHeading;
  }

  const diff = angleDiff(newHeading, stableHeading);
  const absDiff = Math.abs(diff);
  // Muy inclinado -> brújula menos fiable
  const veryTilted = typeof pitch === "number" && Math.abs(pitch) > 110;
  // Salto sospechoso
  if (veryTilted && absDiff > 45) { return stableHeading; }
  // Filtro adaptativo
  const alpha = absDiff > 15 ? 0.25 : 0.08;

  stableHeading = normalizeDeg(stableHeading + alpha * diff );

  return stableHeading;
}

// Manejo de la orientacion del dispositivo. Calculo, actualizacion y
// exposicion en elementos del DOM, de los valores de inclinacion y rumbo.
function onDeviceOrientation(e) {
  if (rafPending) return;
  rafPending = true;
  //Limita la ejecucion de la funcion con el proposito de evitar llamadas
  //excesivas
  requestAnimationFrame(() => {
    rafPending = false;
    lastPitch = (typeof e.beta === "number") ? Math.round(e.beta * 10) / 10 : null;

    const rawHeading = computeHeadingFromEvent(e);

    if (typeof rawHeading === "number") {
      lastHeading = Math.round(stabilizeHeading(rawHeading, e.beta));
    } else {
      lastHeading = null;
    }

    const s = document.querySelector("#iop-sensor");
    if (s) s.textContent = `pitch: ${lastPitch ?? "—"} | heading: ${lastHeading ?? "—"}`;
  });
}
// Activa los sensores de orientacion añadiendo los listeners a las
// funciones correspondientes.
function enableSensors() {
  if (iopSensorsOn) return;
  window.addEventListener("deviceorientation", onDeviceOrientation, false);
  window.addEventListener("deviceorientationabsolute", onDeviceOrientation, false);
  iopSensorsOn = true;
}
function disableSensors() {
  if (!iopSensorsOn) return;
  window.removeEventListener("deviceorientation", onDeviceOrientation, false);
  window.removeEventListener("deviceorientationabsolute", onDeviceOrientation, false);
  iopSensorsOn = false;
}

async function startCamera() {
  if (iopStream) return;
  //Variable que guarda el stream del video capturado desde la
  // camara para poder reutilizarlo. Es importante (no viene por defecto)
  // que vamos a usar la camara trasera del dispositivo
  iopStream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" } },
    audio: false
  });
  const v = document.querySelector("#iop-video");
  if (v) {
    v.srcObject = iopStream;
    // Se ejecuta cuando el video ya tiene sus datos cargados
    v.onloadedmetadata = () => {
      const snap = document.querySelector("#iop-snapshot");
      if (snap) snap.disabled = !(v.videoWidth > 0 && v.videoHeight > 0);
    };
  }
}

function stopCamera() {
  if (!iopStream) return;
  // Un track es una pista individual de datos (audio o video)
  // dentro de un MediaStream. La funcion getTracks() devuelve todos
  // los tracks del stream en formato array.
  for (const tr of iopStream.getTracks()) tr.stop();
  iopStream = null;
  const snap = document.querySelector("#iop-snapshot");
  if (snap) snap.disabled = true;
}

function resetSensorLabel() {
  const s = document.querySelector("#iop-sensor");
  if (s) s.textContent = "pitch: — | heading: —";
}

async function takeSnapshotAndSend() {
  const v = document.querySelector("#iop-video");
  const c = document.querySelector("#iop-canvas");
  if (!v || !c || v.videoWidth === 0 || v.videoHeight === 0) return;

  //Canvas funciona como una superficie interna del dibujo que el usuario
  //no ve. Copia el frame del video y lo dibuja dentro del propio canvas.
  c.width = v.videoWidth;
  c.height = v.videoHeight;
  const ctx = c.getContext("2d");
  ctx.drawImage(v, 0, 0, c.width, c.height);

  // A continuacion, el canvas se convierte en imagen
  const dataUrl = c.toDataURL("image/jpeg", 0.85);

  // AJUSTE SOLO AL PITCH: aplicamos offset -90°, normalizamos y enviamos esa cifra
  let pitchForServer = null;
  if (typeof lastPitch === "number") {
    pitchForServer = normalizeAngle(lastPitch + PITCH_OFFSET);
  }

  // Contencion de todos los datos relevantes del momento en el que se hace
  // la foto. Se puede asemejar a un paquete de datos.
  // payload es un objeto de JS con estructura de pares clave-valor
  const payload = {
    instant: new Date().toISOString(),
    width: c.width,
    height: c.height,
    pitch: pitchForServer,
    heading: (typeof lastHeading === "number") ? lastHeading : null,
    image: dataUrl
  };

  try {
    const resp = await fetch("/api/iop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    await resp.json();
    const img = document.querySelector("#iop-preview");
    // Se asigna la imagen en formato base64 al elemento <img>
    // 'block' desactiva la ocultacion del elemento
    if (img) { img.src = dataUrl; img.style.display = "block"; }
    await window.refreshState?.();
  } catch (err) {
    console.error("Error enviando IOP", err);
  }
}

// La clave es: pedir permiso de orientación antes de cualquier await
document.addEventListener("click", async (e) => {
  if (e.target && e.target.id === "iop-start") {
    const btn = e.target;


    if (!iopSensorsOn || !iopStream) {
      try {
        // Permiso de orientación dentro del gesto de usuario
        if ("DeviceOrientationEvent" in window &&
            typeof DeviceOrientationEvent.requestPermission === "function") {
          const perm = await DeviceOrientationEvent.requestPermission();
          if (perm !== "granted") {
            alert("Permiso de orientación denegado.");
            return;
          }
        }
        // Activacion de sensores inmediata
        enableSensors();

        // Arranca la cámara. Puede resolverse después porque ya no afecta al gesto.
        startCamera().catch(err => {
          alert("No se pudo abrir la cámara: " + err.message);
          console.error(err);
        });

        btn.textContent = "Stop";
      } catch (err) {
        alert("No se pudieron activar los sensores: " + err.message);
        console.error(err);
      }
    } else {
      // Si para todo, si estan activos
      disableSensors();
      stopCamera();
      resetSensorLabel();
      btn.textContent = "Start";
    }
  }

  if (e.target && e.target.id === "iop-snapshot") {
    await takeSnapshotAndSend();
  }
});