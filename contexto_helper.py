import pandas as pd

# Carga de archivos globales
df_valores_mercado = pd.read_csv("VALORES_CONSOLIDADOS_2025.csv")
df_indicadores = pd.read_csv("indice_cargue_descargue_resumen_mensual.csv")
df_competitividad = pd.read_csv("competitividad_rutas_2025.csv")

def estandarizar_codigo_dane(codigo):
    return str(codigo).zfill(8)

def obtener_valor_mercado(cod_origen, cod_destino, config):
    config = config.strip().upper()
    cod_origen = estandarizar_codigo_dane(cod_origen)
    cod_destino = estandarizar_codigo_dane(cod_destino)
    clave_ruta = f"{cod_origen}-{cod_destino}"
    
    fila = df_valores_mercado[
        (df_valores_mercado["RUTA_ANALISIS"] == clave_ruta) &
        (df_valores_mercado["CONFIGURACION_ANALISIS"] == config)
    ]
    if fila.empty:
        return {}
    
    fila_ordenada = fila.sort_values("MES")
    return {
        str(row.MES): round(row.VALOR_PROMEDIO_MERCADO, 0)
        for _, row in fila_ordenada.iterrows()
    }

def obtener_indicadores(codigo, config):
    config = config.strip().upper()
    fila = df_indicadores[
        (df_indicadores["CODIGO_OBJETIVO"] == codigo) &
        (df_indicadores["CONFIGURACION"] == config)
    ]
    if fila.empty:
        return {}
    fila_ordenada = fila.sort_values("AÑOMES")
    return {
        str(row["AÑOMES"]): {
            "viajes_cargue": int(row["VIAJES_ORIGINADOS"]),
            "viajes_descargue": int(row["VIAJES_DESCARGADOS"]),
            "indice": round(row["INDICE_CARGUE_DESCARGUE"], 2)
        }
        for _, row in fila_ordenada.iterrows()
    }

def evaluar_competitividad(cod_origen, cod_destino, config):
    config = config.strip().upper()
    clave_ruta = f"{cod_origen}-{cod_destino}"
    fila = df_competitividad[
        (df_competitividad["RUTA"] == clave_ruta) &
        (df_competitividad["CONFIGURACION"] == config)
    ]
    if fila.empty:
        return {"nivel": "ND", "empresas": "ND", "participacion": "ND"}
    f = fila.iloc[0]
    top1 = f["PARTICIPACION_MAXIMA"]
    if top1 >= 0.6:
        nivel = "Muy baja"
    elif top1 >= 0.4:
        nivel = "Baja"
    elif top1 >= 0.25:
        nivel = "Media"
    else:
        nivel = "Alta"
    return {
        "nivel": nivel,
        "empresas": int(f["NUM_EMPRESAS"]),
        "participacion": round(top1 * 100, 1)
    }

def obtener_meses_disponibles(df, clave_ruta, config, campo_ruta="RUTA_ANALISIS", campo_config="CONFIGURACION_ANALISIS", campo_mes="MES"):
    config = config.strip().upper()
    filas = df[
        (df[campo_ruta] == clave_ruta) &
        (df[campo_config] == config)
    ]
    if filas.empty:
        return []
    return sorted(filas[campo_mes].astype(str).unique().tolist())
