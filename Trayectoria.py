import colorsys
import numpy as np
import pandas as pd
from pvlib import solarposition, location, irradiance


class Trayectoria:
    def __init__(self, lat, lon, tz, proyeccion):
        self.lat = float(lat)
        self.lon = float(lon)
        self.tz = tz
        self.proyeccion = proyeccion

    # Helpers
    def _esta_dentro(self, u, v, elev):
        return (
            np.isfinite(u)
            and np.isfinite(v)
            and np.isfinite(elev)
            and elev > 0
            and 0 <= u < self.proyeccion.width
            and 0 <= v < self.proyeccion.height
        )

    def _posiciones_sol(self, tiempos):

        #Versión vectorizada: acepta uno o varios tiempos y devuelve arrays.

        solpos = solarposition.get_solarposition(tiempos, self.lat, self.lon)
        az = solpos.azimuth.values
        el = solpos.apparent_elevation.values

        u, v = self.proyeccion.vectors2pixels(az, el)
        u = np.array(u, dtype=float)
        v = np.array(v, dtype=float)
        el = np.array(el, dtype=float)

        return u, v, el

    def _posicion_sol(self, tiempo):

        #Versión escalar: acepta un único tiempo y devuelve escalares.

        tiempos = pd.DatetimeIndex([tiempo])
        u, v, el = self._posiciones_sol(tiempos)
        return float(u[0]), float(v[0]), float(el[0])

    def _refinar_cruce(self, t1, t2, dentro_en_t, iteraciones=15):
        for _ in range(iteraciones):
            tm = t1 + (t2 - t1) / 2
            um, vm, em = self._posicion_sol(tm)
            dentro_m = self._esta_dentro(um, vm, em)

            if dentro_m == dentro_en_t:
                t1 = tm
            else:
                t2 = tm

        t_final = t1 + (t2 - t1) / 2
        u_final, v_final, e_final = self._posicion_sol(t_final)
        return t_final, u_final, v_final, e_final

    def buscar_entrada_salida_sol(self, t0, margen_horas=12, paso_grueso_min=5):

        inicio = t0 - pd.Timedelta(hours=margen_horas)
        fin = t0 + pd.Timedelta(hours=margen_horas)

        times = pd.date_range(
            start=inicio,
            end=fin,
            freq=f"{paso_grueso_min}min",
            tz=self.tz
        )

        u, v, el = self._posiciones_sol(times)

        dentro = np.array(
            [
                self._esta_dentro(ui, vi, ei)
                for ui, vi, ei in zip(u, v, el)
            ],
            dtype=bool
        )

        if not dentro.any():
            # El Sol no entra en la imagen durante ese día
            return None

        # ---------------------------------------------------------
        # Buscar todos los intervalos continuos en los que el Sol
        # permanece dentro de la imagen.
        # ---------------------------------------------------------

        intervalos = []
        inicio_intervalo = None

        for i, esta_dentro in enumerate(dentro):

            # Comienza un nuevo intervalo
            if esta_dentro and inicio_intervalo is None:
                inicio_intervalo = i

            # Termina el intervalo anterior
            if not esta_dentro and inicio_intervalo is not None:
                fin_intervalo = i - 1

                intervalos.append(
                    (inicio_intervalo, fin_intervalo)
                )

                inicio_intervalo = None

        # Si el último intervalo llega hasta el final del rango
        if inicio_intervalo is not None:
            intervalos.append(
                (inicio_intervalo, len(dentro) - 1)
            )

        if not intervalos:
            return None

        # ---------------------------------------------------------
        # Elegir el intervalo continuo más largo.
        # De esta forma no se unen tramos separados.
        # ---------------------------------------------------------

        idx_inicio_dentro, idx_fin_dentro = max(
            intervalos,
            key=lambda intervalo: intervalo[1] - intervalo[0]
        )

        # Necesitamos un punto exterior antes de la entrada
        # y otro después de la salida para poder refinar los cruces.
        if idx_inicio_dentro == 0:
            return None

        if idx_fin_dentro >= len(times) - 1:
            return None

        # ---------------------------------------------------------
        # Refinar la entrada
        #
        # idx_inicio_dentro - 1: fuera de la imagen
        # idx_inicio_dentro: dentro de la imagen
        # ---------------------------------------------------------

        t1_ent = times[idx_inicio_dentro - 1]
        t2_ent = times[idx_inicio_dentro]

        t_entrada, u_entrada, v_entrada, _ = self._refinar_cruce(
            t1_ent,
            t2_ent,
            dentro_en_t=False
        )

        # ---------------------------------------------------------
        # Refinar la salida
        #
        # idx_fin_dentro: dentro de la imagen
        # idx_fin_dentro + 1: fuera de la imagen
        # ---------------------------------------------------------

        t1_sal = times[idx_fin_dentro]
        t2_sal = times[idx_fin_dentro + 1]

        t_salida, u_salida, v_salida, _ = self._refinar_cruce(
            t1_sal,
            t2_sal,
            dentro_en_t=True
        )

        if t_salida <= t_entrada:
            return None

        return {
            "t_entrada": t_entrada,
            "u_entrada": u_entrada,
            "v_entrada": v_entrada,
            "t_salida": t_salida,
            "u_salida": u_salida,
            "v_salida": v_salida,
        }

    @staticmethod
    def es_azul(rgb):

        r, g, b = rgb

        # 1) Sol o brillo muy intenso
        if r > 200 and g > 200 and b > 200:
            return True

        # 2) Conversión a HSV
            # Convertimos a HSV
        r_n = r / 255.0
        g_n = g / 255.0
        b_n = b / 255.0

        h, s, v = colorsys.rgb_to_hsv(r_n, g_n, b_n)

        h *= 360
        s *= 100
        v *= 100

        # 3) Hue: solamente azules
        if not (195 <= h <= 240):
            return False

        # 4) Saturación mínima. Evita blancos, grises y muchas nubes.
        if s < 35:
            return False

        # 5) Brillo mínimo. Evita sombras muy oscuras.
        if v < 35:
            return False

        # 6) El azul debe dominar claramente
        if b < g + 10:
            return False

        if b < r + 25:
            return False


        return True

    def estimar_longitud_px(self, t_ini, t_fin, freq="1min"):
        times_g = pd.date_range(start=t_ini, end=t_fin, freq=freq, tz=t_ini.tz)
        if len(times_g) < 2:
            return 0.0

        u, v, _ = self._posiciones_sol(times_g)

        L = 0.0
        for i in range(1, len(times_g)):
            du = u[i] - u[i - 1]
            dv = v[i] - v[i - 1]
            L += np.hypot(du, dv)

        return L

    def calcular_ghi_poa_times(self, times, tilt, surf_az):
        site = location.Location(self.lat, self.lon, self.tz)

        # Clearsky (GHI, DNI, DHI) para esos tiempos
        clearsky = site.get_clearsky(times)

        # Posición solar
        solar_pos = site.get_solarposition(times=times)

        poa = irradiance.get_total_irradiance(
            surface_tilt=tilt,
            surface_azimuth=surf_az,
            dni=clearsky["dni"],
            ghi=clearsky["ghi"],
            dhi=clearsky["dhi"],
            solar_zenith=solar_pos["apparent_zenith"],
            solar_azimuth=solar_pos["azimuth"],
        )

        return poa

    def calcular_ghi_poa_time(self, tiempo, tilt, surf_az):
        site = location.Location(self.lat, self.lon, self.tz)

        times = pd.DatetimeIndex([tiempo])

        # Clearsky
        clearsky = site.get_clearsky(times)

        # Posición solar
        solar_pos = site.get_solarposition(times=times)

        poa = irradiance.get_total_irradiance(
            surface_tilt=tilt,
            surface_azimuth=surf_az,
            dni=clearsky["dni"],
            ghi=clearsky["ghi"],
            dhi=clearsky["dhi"],
            solar_zenith=solar_pos["apparent_zenith"],
            solar_azimuth=solar_pos["azimuth"],
        )

        # Devolvemos como escalares
        return {
            "poa_global": float(poa["poa_global"].iloc[0]),
            "poa_diffuse": float(poa["poa_diffuse"].iloc[0]),
        }