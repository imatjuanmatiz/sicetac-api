import pandas as pd

# Carga de archivos
df_valores = pd.read_excel("VALORES_CONSOLIDADOS_2025.xlsx")
df_tiempos = pd.read_excel("indice_cargue_descargue_resumen_mensual.xlsx")
df_competitividad = pd.read_excel("competitividad_rutas_2025.xlsx")

# Función: Valores de mercado por mes/ruta/configuración
def obtener_valores_mercado(mes, origen, destino, configuracion):
    clave_ruta = f"{origen}-{destino}-{configuracion}"
    filtro = (df_valores["MES"] == mes) & (df_valores["RUTA_CONFIGURACION"] == clave_ruta)
    if df_valores[filtro].empty:
        return None
    return df_valores[filtro].iloc[0].to_dict()

# Función: Tiempos operativos de cargue y descargue
def obtener_tiempos_operativos(mes, origen, destino):
    filtro = (
        (df_tiempos["MES"] == mes) &
        (df_tiempos["CODIGO_ORIGEN"] == int(origen)) &
        (df_tiempos["CODIGO_DESTINO"] == int(destino))
    )
    if df_tiempos[filtro].empty:
        return None
    return df_tiempos[filtro].iloc[0].to_dict()

# Función: Índice de competitividad
def obtener_indice_competitividad(origen, destino, configuracion):
    clave_ruta = f"{origen}-{destino}-{configuracion}"
    filtro = df_competitividad["RUTA_CONFIGURACION"] == clave_ruta
    if df_competitividad[filtro].empty:
        return None
    return df_competitividad[filtro].iloc[0].to_dict()

