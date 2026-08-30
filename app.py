import os
import re
import io
import base64
from datetime import datetime

from flask import Flask, render_template, request, jsonify, session
import pandas as pd

from PIL import Image

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

from core import PhotoProjection
from trayectory import Trajectory

#Flask crea una aplicacion web. app es la variable/centro de control de la aplicacion
#Imprescindible para definir rutas, ejecutar el servidor, encontrar recursos como
#plantillas o archivos estaticos, etc.
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# Estado por usuario mediante session de Flask.
# Cada navegador mantiene sus propios datos temporales, evitando problemas
# con variables globales en produccion.
SESSION_DEFAULTS = {
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

def get_session_state():
    return {k: session.get(k, v) for k, v in SESSION_DEFAULTS.items()}

def reset_session_state():
    for k, v in SESSION_DEFAULTS.items():
        session[k] = v
#colores de los meses
MONTH_COLORS = {
    12: "#FFF9E6",  # blanco cálido invernal
    1:  "#FFF2CC",  # crema
    2:  "#FFE699",  # amarillo suave
    3:  "#FFD966",  # dorado
    4:  "#FFC000",  # amarillo intenso
    5:  "#F4B183",  # naranja suave
    6:  "#E69138",  # naranja cálido

    7:  "#D97A2B",  # naranja verano
    8:  "#C96A1A",  # ámbar intenso
    9:  "#B85C0A",  # cobre
    10: "#996515",  # ocre otoñal
    11: "#C2A878",  # beige otoñal
}

#Cuando el cliente accede a la URL indicada, se ejecuta la funcion mostrada
@app.route("/")
def index():
    reset_session_state()
    return render_template("index.html")
#render_template busca un archivo HTML en la carpeta templates, lee el archivo,
#convierte al archivo en una respuesta web, y, lo envia al navegador.

@app.route("/api/state")
def api_state():
    return jsonify({"ok": True, **get_session_state()})


@app.route("/api/gps", methods=["POST"])
def api_gps():
    # request se emplea para leer datos que el cliente envia al servidor
    # en nuestro caso, con una peticion POST
    data = request.get_json(force=True)
    session["latitud"] = data.get("latitud")
    session["longitud"] = data.get("longitud")
    return jsonify(ok=True, msg="GPS actualizado")
    # devuelve al cliente un formato json

@app.route("/api/fov", methods=["POST"])
def api_fov():
    data = request.get_json(force=True)
    session["fov"] = data.get("fov")
    return jsonify(ok=True, msg="FOV actualizado")


@app.route("/api/iop", methods=["POST"])
def api_iop():
    data = request.get_json(force=True) or {}

    # Actualiza campos numéricos / string
    session["iop_instant"] = data.get("instant")
    session["iop_width"] = data.get("width")
    session["iop_height"] = data.get("height")
    session["iop_pitch"] = data.get("pitch")
    session["iop_heading"] = data.get("heading")

    # Procesamiento de imagen Data URL
    img_data_url = data.get("image")
    session["iop_image_ok"] = False
    session["iop_image_url"] = None

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
                stamp = session.get("iop_instant") or datetime.utcnow().strftime("%d-%m-%Y_%H-%M-%S")
                fname = f"iop_{stamp}.{ext}"
                # Se sanitiza el nombre o se reemplaza cualquier caracter
                # que no sea seguro, por motivos de seguridad y compatibilidad
                fname = re.sub(r"[^a-zA-Z0-9_.-]", "_", fname)
                fpath = os.path.join(up_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(blob)
                session["iop_image_ok"] = True
                session["iop_image_url"] = f"/static/uploads/{fname}"
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

def _pixel_is_blue(img, u, v, width, height, trajectory):
    x = int(round(u))
    y = int(round(v))

    x = min(max(x, 0), width - 1)
    y = min(max(y, 0), height - 1)

    rgb = img.getpixel((x, y))
    return trajectory.is_blue(rgb)
# =====================================
# RUTA PRINCIPAL /api/solution
# =====================================

@app.route("/api/solution", methods=["POST"])
def api_solution():
    state = get_session_state()
    if not _state_ready(state):
        return ("Imagen no disponible: faltan datos"
                " (GPS/FOV/IOP).", 400)

    # --- Gather values ---#
    lat = float(state["latitud"])
    lon = float(state["longitud"])
    fov = float(state["fov"])

    photo_width = int(state["iop_width"])
    photo_height = int(state["iop_height"])
    _pitch = float(state["iop_pitch"])
    _heading = float(state["iop_heading"])
    iso_time = state["iop_instant"]

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

    #DESFASE_HORAS = 9
    #capture_datetime = pd.Timestamp(iso_time, tz="UTC") - pd.Timedelta(hours=DESFASE_HORAS)
    capture_datetime = pd.Timestamp(iso_time, tz="UTC")

    #Instancia de PhotoProjection
    projection = PhotoProjection(
        fov=fov,
        width=photo_width,
        height=photo_height,
        h0=_heading,
        p0=_pitch
    )
    #Instancia de Trayectoria
    trajectory = Trajectory(lat=lat, lon=lon, tz="UTC", projection=projection)

    #Calcula de la posicion del Sol en coordenada (u,v) dentro de la propia imagen
    u, v, _ = trajectory._sun_position(capture_datetime)

    #
    solar_irradiance = 0.0

    # POA en el instante en el que se toma la foto
    poa_inst = trajectory.calculate_ghi_poa_time(
        time=capture_datetime,
        tilt=_pitch,
        surf_az=_heading,
    )

    # Comprobacion del color del pixel
    is_blue = _pixel_is_blue(img, u, v, photo_width, photo_height, trajectory)

    if is_blue:
        solar_irradiance = poa_inst["poa_global"]
    else:
        solar_irradiance = poa_inst["poa_diffuse"]
    #

    uv_trajectories = []
    global_irradiation = 0.0
    today_irradiation = 0.0  # ← AQUÍ
    target_date = capture_datetime.date()  # ← Y AQUÍ
    today_iteration_data = {}
    days_sun_enters_image = 0
    today_duration_min = None

    actual_year = capture_datetime.year
    actual_month = capture_datetime.month
    actual_day = capture_datetime.day

    # 1) Entre 1 Ene y 21 Jun
    if (
            actual_month < 6
            or (actual_month == 6 and actual_day <= 21)
    ):
        start = capture_datetime.replace(
            year=actual_year - 1,
            month=12,
            day=21
        )
        end = capture_datetime.replace(
            year=actual_year,
            month=6,
            day=21
        )

    # 2) Entre 22 Jun y 21 Dic
    elif (
            actual_month < 12
            or (actual_month == 12 and actual_day <= 21)
    ):
        start = capture_datetime.replace(
            year=actual_year,
            month=6,
            day=21
        )
        end = capture_datetime.replace(
            year=actual_year,
            month=12,
            day=21
        )

    # 3) Entre 22 Dic y 31 Dic
    else:
        start = capture_datetime.replace(
            year=actual_year,
            month=12,
            day=21
        )
        end = capture_datetime.replace(
            year=actual_year + 1,
            month=6,
            day=21
        )

    tracks_dir = os.path.join(app.root_path, "static", "tracks")
    os.makedirs(tracks_dir, exist_ok=True)

    photo_stamp = (iso_time.replace(":", "-") if iso_time
                  else datetime.utcnow().strftime("%d-%m-%Y_%H-%M-%S"))
    fname_out = f"trajectories_{photo_stamp}.txt"
    fname_out = re.sub(r"[^a-zA-Z0-9_.-]", "_", fname_out)
    fpath_out = os.path.join(tracks_dir, fname_out)

    # Se usa para gestionar recursos automaticamente (abrir archivos, establecer
    # conexiones, etc ), garantizando el cierre del archivo aunque existan errores.
    with open(fpath_out, "w", encoding="utf-8") as f:

        for day_datetime in pd.date_range(start=start, end=end, freq="1D", tz="UTC"):

            entry_time = exit_time = None
            entry_u = entry_v = None
            exit_u = exit_v = None

            # try-except, similar al try-catch de js. Ambas manejan excepciones (errores)
            # durante la ejecucion de un programa sin que se detenga por completo
            try:
                result = trajectory.find_sun_entry_exit(
                    t0=day_datetime,
                    margin_hours=12,
                    coarse_step_min=5
                )

                if result is None:
                    print(f"[SOL] El sol no entra en la imagen (t0={day_datetime.isoformat()}).")
                    continue

                days_sun_enters_image += 1

                entry_time = result["entry_time"]
                entry_u = result["entry_u"]
                entry_v = result["entry_v"]
                exit_time = result["exit_time"]
                exit_u = result["exit_u"]
                exit_v = result["exit_v"]

            except Exception as e:
                print(f"[ERROR] calculando entrada/salida del sol:", e)
                continue

            if (entry_time is None) or (exit_time is None) or (exit_time <= entry_time):
                print("[TRAYECTORIA] No se genera: tiempos no válidos.")
                continue
            # Rango de fechas y horas (DatetimeIndex) con un intervalo de tiempo ajustable
            times_i = pd.date_range(start=entry_time, end=exit_time, freq="30min", tz="UTC")
            if len(times_i) < 2:
                print("[TRAYECTORIA] No se genera: intervalo corto.")
                continue

            try:
                poa_df = trajectory.calculate_ghi_poa_times(
                    times=times_i,
                    tilt=_pitch,
                    surf_az=_heading,
                )
            except Exception as e:
                print("[ERROR] calculando GHI/POA:", e)
                continue

            poa_vals = [None] * len(times_i)
            valid = [False] * len(times_i)
            u_list = []
            v_list = []
            is_photo_day = day_datetime.date() == target_date

            try:
                for i, t_i in enumerate(times_i):
                    u_i, v_i, el_i = trajectory._sun_position(t_i)

                    #u_list.append(u_i)
                    #v_list.append(v_i)

                    inside_i = trajectory._is_inside(u_i, v_i, el_i)
                    if not inside_i:
                        continue

                    u_list.append(u_i)
                    v_list.append(v_i)

                    is_blue = _pixel_is_blue(img, u_i, v_i, photo_width, photo_height, trajectory)

                    if is_photo_day:
                        today_iteration_data[i + 1] = {
                            "t_i": t_i.strftime("%d/%m/%Y %H:%M"),
                            "u_i": float(u_i),
                            "v_i": float(v_i),
                            "is_blue": bool(is_blue),
                        }

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
            total_irradiation = 0.0
            for i in range(len(times_i) - 1):
                if not (valid[i] and valid[i + 1]):
                    continue
                dt_h = (times_i[i + 1] - times_i[i]).total_seconds() / 3600.0
                total_irradiation += 0.5 * (poa_vals[i] + poa_vals[i + 1]) * dt_h

            global_irradiation += total_irradiation

            # Dibujar los dias 21 de cada mes
            if len(u_list) >= 2 and day_datetime.day == 21:
                month = int(day_datetime.month)
                color = MONTH_COLORS.get(month, "#FFFFFF")  # fallback
                uv_trajectories.append((day_datetime, u_list, v_list, color))
            # Dibujar si coincide con el dia de hoy
            if len(u_list) >= 2 and day_datetime.date() == target_date:
                color = "#FFCC00"  # Amarillo Solar Intenso
                uv_trajectories.append((day_datetime, u_list, v_list, color))
                today_irradiation = total_irradiation

            trajectory_duration = (exit_time - entry_time)

            if day_datetime.date() == target_date:
                today_duration_min = round(trajectory_duration.total_seconds() / 60)

            # Escritura en fichero
            f.write(f"TRAYECTORIA    {day_datetime.strftime('%d/%m/%Y')}\n")

            # 1) Coordenadas de entrada/salida
            f.write(
                f"1) (ue, ve) = ({entry_u:.2f}, {entry_v:.2f})"
                f"    -    (us, vs) = ({exit_u:.2f}, {exit_v:.2f})\n"
            )

            # 2) Tiempos de entrada/salida y diferencia
            entry_time_str = entry_time.tz_convert("UTC").strftime("%H:%M")
            exit_time_str = exit_time.tz_convert("UTC").strftime("%H:%M")
            f.write(
                f"2) t_entrada = {entry_time_str}"
                f"    -    t_salida = {exit_time_str}"
                f"    -    Diferencia de tiempo = {_fmt_hms(trajectory_duration)}\n"
            )

            # 3) Irradiancias
            f.write(
                f"3) Irradiacion_global = {global_irradiation:.2f}"
                f"    -    Irradiacion_total = {total_irradiation:.2f}\n"
            )

            f.write("*" * 80 + "\n")
            f.write("*" * 80 + "\n\n")

    # --- Draw overlay --- #
    fig, ax = plt.subplots()
    ax.imshow(img)

    ax.set_xlim(0, photo_width)
    ax.set_ylim(photo_height, 0)

    for (t_base, tu, tv, color) in uv_trajectories:
        ax.plot(
            tu, tv,
            linewidth=2,
            color=color,
            marker="o",
            markersize=8,
            markeredgewidth=0
        )

    ax.scatter([u], [v], s=700, c="#FFCC00", edgecolors="black", linewidths=2.0, zorder=10)
    ax.axis('off')

    output = io.BytesIO()
    canvas = FigureCanvas(fig)
    canvas.print_png(output)
    output.seek(0)
    img_b64 = base64.b64encode(output.read()).decode('utf-8')
    plt.close(fig)

    return jsonify({
        "image": f"data:image/png;base64,{img_b64}",
        "solar_irradiance": solar_irradiance,
        "today_irradiation": today_irradiation,
        "global_irradiation": global_irradiation,
        "today_iteration_data": today_iteration_data,
        "today_duration_min": today_duration_min,
        "days_sun_enters_image": days_sun_enters_image
    })


@app.after_request
def add_no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp

if __name__ == "__main__":
    #app.run(debug=True)
    port = int(os.environ.get("PORT", 5000))
    app.run( host="0.0.0.0", port=port, debug=True )