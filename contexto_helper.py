import pandas as pd
import numpy as np

# =========================================
# 🧹 Función para limpiar NaN en los outputs
# =========================================
def limpiar_nan_json(obj):
    import math
    if isinstance(obj, dict):
        return {k: limpiar_nan_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [limpiar_nan_json(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    else:
        return obj

# ================================
# ✅ Carga única de todas las bases
# ================================
df_valores = pd.read_excel("VALORES_CONSOLIDADOS_2025.xlsx")
df_tiempos = pd.read_excel("indice_cargue_descargue_resumen_mensual.xlsx")
df_competitividad = pd.read_excel("competitividad_rutas_2025.xlsx")


# =======================================
# 1. HISTÓRICO DE VALORES DE MERCADO
# =======================================
def obtener_valores_promedio_mercado(origen, destino, configuracion):
    config = configuracion.upper()
    df_valores["CONFIGURACION_ANALISIS"] = df_valores["CONFIGURACION_ANALISIS"].astype(str)
    filtro = (
        (df_valores["CODIGO_ORIGEN"] == int(origen)) &
        (df_valores["CODIGO_DESTINO"] == int(destino)) &
        (df_valores["CONFIGURACION_ANALISIS"].str.upper() == config)
    )
    df_filtrado = df_valores[filtro]

    # Lista de todos los meses disponibles (puede que no tengan valor promedio)
    meses_disponibles = sorted(df_filtrado["MES"].unique().tolist())
    
    if df_filtrado.empty:
        return {
            "valores_mes": [],
            "meses_disponibles": meses_disponibles
        }
    # Solo los meses donde sí hay valor promedio registrado (no NaN)
    df_resultado = df_filtrado[["MES", "VALOR_PROMEDIO_MERCADO"]].sort_values("MES")
    valores_mes = df_resultado.to_dict(orient="records")
    
    return {
        "valores_mes": valores_mes,
        "meses_disponibles": meses_disponibles
    }

# =======================================
# 2. INDICADORES OPERATIVOS
# =======================================
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


# =======================================
# 3. COMPETITIVIDAD POR RUTA
# =======================================
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


# =======================================
# 4. MESES DISPONIBLES PARA MERCADO
# =======================================
def obtener_meses_disponibles_mercado(cod_origen, cod_destino, config):
    filtro = (
        (df_valores["CODIGO_ORIGEN"] == int(cod_origen)) &
        (df_valores["CODIGO_DESTINO"] == int(cod_destino)) &
        (df_valores["CONFIGURACION_ANALISIS"].str.upper() == config.upper())
    )
    meses = df_valores.loc[filtro, "MES"].dropna().unique()
    return sorted([int(m) for m in meses])


# =======================================
# 5. MESES DISPONIBLES PARA INDICADORES
# =======================================
def obtener_meses_disponibles_indicador(df, codigo_objetivo, configuracion):
    filtro = (
        (df["CODIGO_OBJETIVO"] == int(codigo_objetivo)) &
        (df["CONFIGURACION"].str.upper() == configuracion.upper())
    )
    meses = df.loc[filtro, "AÑOMES"].dropna().unique()
    return sorted([int(m) for m in meses])


# =======================================
# 6. BLOQUEOS DE COLFECAR POR RUTA
# =======================================

def obtener_bloqueos_ruta_por_id(cod_origen, cod_destino, depto_helper_file='DEPTO HELPER.xlsx'):
    """
    Analiza bloqueos históricos para una ruta definida por cod_origen y cod_destino, usando ID DEPTO.
    Usa depto_helper para identificar IDs y EFECTO TOTAL HORAS para análisis.
    """
    import pandas as pd
    from depto_helper import DeptoHelper

    # Inicializa helper una sola vez por función
    helper = DeptoHelper(depto_helper_file)

    # Cargar bases
    df_deptos = pd.read_excel('DEPARTAMENTOS EN RUTAS SICE.xlsx')
    df_bloqueos = pd.read_excel('BLOQUEOS EN VIAS COLFECAR.xlsx')

    # Limpieza y normalización
    df_deptos.columns = df_deptos.columns.str.strip()
    df_bloqueos.columns = df_bloqueos.columns.str.strip()
    df_deptos['codigo_dane_origen'] = df_deptos['codigo_dane_origen'].astype(int)
    df_deptos['codigo_dane_destino'] = df_deptos['codigo_dane_destino'].astype(int)
    df_deptos['ID DEPTO'] = df_deptos['ID DEPTO'].astype(int)
    df_bloqueos['ID DEPTO'] = df_bloqueos['ID DEPTO'].astype(int)
    df_bloqueos['EFECTO TOTAL HORAS'] = pd.to_numeric(df_bloqueos['EFECTO TOTAL HORAS'], errors='coerce').fillna(0)

    # 1. Identificar los departamentos por donde pasa la ruta (ambos sentidos)
    filtro = df_deptos[
        ((df_deptos['codigo_dane_origen'] == cod_origen) & (df_deptos['codigo_dane_destino'] == cod_destino)) |
        ((df_deptos['codigo_dane_origen'] == cod_destino) & (df_deptos['codigo_dane_destino'] == cod_origen))
    ]

    if filtro.empty:
        return {
            "total_bloqueos": 0,
            "departamentos_ruta": [],
            "id_departamentos_ruta": [],
            "lista_bloqueos": [],
            "resumen_motivos": [],
            "total_efecto_horas": 0,
            "riesgo_bloqueos": 0,
            "fuente": "Datos proporcionados por Colfecar"
        }

    # 2. Extraer todos los ID DEPTO únicos involucrados en la ruta
    id_deptos_ruta = filtro['ID DEPTO'].dropna().astype(int).unique().tolist()

    # 3. Mapear IDs a nombres oficiales usando helper
    nombres_departamentos = [helper.buscar_nombre(x) or f"ID {x}" for x in id_deptos_ruta]

    # 4. Filtrar bloqueos para esos departamentos
    bloqueos = df_bloqueos[df_bloqueos['ID DEPTO'].isin(id_deptos_ruta)]

    if bloqueos.empty:
        return {
            "total_bloqueos": 0,
            "departamentos_ruta": nombres_departamentos,
            "id_departamentos_ruta": id_deptos_ruta,
            "lista_bloqueos": [],
            "resumen_motivos": [],
            "total_efecto_horas": 0,
            "riesgo_bloqueos": 0,
            "fuente": "Datos proporcionados por Colfecar"
        }

    # 5. Lista de bloqueos relevante
    columnas = [
        "ID DEPTO",
        "DEPARTAMENTO SICE",
        "VIA AFECTADA",
        "MOTIVO DE LA MANIFESTACION",
        "EFECTO TOTAL HORAS",
        "AÑOMES"
    ]
    lista_bloqueos = bloqueos[columnas].rename(columns={
        "ID DEPTO": "id_depto",
        "DEPARTAMENTO SICE": "departamento",
        "VIA AFECTADA": "via_afectada",
        "MOTIVO DE LA MANIFESTACION": "motivo_manifestacion",
        "EFECTO TOTAL HORAS": "efecto_total_horas",
        "AÑOMES": "añomes"
    }).to_dict(orient="records")

    # 6. Resumen por motivo
    resumen = (
        bloqueos.groupby("MOTIVO DE LA MANIFESTACION")
        .agg(
            total_eventos=pd.NamedAgg(column="MOTIVO DE LA MANIFESTACION", aggfunc="count"),
            total_efecto_horas=pd.NamedAgg(column="EFECTO TOTAL HORAS", aggfunc="sum")
        )
        .reset_index()
        .rename(columns={"MOTIVO DE LA MANIFESTACION": "motivo"})
        .to_dict(orient="records")
    )

    # 7. Suma total de horas efecto y riesgo (frecuencia histórica de bloqueo)
    total_efecto_horas = bloqueos["EFECTO TOTAL HORAS"].sum()
    total_meses = df_bloqueos["AÑOMES"].nunique()
    meses_con_bloqueo = bloqueos["AÑOMES"].nunique()
    riesgo_bloqueos = meses_con_bloqueo / total_meses if total_meses > 0 else 0

    return {
        "total_bloqueos": len(lista_bloqueos),
        "departamentos_ruta": nombres_departamentos,
        "id_departamentos_ruta": id_deptos_ruta,
        "lista_bloqueos": lista_bloqueos,
        "resumen_motivos": resumen,
        "total_efecto_horas": float(total_efecto_horas),
        "riesgo_bloqueos": round(riesgo_bloqueos, 2),
        "fuente": "Datos proporcionados por Colfecar"
    }
