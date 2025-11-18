import pandas as pd
from difflib import get_close_matches
import logging
import math

logging.basicConfig(level=logging.INFO)

class SICETACHelper:
    def __init__(self, archivo_municipios):
        self.df_municipios = pd.read_excel(archivo_municipios)
        self.columnas_municipios = ['nombre_oficial', 'variacion_1', 'variacion_2', 'variacion_3']
        self.codigo_municipio_col = 'codigo_dane'

    def buscar_municipio(self, nombre_input):
        resultado = self._buscar_codigo(
            self.df_municipios,
            nombre_input,
            self.columnas_municipios,
            self.codigo_municipio_col,
            ['departamento', 'nombre_oficial']
        )
        if resultado:
            logging.info(f"✔ Municipio encontrado: {resultado}")
        else:
            logging.warning(f"✘ Municipio NO encontrado: {nombre_input}")
        return resultado

    def _buscar_codigo(self, df, nombre_input, columnas_nombres, codigo_col, extra_cols=None):
        nombre_input = str(nombre_input).strip().upper()
        for col in columnas_nombres:
            if col in df.columns:
                match = df[df[col].astype(str).str.upper().fillna('') == nombre_input]
                if not match.empty:
                    row = match.iloc[0]
                    result = {codigo_col: row[codigo_col]}
                    if extra_cols:
                        for c in extra_cols:
                            if c in row:
                                result[c] = row[c]
                    return result

        for col in columnas_nombres:
            if col in df.columns:
                opciones = df[col].dropna().astype(str).str.upper().unique().tolist()
                cercanos = get_close_matches(nombre_input, opciones, n=1, cutoff=0.8)
                if cercanos:
                    match = df[df[col].astype(str).str.upper() == cercanos[0]]
                    if not match.empty:
                        row = match.iloc[0]
                        result = {codigo_col: row[codigo_col]}
                        if extra_cols:
                            for c in extra_cols:
                                if c in row:
                                    result[c] = row[c]
                        result['coincidencia_aproximada'] = cercanos[0]
                        return result
        return None

    def ruta_existe(self, origen_input, destino_input, df_rutas):
        cod_origen = self.buscar_municipio(origen_input)
        cod_destino = self.buscar_municipio(destino_input)
        if cod_origen and cod_destino:
            existe = df_rutas[
                (df_rutas['codigo_dane_origen'] == cod_origen['codigo_dane']) &
                (df_rutas['codigo_dane_destino'] == cod_destino['codigo_dane'])
            ]
              def obtener_municipio_por_codigo(self, codigo_dane):
        """
        Devuelve la fila del municipio (Series) dado su código DANE,
        o None si no existe.
        """
        try:
            codigo_dane = int(codigo_dane)
        except Exception:
            return None

        fila = self.df_municipios[self.df_municipios[self.codigo_municipio_col] == codigo_dane]
        if fila.empty:
            return None
        return fila.iloc[0]

    @staticmethod
    def _distancia_km(lat1, lon1, lat2, lon2):
        """
        Distancia Haversine en km entre dos puntos (lat/lon en grados decimales).
        """
        if any(v is None for v in [lat1, lon1, lat2, lon2]):
            return None

        # Radio de la Tierra en km
        r = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c

    def _municipio_mas_cercano(self, codigo_objetivo, codigos_candidatos):
        """
        Dado un código DANE objetivo y una colección de códigos candidatos,
        devuelve el código del municipio candidato más cercano según lat/long.
        """
        muni_ref = self.obtener_municipio_por_codigo(codigo_objetivo)
        if muni_ref is None:
            return None

        lat_ref = muni_ref.get("latitud")
        lon_ref = muni_ref.get("longitud")
        if pd.isna(lat_ref) or pd.isna(lon_ref):
            return None

        mejor_codigo = None
        mejor_dist = None

        for cod in codigos_candidatos:
            muni_cand = self.obtener_municipio_por_codigo(cod)
            if muni_cand is None:
                continue
            lat_c = muni_cand.get("latitud")
            lon_c = muni_cand.get("longitud")
            if pd.isna(lat_c) or pd.isna(lon_c):
                continue

            dist = self._distancia_km(lat_ref, lon_ref, lat_c, lon_c)
            if dist is None:
                continue

            if (mejor_dist is None) or (dist < mejor_dist):
                mejor_dist = dist
                mejor_codigo = cod

        return mejor_codigo

    def buscar_ruta_con_aproximacion(self, origen_input, destino_input, df_rutas):
        """
        Intenta encontrar una ruta exacta origen-destino.
        Si no existe, busca municipios cercanos (por lat/long) que sí tengan ruta en SICETAC.

        Devuelve (fila_ruta, info_aproximacion), donde:
        - fila_ruta: row de df_rutas (o None si no se encuentra nada)
        - info_aproximacion: dict con detalles de la aproximación
        """
        info_aprox = {
            "es_aproximada": False,
            "origen_solicitado": origen_input,
            "destino_solicitado": destino_input,
            "codigo_origen_solicitado": None,
            "codigo_destino_solicitado": None,
            "codigo_origen_usado": None,
            "codigo_destino_usado": None,
            "nombre_origen_usado": None,
            "nombre_destino_usado": None,
            "motivo": "",
        }

        # 1. Códigos DANE de origen y destino solicitados
        origen_info = self.buscar_municipio(origen_input)
        destino_info = self.buscar_municipio(destino_input)

        if not origen_info or not destino_info:
            info_aprox["motivo"] = "No se encontraron códigos DANE para origen o destino."
            return None, info_aprox

        cod_origen = origen_info["codigo_dane"]
        cod_destino = destino_info["codigo_dane"]
        info_aprox["codigo_origen_solicitado"] = cod_origen
        info_aprox["codigo_destino_solicitado"] = cod_destino

        # 2. Intentar ruta exacta
        ruta_directa = df_rutas[
            (df_rutas["codigo_dane_origen"] == cod_origen) &
            (df_rutas["codigo_dane_destino"] == cod_destino)
        ]
        if ruta_directa.empty:
            ruta_directa = df_rutas[
                (df_rutas["codigo_dane_origen"] == cod_destino) &
                (df_rutas["codigo_dane_destino"] == cod_origen)
            ]

        if not ruta_directa.empty:
            fila = ruta_directa.iloc[0]
            info_aprox["es_aproximada"] = False
            info_aprox["motivo"] = "Ruta exacta encontrada en SICETAC."
            info_aprox["codigo_origen_usado"] = fila["codigo_dane_origen"]
            info_aprox["codigo_destino_usado"] = fila["codigo_dane_destino"]

            muni_origen_usado = self.obtener_municipio_por_codigo(fila["codigo_dane_origen"])
            muni_destino_usado = self.obtener_municipio_por_codigo(fila["codigo_dane_destino"])
            if muni_origen_usado is not None:
                info_aprox["nombre_origen_usado"] = f"{muni_origen_usado.get('nombre_oficial', '')} ({muni_origen_usado.get('departamento', '')})"
            if muni_destino_usado is not None:
                info_aprox["nombre_destino_usado"] = f"{muni_destino_usado.get('nombre_oficial', '')} ({muni_destino_usado.get('departamento', '')})"

            return fila, info_aprox

        # 3. Ruta no existe: buscar municipios más cercanos con ruta en SICETAC
        codigos_origen_sice = set(df_rutas["codigo_dane_origen"].unique())
        codigos_destino_sice = set(df_rutas["codigo_dane_destino"].unique())

        # 3a. Origen usado
        if cod_origen in codigos_origen_sice:
            cod_origen_usado = cod_origen
        else:
            cod_origen_usado = self._municipio_mas_cercano(cod_origen, codigos_origen_sice)

        # 3b. Destino usado
        if cod_destino in codigos_destino_sice:
            cod_destino_usado = cod_destino
        else:
            cod_destino_usado = self._municipio_mas_cercano(cod_destino, codigos_destino_sice)

        if cod_origen_usado is None or cod_destino_usado is None:
            info_aprox["motivo"] = "No fue posible encontrar municipios cercanos con rutas registradas en SICETAC."
            return None, info_aprox

        # 4. Buscar ruta entre los códigos aproximados
        ruta_aprox = df_rutas[
            (df_rutas["codigo_dane_origen"] == cod_origen_usado) &
            (df_rutas["codigo_dane_destino"] == cod_destino_usado)
        ]
        if ruta_aprox.empty:
            ruta_aprox = df_rutas[
                (df_rutas["codigo_dane_origen"] == cod_destino_usado) &
                (df_rutas["codigo_dane_destino"] == cod_origen_usado)
            ]

        if ruta_aprox.empty:
            info_aprox["motivo"] = "No existe tampoco ruta entre los municipios aproximados."
            return None, info_aprox

        fila_aprox = ruta_aprox.iloc[0]

        muni_origen_usado = self.obtener_municipio_por_codigo(cod_origen_usado)
        muni_destino_usado = self.obtener_municipio_por_codigo(cod_destino_usado)

        info_aprox["es_aproximada"] = True
        info_aprox["codigo_origen_usado"] = cod_origen_usado
        info_aprox["codigo_destino_usado"] = cod_destino_usado
        if muni_origen_usado is not None:
            info_aprox["nombre_origen_usado"] = f"{muni_origen_usado.get('nombre_oficial', '')} ({muni_origen_usado.get('departamento', '')})"
        if muni_destino_usado is not None:
            info_aprox["nombre_destino_usado"] = f"{muni_destino_usado.get('nombre_oficial', '')} ({muni_destino_usado.get('departamento', '')})"

        info_aprox["motivo"] = (
            "Ruta exacta no encontrada. Se utilizó como referencia la ruta entre los municipios más cercanos con registro en SICETAC."
        )

        return fila_aprox, info_aprox

