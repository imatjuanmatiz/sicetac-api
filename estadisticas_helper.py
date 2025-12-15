# estadisticas_helper.py

import pandas as pd

# Carga los archivos .xlsx con todas las estadísticas
DF_MERCANCIAS = pd.read_excel("top_mercancias_ruta_2024_2025.xlsx")
DF_EVOLUCION = pd.read_excel("evolucion_viajes_toneladas_2024_2025.xlsx")
DF_DESTINOS = pd.read_excel("top_destinos_por_origen_2025.xlsx")
DF_ORIGENES = pd.read_excel("top_origenes_por_destino_2025.xlsx")
DF_VEHICULOS = pd.read_excel("tipos_vehiculo_por_ruta_2025.xlsx")

def obtener_evolucion_viajes_y_toneladas(origen, destino):
    clave = f"{origen}-{destino}"
    df = DF_EVOLUCION[DF_EVOLUCION["RUTA"] == clave]
    return df.sort_values("MES").to_dict(orient="records")

def obtener_top_mercancias_ruta(origen, destino):
    clave = f"{origen}-{destino}"
    df = DF_MERCANCIAS[DF_MERCANCIAS["RUTA"] == clave]
    merc_2024 = df[df["AÑO"] == 2024].sort_values("TONELADAS", ascending=False).head(20)
    merc_2025 = df[df["AÑO"] == 2025].sort_values("TONELADAS", ascending=False).head(20)
    return {
        "TOP_MERCANCIAS_2024": merc_2024[["CODMERCANCIA", "MERCANCIA", "TONELADAS", "PCT"]].to_dict(orient="records"),
        "TOP_MERCANCIAS_2025": merc_2025[["CODMERCANCIA", "MERCANCIA", "TONELADAS", "PCT"]].to_dict(orient="records")
    }

def obtener_top_destinos(cod_origen):
    df = DF_DESTINOS[DF_DESTINOS["CODIGO_ORIGEN"] == int(cod_origen)]
    return df.sort_values("TONELADAS", ascending=False).head(20).to_dict(orient="records")

def obtener_top_origenes(cod_destino):
    df = DF_ORIGENES[DF_ORIGENES["CODIGO_DESTINO"] == int(cod_destino)]
    return df.sort_values("TONELADAS", ascending=False).head(20).to_dict(orient="records")

def obtener_distribucion_vehiculos_ruta(origen, destino):
    clave = f"{origen}-{destino}"
    df = DF_VEHICULOS[DF_VEHICULOS["RUTA"] == clave]
    return df.sort_values("VIAJES", ascending=False).to_dict(orient="records")
