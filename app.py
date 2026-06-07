import os
import re
import io
import base64
from datetime import datetime

from flask import Flask, render_template, request, jsonify
import pandas as pd

from PIL import Image

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

from core import PhotoProjection
from Trayectoria import Trayectoria

#Flask crea una aplicacion web. app es la variable/centro de control de la aplicacion
#Imprescindible para definir rutas, ejecutar el servidor, encontrar recursos como
#plantillas o archivos estaticos, etc.
app = Flask(__name__)

#Declaramos 2 diccionarios para: el estado en memoria y los colores de las trayectorias
#mensuales.

#Para este proyecto, recurrimos a los diccionarios y no a las clases, porque encajan
#directamente con JSON, requieren menos codigos y son mas flexibles a la hora de
#trabajar con datos dinamicos

# Estado en memoria
STATE = {
    "latitud": None,
    "longitud": None,
    "fov": None,
    "iop_instant": None,
    "iop_width": None,
    "iop_height": None,
    "iop_pitch": None,
    "iop_heading": None,
    "iop_image_ok": False,
    "iop_image_url": None,
}

#colores de los meses
COLORES_MESES = {
    12: "#FFF9E6",  # blanco cálido invernal
    1:  "#FFF2CC",  # crema
    2:  "#FFE699",  # amarillo suave
    3:  "#FFD966",  # dorado
    4:  "#FFC000",  # amarillo intenso
    5:  "#F4B183",  # naranja suave
    6:  "#E69138",  # naranja cálido
}

#Cuando el cliente accede a la URL indicada, se ejecuta la funcion mostrada
@app.route("/")
def index():
    return render_template("index.html")
#render_template busca un archivo HTML en la carpeta templates, lee el archivo,
#convierte al archivo en una respuesta web, y, lo envia al navegador.

@app.route("/api/state")
def api_state():
    return jsonify({"ok": True, **STATE})


@app.route("/api/gps", methods=["POST"])
def api_gps():
    # request se emplea para leer datos que el cliente envia al servidor
    # en nuestro caso, con una peticion POST
    data = request.get_json(force=True)
    STATE["latitud"] = data.get("latitud")
    STATE["longitud"] = data.get("longitud")
    return jsonify(ok=True, msg="GPS actualizado")
    # devuelve al cliente un formato json

@app.route("/api/fov", methods=["POST"])
def api_fov():
    data = request.get_json(force=True)
    STATE["fov"] = data.get("fov")
    return jsonify(ok=True, msg="FOV actualizado")


@app.route("/api/iop", methods=["POST"])
def api_iop():
    data = request.get_json(force=True) or {}

    # Actualiza campos numéricos / string
    STATE["iop_instant"] = data.get("instant")
    STATE["iop_width"] = data.get("width")
    STATE["iop_height"] = data.get("height")
    STATE["iop_pitch"] = data.get("pitch")
    STATE["iop_heading"] = data.get("heading")

    # Procesamiento de imagen Data URL
    img_data_url = data.get("image")
    STATE["iop_image_ok"] = False
    STATE["iop_image_url"] = None

    if isinstance(img_data_url, str):
        #^ Indica el inicio del texto
        #data:image/ es el inicio tipico de una DATA URL de imagen
        #(png|jpeg) tipo de extension aceptable
        #;base64,  Indica que los datos están codificados en base64
        #(.+) Captura todo el contenido de base64
        m = re.match(r"^data:image/(png|jpeg);base64,(.+)$", img_data_url)
        if m:
            ext = "jpg" if m.group(1) == "jpeg" else "png"
            b64 = m.group(2)
            try:
                blob = base64.b64decode(b64)
                # Se construye una ruta de carpeta de forma segura, usando la
                # carpeta raiz de la aplicacion como punto de referencia.Posteriormente,
                # se crea la carpeta dentro del sistema
                up_dir = os.path.join(app.root_path, "static", "uploads")
                os.makedirs(up_dir, exist_ok=True)
                # El nombre del archivo con la extension .jpg o .png,
                # no eso otro que la variable temporal del instante en el que
                # se toma la foto del Sol
                stamp = STATE["iop_instant"] or datetime.utcnow().strftime("%d-%m-%Y_%H-%M-%S")
                fname = f"iop_{stamp}.{ext}"
                # Se sanitiza el nombre o se reemplaza cualquier caracter
                # que no sea seguro, por motivos de seguridad y compatibilidad
                fname = re.sub(r"[^a-zA-Z0-9_.-]", "_", fname)
                fpath = os.path.join(up_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(blob)
                STATE["iop_image_ok"] = True
                STATE["iop_image_url"] = f"/static/uploads/{fname}"
            except Exception as exc:
                print("Error guardando imagen:", exc)

    return jsonify(ok=True, msg="IOP actualizado")


@app.route("/partials/gps")
def partial_gps():
    return render_template("partials/gps.html")


@app.route("/partials/fov")
def partial_fov():
    return render_template("partials/fov.html")


@app.route("/partials/iop")
def partial_iop():
    return render_template("partials/iop.html")


@app.route("/partials/solution")
def partial_solution():
    return render_template("partials/solution.html")

# comprobacion del valor y/o de la nulidad de cada variable del Estado en Memoria
def _state_ready(state):
    for k, v in state.items():
        # Caso especial: la imagen debe ser True
        if k == "iop_image_ok":
            if not v:
                return False
        else:
            if v is None:
                return False
    return True

def _fmt_hms(td: pd.Timedelta) -> str:
    total = int(td.total_seconds())
    if total < 0:
        total = -total
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def _pixel_es_azul(img, u, v, ancho, alto, trayectoria):
    x = int(round(u))
    y = int(round(v))

    x = min(max(x, 0), ancho - 1)
    y = min(max(y, 0), alto - 1)

    rgb = img.getpixel((x, y))
    return trayectoria.es_azul(rgb)
# =====================================
# RUTA PRINCIPAL /api/solution
# =====================================

@app.route("/api/solution", methods=["POST"])
def api_solution():
    state = STATE
    if not _state_ready(state):
        return ("Imagen no disponible: faltan datos"
                " (GPS/FOV/IOP).", 400)

    # --- Gather values ---#
    lat = float(state["latitud"])
    lon = float(state["longitud"])
    fov = float(state["fov"])

    foto_ancho = int(state["iop_width"])
    foto_alto = int(state["iop_height"])
    _pitch = float(state["iop_pitch"])
    _heading = float(state["iop_heading"])
    hora_iso = state["iop_instant"]

    #Comprobacion de la disponibilidad de la ultima "image uploaded"
    #Es fundamental la funcion lstrip() porque si rel_path empezara
    #con "/" Flask lo interpretaria como una ruta absoluta
    rel_path = state.get("iop_image_url")
    if not rel_path:
        return ("Imagen no disponible: no hay captura.", 400)
    fs_path = os.path.join(app.root_path, rel_path.lstrip("/"))
    if not os.path.exists(fs_path):
        return ("Imagen no disponible: archivo no encontrado.", 404)

    img = Image.open(fs_path).convert("RGB")
    #img.thumbnail((1200, 1200))

    #DESFASE_HORAS = 6
    fecha_hora = pd.Timestamp(hora_iso, tz="UTC")

    #Instancia de PhotoProjection
    proyeccion = PhotoProjection(
        fov=fov,
        width=foto_ancho,
        height=foto_alto,
        h0=_heading,
        p0=_pitch
    )
    #Instancia de Trayectoria
    trayectoria = Trayectoria(lat=lat, lon=lon, tz="UTC", proyeccion=proyeccion)

    #Calcula de la posicion del Sol en coordenada (u,v) dentro de la propia imagen
    u, v, _ = trayectoria._posicion_sol(fecha_hora)

    #
    irradiancia_solar = 0.0

    # POA en el instante en el que se toma la foto
    poa_inst = trayectoria.calcular_ghi_poa_time(
        tiempo=fecha_hora,
        tilt=_pitch,
        surf_az=_heading,
    )

    # Comprobacion del color del pixel
    is_blue = _pixel_es_azul(img, u, v, foto_ancho, foto_alto, trayectoria)

    if is_blue:
        irradiancia_solar = poa_inst["poa_global"]
    else:
        irradiancia_solar = poa_inst["poa_diffuse"]
    #

    trayectorias_uv = []
    irradiacion_global = 0.0
    irradiacion_hoy = 0.0  # ← AQUÍ
    fecha_objetivo = fecha_hora.date()  # ← Y AQUÍ

    # "start" representa el solsticio de invierno, y "end", el de verano
    start = fecha_hora.replace(year=2025, month=12, day=21)
    end = fecha_hora.replace(year=2026, month=6, day=21)

    tracks_dir = os.path.join(app.root_path, "static", "tracks")
    os.makedirs(tracks_dir, exist_ok=True)

    stamp_foto = (hora_iso.replace(":", "-") if hora_iso
                  else datetime.utcnow().strftime("%d-%m-%Y_%H-%M-%S"))
    fname_out = f"trayectorias_{stamp_foto}.txt"
    fname_out = re.sub(r"[^a-zA-Z0-9_.-]", "_", fname_out)
    fpath_out = os.path.join(tracks_dir, fname_out)

    # Se usa para gestionar recursos automaticamente (abrir archivos, establecer
    # conexiones, etc ), garantizando el cierre del archivo aunque existan errores.
    with open(fpath_out, "w", encoding="utf-8") as f:

        for fecha_hora_k in pd.date_range(start=start, end=end, freq="1D", tz="UTC"):

            t_entrada = t_salida = None
            u_entrada = v_entrada = None
            u_salida = v_salida = None

            # try-except, similar al try-catch de js. Ambas manejan excepciones (errores)
            # durante la ejecucion de un programa sin que se detenga por completo
            try:
                resultado = trayectoria.buscar_entrada_salida_sol(
                    t0=fecha_hora_k,
                    margen_horas=12,
                    paso_grueso_min=5
                )

                if resultado is None:
                    print(f"[SOL] El sol no entra en la imagen (t0={fecha_hora_k.isoformat()}).")
                    continue

                t_entrada = resultado["t_entrada"]
                u_entrada = resultado["u_entrada"]
                v_entrada = resultado["v_entrada"]
                t_salida = resultado["t_salida"]
                u_salida = resultado["u_salida"]
                v_salida = resultado["v_salida"]

            except Exception as e:
                print(f"[ERROR] calculando entrada/salida del sol:", e)
                continue

            if (t_entrada is None) or (t_salida is None) or (t_salida <= t_entrada):
                print("[TRAYECTORIA] No se genera: tiempos no válidos.")
                continue
            # Rango de fechas y horas (DatetimeIndex) con un intervalo de tiempo ajustable
            times_i = pd.date_range(start=t_entrada, end=t_salida, freq="30min", tz="UTC")
            if len(times_i) < 2:
                print("[TRAYECTORIA] No se genera: intervalo corto.")
                continue

            try:
                poa_df = trayectoria.calcular_ghi_poa_times(
                    times=times_i,
                    tilt=_pitch,
                    surf_az=_heading,
                )
            except Exception as e:
                print("[ERROR] calculando GHI/POA:", e)
                continue

            poa_vals = [None] * len(times_i)
            valid = [False] * len(times_i)
            lista_u = []
            lista_v = []

            try:
                for i, t_i in enumerate(times_i):
                    u_i, v_i, el_i = trayectoria._posicion_sol(t_i)

                    lista_u.append(u_i)
                    lista_v.append(v_i)

                    dentro_i = trayectoria._esta_dentro(u_i, v_i, el_i)
                    if not dentro_i:
                        continue

                    is_blue = _pixel_es_azul(img, u_i, v_i, foto_ancho, foto_alto, trayectoria)

                    if is_blue:
                        poa_t = float(poa_df["poa_global"].iloc[i])
                    else:
                        poa_t = float(poa_df["poa_diffuse"].iloc[i])

                    poa_vals[i] = poa_t
                    valid[i] = True

            except Exception as e:
                print("[ERROR] generando datos de trayectoria:", e)
                f.write("*" * 80 + "\n")
                f.write("*" * 80 + "\n\n")
                continue

            # --- Integración (irradiancia_total) ---
            irradiacion_total = 0.0
            for i in range(len(times_i) - 1):
                if not (valid[i] and valid[i + 1]):
                    continue
                dt_h = (times_i[i + 1] - times_i[i]).total_seconds() / 3600.0
                irradiacion_total += 0.5 * (poa_vals[i] + poa_vals[i + 1]) * dt_h

            irradiacion_global += irradiacion_total

            # Dibujar los dias 21 de cada mes
            if len(lista_u) >= 2 and fecha_hora_k.day == 21:
                mes = int(fecha_hora_k.month)
                color = COLORES_MESES.get(mes, "#FFFFFF")  # fallback
                trayectorias_uv.append((fecha_hora_k, lista_u, lista_v, color))
            # Dibujar si coincide con el dia de hoy
            if len(lista_u) >= 2 and fecha_hora_k.date() == fecha_objetivo:
                color = "#FFCC00"  # Amarillo Solar Intenso
                trayectorias_uv.append((fecha_hora_k, lista_u, lista_v, color))
                irradiacion_hoy = irradiacion_total

            dt_tray = (t_salida - t_entrada)

            # Escritura en fichero
            f.write(f"TRAYECTORIA    {fecha_hora_k.strftime('%d/%m/%Y')}\n")

            # 1) Coordenadas de entrada/salida
            f.write(
                f"1) (ue, ve) = ({u_entrada:.2f}, {v_entrada:.2f})"
                f"    -    (us, vs) = ({u_salida:.2f}, {v_salida:.2f})\n"
            )

            # 2) Tiempos de entrada/salida y diferencia
            t_ent_str = t_entrada.tz_convert("UTC").strftime("%H:%M")
            t_sal_str = t_salida.tz_convert("UTC").strftime("%H:%M")
            f.write(
                f"2) t_entrada = {t_ent_str}"
                f"    -    t_salida = {t_sal_str}"
                f"    -    Diferencia de tiempo = {_fmt_hms(dt_tray)}\n"
            )

            # 3) Irradiancias
            f.write(
                f"3) Irradiancia_global = {irradiacion_global:.2f}"
                f"    -    Irradiancia_total = {irradiacion_total:.2f}\n"
            )

            f.write("*" * 80 + "\n")
            f.write("*" * 80 + "\n\n")

    # --- Draw overlay --- #
    fig, ax = plt.subplots()
    ax.imshow(img)

    for (t_base, tu, tv, color) in trayectorias_uv:
        ax.plot(
            tu, tv,
            linewidth=2,
            color=color,
            marker="o",
            markersize=3,
            markeredgewidth=0
        )

    ax.scatter([u], [v], s=400, c="#FFCC00", edgecolors="black", linewidths=2.0, zorder=10)
    ax.axis('off')

    output = io.BytesIO()
    canvas = FigureCanvas(fig)
    canvas.print_png(output)
    output.seek(0)
    img_b64 = base64.b64encode(output.read()).decode('utf-8')
    plt.close(fig)

    return jsonify({
        "image": f"data:image/png;base64,{img_b64}",
        "irradiancia_solar":irradiancia_solar,
        "irradiacion_hoy":irradiacion_hoy,
        "irradiacion_global":irradiacion_global
    })


@app.after_request
def add_no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp

if __name__ == "__main__":
    #app.run(debug=True)
    port = int(os.environ.get("PORT", 5000))
    app.run( host="0.0.0.0", port=port, debug=True )