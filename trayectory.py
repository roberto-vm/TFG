import colorsys
import numpy as np
import pandas as pd
from pvlib import solarposition, location, irradiance


class Trajectory:
    def __init__(self, lat, lon, tz, projection):
        self.lat = float(lat)
        self.lon = float(lon)
        self.tz = tz
        self.projection = projection

    # Helpers
    def _is_inside(self, u, v, elev):
        return (
            np.isfinite(u)
            and np.isfinite(v)
            and np.isfinite(elev)
            and elev > 0
            and 0 <= u < self.projection.width
            and 0 <= v < self.projection.height
        )

    def _sun_positions(self, times):

        #Versión vectorizada: acepta uno o varios tiempos y devuelve arrays.

        solpos = solarposition.get_solarposition(times, self.lat, self.lon)
        az = solpos.azimuth.values
        el = solpos.apparent_elevation.values

        u, v = self.projection.vectors2pixels(az, el)
        u = np.array(u, dtype=float)
        v = np.array(v, dtype=float)
        el = np.array(el, dtype=float)

        return u, v, el

    def _sun_position(self, time):

        #Versión escalar: acepta un único tiempo y devuelve escalares.

        times = pd.DatetimeIndex([time])
        u, v, el = self._sun_positions(times)
        return float(u[0]), float(v[0]), float(el[0])

    def _refine_crossing(self, t1, t2, inside_at_t, iterations=15):
        for _ in range(iterations):
            tm = t1 + (t2 - t1) / 2
            um, vm, em = self._sun_position(tm)
            inside_mid = self._is_inside(um, vm, em)

            if inside_mid == inside_at_t:
                t1 = tm
            else:
                t2 = tm

        final_time = t1 + (t2 - t1) / 2
        final_u, final_v, final_e = self._sun_position(final_time)
        return final_time, final_u, final_v, final_e

    def find_sun_entry_exit(self, t0, margin_hours=12, coarse_step_min=5):

        start = t0 - pd.Timedelta(hours=margin_hours)
        end = t0 + pd.Timedelta(hours=margin_hours)

        times = pd.date_range(
            start=start,
            end=end,
            freq=f"{coarse_step_min}min",
            tz=self.tz
        )

        u, v, el = self._sun_positions(times)

        inside = np.array(
            [
                self._is_inside(ui, vi, ei)
                for ui, vi, ei in zip(u, v, el)
            ],
            dtype=bool
        )

        if not inside.any():
            # El Sol no entra en la imagen durante ese día
            return None

        # ---------------------------------------------------------
        # Buscar todos los intervalos continuos en los que el Sol
        # permanece dentro de la imagen.
        # ---------------------------------------------------------

        intervals = []
        interval_start = None

        for i, is_inside in enumerate(inside):

            # Comienza un nuevo intervalo
            if is_inside and interval_start is None:
                interval_start = i

            # Termina el intervalo anterior
            if not is_inside and interval_start is not None:
                interval_end = i - 1

                intervals.append(
                    (interval_start, interval_end)
                )

                interval_start = None

        # Si el último intervalo llega hasta el final del rango
        if interval_start is not None:
            intervals.append(
                (interval_start, len(inside) - 1)
            )

        if not intervals:
            return None

        # ---------------------------------------------------------
        # Elegir el intervalo continuo más largo.
        # De esta forma no se unen tramos separados.
        # ---------------------------------------------------------

        inside_start_idx, inside_end_idx = max(
            intervals,
            key=lambda interval: interval[1] - interval[0]
        )

        # Necesitamos un punto exterior antes de la entrada
        # y otro después de la salida para poder refinar los cruces.
        if inside_start_idx == 0:
            return None

        if inside_end_idx >= len(times) - 1:
            return None

        # ---------------------------------------------------------
        # Refinar la entrada
        #
        # inside_start_idx - 1: fuera de la imagen
        # inside_start_idx: dentro de la imagen
        # ---------------------------------------------------------

        entry_t1 = times[inside_start_idx - 1]
        entry_t2 = times[inside_start_idx]

        entry_time, entry_u, entry_v, _ = self._refine_crossing(
            entry_t1,
            entry_t2,
            inside_at_t=False
        )

        # ---------------------------------------------------------
        # Refinar la salida
        #
        # inside_end_idx: dentro de la imagen
        # inside_end_idx + 1: fuera de la imagen
        # ---------------------------------------------------------

        exit_t1 = times[inside_end_idx]
        exit_t2 = times[inside_end_idx + 1]

        exit_time, exit_u, exit_v, _ = self._refine_crossing(
            exit_t1,
            exit_t2,
            inside_at_t=True
        )

        if exit_time <= entry_time:
            return None

        return {
            "entry_time": entry_time,
            "entry_u": entry_u,
            "entry_v": entry_v,
            "exit_time": exit_time,
            "exit_u": exit_u,
            "exit_v": exit_v,
        }

    @staticmethod
    def is_blue(rgb):

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

    def estimate_length_px(self, start_time, end_time, freq="1min"):
        sample_times = pd.date_range(start=start_time, end=end_time, freq=freq, tz=start_time.tz)
        if len(sample_times) < 2:
            return 0.0

        u, v, _ = self._sun_positions(sample_times)

        length = 0.0
        for i in range(1, len(sample_times)):
            du = u[i] - u[i - 1]
            dv = v[i] - v[i - 1]
            length += np.hypot(du, dv)

        return length

    def calculate_ghi_poa_times(self, times, tilt, surf_az):
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

    def calculate_ghi_poa_time(self, time, tilt, surf_az):
        site = location.Location(self.lat, self.lon, self.tz)

        times = pd.DatetimeIndex([time])

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