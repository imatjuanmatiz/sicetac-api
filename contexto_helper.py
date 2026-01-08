import pandas as pd
import numpy as np
import math
import unicodedata
from depto_helper import DeptoHelper  # Si usas este helper en bloqueos

# contexto_helper.py
_modo_viaje_global = "CARGADO"

def set_modo_viaje(modo: str):
    global _modo_viaje_global
    _modo_viaje_global = str(modo).upper().strip()

def get_modo_viaje() -> str:
    return _modo_viaje_global

# =========================================
# 🧹 Función para limpiar NaN en los outputs
# =========================================
def limpiar_nan_json(obj):
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

# Nueva carga: Mapeo de configuraciones vehiculares
df_config = pd.read_excel("CONFIGURACION_VEHICULAR_LIMPIO.xlsx")
df_config['TIPO_VEHICULO'] = df_config['TIPO_VEHICULO'].astype(str).str.strip().str.upper()
df_config['CONFIGURACION_ANALISIS'] = df_config['CONFIGURACION_ANALISIS'].astype(str).str.strip().str.upper()
mapeo_config = dict(zip(df_config['TIPO_VEHICULO'], df_config['CONFIGURACION_ANALISIS']))

def traducir_config(config):
    """Traduce configuración usando el mapeo, si es necesario."""
    config = config.upper()
    return mapeo_config.get(config, config)

# =======================================
# 1. HISTÓRICO DE VALORES DE MERCADO
# =======================================

def obtener_valores_promedio_mercado_por_llave(ruta_config):
    """
    Devuelve una lista de diccionarios
    {'MES': ..., 'VALOR_PROMEDIO_MERCADO': ..., 'VALOR_PROMEDIO_VALPAGADOS': ...}
    para cada mes registrado en el Excel, según la llave exacta 'RUTA_CONFIGURACION'.
    """
    ruta_config = str(ruta_config).strip().upper()
    df_valores["RUTA_CONFIGURACION"] = df_valores["RUTA_CONFIGURACION"].astype(str).str.upper().str.strip()
    # Asegúrate que ambas columnas son numéricas
    df_valores["VALOR_PROMEDIO_VALPAGADOS"] = pd.to_numeric(df_valores["VALOR_PROMEDIO_VALPAGADOS"], errors="coerce")

    # DEBUG para ver exactamente qué filas se están usando
    print(f"🔍 Buscando ruta_config: {ruta_config}")
    df_filtrado = df_valores[df_valores["RUTA_CONFIGURACION"] == ruta_config]
    print("Filas encontradas:", len(df_filtrado))
    print(df_filtrado[["MES", "VALOR_PROMEDIO_VALPAGADOS"]])

    # Si no hay datos, retorna lista vacía
    if df_filtrado.empty:
        return []

    # Ordena y retorna solo lo que pide el API
    df_filtrado = df_filtrado.sort_values("MES")
    return df_filtrado[["MES", "VALOR_PROMEDIO_VALPAGADOS"]].to_dict(orient="records")

# =======================================
# 2. INDICADORES OPERATIVOS
# =======================================
def obtener_indicadores(municipio_dane, configuracion):
    config = traducir_config(configuracion)
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
    config = traducir_config(configuracion)
    fila = df_competitividad[
        (df_competitividad["CODIGO_ORIGEN"] == int(origen)) &
        (df_competitividad["CODIGO_DESTINO"] == int(destino)) &
        (df_competitividad["CONFIGURACION"].str.upper() == config)
    ]
    if fila.empty:
        return None
    return fila.iloc[0].to_dict()

# =======================================
# 5. MESES DISPONIBLES PARA INDICADORES
# =======================================
def obtener_meses_disponibles_indicador(df, codigo_objetivo, configuracion):
    config = traducir_config(configuracion)
    filtro = (
        (df["CODIGO_OBJETIVO"] == int(codigo_objetivo)) &
        (df["CONFIGURACION"].str.upper() == config.upper())
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
    Limpia columnas y asegura que no haya NaN en la respuesta JSON.
    """
    import pandas as pd
    import math
    import unicodedata
    from depto_helper import DeptoHelper

# ==== Estado global de modo de viaje (CARGADO | VACIO) ====\n_modo_viaje_global = "CARGADO"\n\ndef set_modo_viaje(modo: str):\n    global _modo_viaje_global\n    _modo_viaje_global = str(modo).upper().strip()\n\n\ndef get_modo_viaje() -> str:\n    return _modo_viaje_global\n\n
    # ---- Función para limpiar columnas (mayúsculas, sin tildes, sin espacios extras) ----
    def limpiar_columna(col):
        col = col.strip().upper()
        col = ''.join((c for c in unicodedata.normalize('NFD', col) if unicodedata.category(c) != 'Mn'))
        return col

    # ---- Función para limpiar NaN e infinitos de la salida ----
    def limpiar_nan_json(obj):
        if isinstance(obj, dict):
            return {k: limpiar_nan_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [limpiar_nan_json(v) for v in obj]
        elif isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        else:
            return obj

    # ---- Inicializa helper y carga bases ----
    helper = DeptoHelper(depto_helper_file)

    df_deptos = pd.read_excel('DEPARTAMENTOS EN RUTAS SICE.xlsx')
    df_bloqueos = pd.read_excel('BLOQUEOS EN VIAS COLFECAR.xlsx')

    df_deptos.columns = [limpiar_columna(c) for c in df_deptos.columns]
    df_bloqueos.columns = [limpiar_columna(c) for c in df_bloqueos.columns]
    df_deptos['CODIGO_DANE_ORIGEN'] = df_deptos['CODIGO_DANE_ORIGEN'].astype(int)
    df_deptos['CODIGO_DANE_DESTINO'] = df_deptos['CODIGO_DANE_DESTINO'].astype(int)
    df_deptos['ID DEPTO'] = df_deptos['ID DEPTO'].astype(int)
    df_bloqueos['ID DEPTO'] = df_bloqueos['ID DEPTO'].astype(int)
    df_bloqueos['EFECTO TOTAL HORAS'] = pd.to_numeric(df_bloqueos['EFECTO TOTAL HORAS'], errors='coerce').fillna(0)

    # ---- 1. Identificar los departamentos por donde pasa la ruta (ambos sentidos) ----
    filtro = df_deptos[
        ((df_deptos['CODIGO_DANE_ORIGEN'] == cod_origen) & (df_deptos['CODIGO_DANE_DESTINO'] == cod_destino)) |
        ((df_deptos['CODIGO_DANE_ORIGEN'] == cod_destino) & (df_deptos['CODIGO_DANE_DESTINO'] == cod_origen))
    ]

    if filtro.empty:
        resultado = {
            "total_bloqueos": 0,
            "departamentos_ruta": [],
            "id_departamentos_ruta": [],
            "lista_bloqueos": [],
            "resumen_motivos": [],
            "total_efecto_horas": 0,
            "riesgo_bloqueos": 0,
            "fuente": "Datos proporcionados por Colfecar"
        }
        return limpiar_nan_json(resultado)

    # ---- 2. Extraer todos los ID DEPTO únicos involucrados en la ruta ----
    id_deptos_ruta = filtro['ID DEPTO'].dropna().astype(int).unique().tolist()

    # ---- 3. Mapear IDs a nombres oficiales usando helper ----
    nombres_departamentos = [helper.buscar_nombre(x) or f"ID {x}" for x in id_deptos_ruta]

    # ---- 4. Filtrar bloqueos para esos departamentos ----
    bloqueos = df_bloqueos[df_bloqueos['ID DEPTO'].isin(id_deptos_ruta)]

    if bloqueos.empty:
        resultado = {
            "total_bloqueos": 0,
            "departamentos_ruta": nombres_departamentos,
            "id_departamentos_ruta": id_deptos_ruta,
            "lista_bloqueos": [],
            "resumen_motivos": [],
            "total_efecto_horas": 0,
            "riesgo_bloqueos": 0,
            "fuente": "Datos proporcionados por Colfecar"
        }
        return limpiar_nan_json(resultado)

    # ---- 5. Lista de bloqueos relevante ----
    columnas = [
        "ID DEPTO",
        "DEPARTAMENTO",
        "VIA AFECTADA",
        "MOTIVO DE LA MANIFESTACION",
        "EFECTO TOTAL HORAS",
        "AÑOMES"
    ]
    # Solo deja las columnas que existan
    columnas_existentes = [c for c in columnas if c in bloqueos.columns]
    lista_bloqueos = bloqueos[columnas_existentes].rename(columns={
        "ID DEPTO": "id_depto",
        "DEPARTAMENTO": "departamento",
        "VIA AFECTADA": "via_afectada",
        "MOTIVO DE LA MANIFESTACION": "motivo_manifestacion",
        "EFECTO TOTAL HORAS": "efecto_total_horas",
        "AÑOMES": "añomes"
    }).to_dict(orient="records")

    # ---- 6. Resumen por motivo ----
    motivo_col = "MOTIVO DE LA MANIFESTACION" if "MOTIVO DE LA MANIFESTACION" in bloqueos.columns else bloqueos.columns[0]  # fallback
    resumen = (
        bloqueos.groupby(motivo_col)
        .agg(
            total_eventos=pd.NamedAgg(column=motivo_col, aggfunc="count"),
            total_efecto_horas=pd.NamedAgg(column="EFECTO TOTAL HORAS", aggfunc="sum")
        )
        .reset_index()
        .rename(columns={motivo_col: "motivo"})
        .to_dict(orient="records")
    )

    # ---- 7. Suma total de horas efecto y riesgo (frecuencia histórica de bloqueo) ----
    total_efecto_horas = bloqueos["EFECTO TOTAL HORAS"].sum()
    total_meses = df_bloqueos["AÑOMES"].nunique() if "AÑOMES" in df_bloqueos.columns else 1
    meses_con_bloqueo = bloqueos["AÑOMES"].nunique() if "AÑOMES" in bloqueos.columns else 1
    riesgo_bloqueos = meses_con_bloqueo / total_meses if total_meses > 0 else 0

    resultado = {
        "total_bloqueos": len(lista_bloqueos),
        "departamentos_ruta": nombres_departamentos,
        "id_departamentos_ruta": id_deptos_ruta,
        "lista_bloqueos": lista_bloqueos,
        "resumen_motivos": resumen,
        "total_efecto_horas": float(total_efecto_horas),
        "riesgo_bloqueos": round(riesgo_bloqueos, 2),
        "fuente": "Datos proporcionados por Colfecar"
    }
    return limpiar_nan_json(resultado)
