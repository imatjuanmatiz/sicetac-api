
import pandas as pd
from difflib import get_close_matches
import logging
logging.basicConfig(level=logging.INFO)

class SICETACHelper:
    def __init__(self, archivo_municipios, archivo_camiones):
        self.df_municipios = pd.read_excel(archivo_municipios)
        self.df_camiones = pd.read_excel(archivo_camiones)
        self.columnas_municipios = ['nombre_oficial', 'variacion_1', 'variacion_2', 'variacion_3']
        self.codigo_municipio_col = 'codigo_dane'
        self.columnas_camiones = ['nombre_oficial', 'variante_2', 'variante_3']

    def buscar_municipio(self, nombre_input):
        return self._buscar_codigo(
            self.df_municipios,
            nombre_input,
            self.columnas_municipios,
            'codigo_municipio',
            ['departamento', 'nombre_oficial']
        )

    def buscar_camion(self, nombre_input):
        return self._buscar_codigo(
            self.df_camiones,
            nombre_input,
            self.columnas_camiones,
            'codigo_carroceria',
            ['detalle', 'TIPO_VEHICULO', 'nombre_oficial']
        )

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

        # Si no se encontró una coincidencia exacta, hacer fuzzy match
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
                (df_rutas['COD_DANE_ORIGEN'] == cod_origen['codigo_municipio']) &
                (df_rutas['COD_DANE_DESTINO'] == cod_destino['codigo_municipio'])
            ]
            return not existe.empty
        return False
