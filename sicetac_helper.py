import pandas as pd
from difflib import get_close_matches
import logging

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
            return not existe.empty
        return False
