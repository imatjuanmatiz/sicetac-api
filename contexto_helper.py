import pandas as pd

# Carga única de todos los archivos
df_valores = pd.read_excel("VALORES_CONSOLIDADOS_2025.xlsx")
df_tiempos = pd.read_excel("indice_cargue_descargue_resumen_mensual.xlsx")
df_competitividad = pd.read_excel("competitividad_rutas_2025.xlsx")

# --- 1. HISTÓRICO DE VALORES DE MERCADO (por ruta + config) ---
def obtener_valores_promedio_mercado(origen, destino, configuracion):
    config = configuracion.upper()
    
    df_filtrado = df_valores[
        (df_valores["CODIGO_ORIGEN"] == int(origen)) &
        (df_valores["CODIGO_DESTINO"] == int(destino)) &
        (df_valores["CONFIGURACION_ANALISIS"].str.upper() == config)
    ]

    if df_filtrado.empty:
        return None

    df_resultado = df_filtrado[["MES", "VALOR_PROMEDIO_MERCADO"]].sort_values("MES")

    return df_resultado.to_dict(orient="records")

# --- 2. INDICADORES OPERATIVOS POR MUNICIPIO OBJETIVO ---
def obtener_indicadores(municipio_dane, configuracion):
    config = configuracion.upper()

    df_filtro = df_tiempos[
        (df_tiempos["CODIGO_OBJETIVO"] == int(municipio_dane)) &
        (df_tiempos["CONFIGURACION"].str.upper() == config)
    ]

    if df_filtro.empty:
        return None

    fila = df_filtro.iloc[0]
    
    return {
        "configuracion": fila["CONFIGURACION"],
        "vehiculos_cargue": fila.get("VEHICULOS_CARGUE"),
        "vehiculos_descargue": fila.get("VEHICULOS_DESCARGUE"),
        "indice_cargue_descargue": fila.get("INDICE_CARGUE_DESCARGUE"),
        "interpretacion": (
            "Exceso de oferta (salen más vehículos de los que llegan)"
            if fila.get("INDICE_CARGUE_DESCARGUE", 0) > 1
            else "Mayor recepción de vehículos (entran más de los que salen)"
        )
    }

# --- 3. COMPETITIVIDAD POR RUTA + CONFIGURACIÓN ---
def evaluar_competitividad(origen, destino, configuracion):
    config = configuracion.upper()
    fila = df_competitividad[
        (df_competitividad["CODIGO_ORIGEN"] == int(origen)) &
        (df_competitividad["CODIGO_DESTINO"] == int(destino)) &
        (df_competitividad["CONFIGURACION"].str.upper() == config)
    ]
    if fila.empty:
        return None
    return fila.iloc[0].to_dict()

# --- 4. MESES DISPONIBLES PARA MERCADO ---
def obtener_meses_disponibles_mercado(cod_origen, cod_destino, config):
    filtro = (
        (df_valores["CODIGO_ORIGEN"] == int(cod_origen)) &
        (df_valores["CODIGO_DESTINO"] == int(cod_destino)) &
        (df_valores["CONFIGURACION_ANALISIS"].str.upper() == config.upper())
    )
    meses = df_valores.loc[filtro, "MES"].dropna().unique()
    return sorted([int(m) for m in meses])

# --- 5. MESES DISPONIBLES PARA INDICADORES OPERATIVOS ---
def obtener_meses_disponibles_indicador(df, codigo_objetivo, configuracion):
    filtro = (
        (df["CODIGO_OBJETIVO"] == int(codigo_objetivo)) &
        (df["CONFIGURACION"].str.upper() == configuracion.upper())
    )
    meses = df.loc[filtro, "AÑOMES"].dropna().unique()
    return sorted([int(m) for m in meses])
