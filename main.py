from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import pandas as pd
from fastapi.responses import JSONResponse

from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido

from contexto_helper import (
    obtener_valores_promedio_mercado_por_llave,
    obtener_indicadores,
    evaluar_competitividad,
    obtener_meses_disponibles_indicador,
    obtener_estadisticas_completas
)

# =========================
# APP
# =========================
app = FastAPI(title="API SICETAC", version="2.0.0")

# =========================
# MODELO INPUT
# =========================
class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int = 202601
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0

    horas_logisticas_personalizadas: float | None = None
    tarifa_standby: float = 150000

    # 📏 DISTANCIAS MANUALES (obligatorias si la ruta no existe)
    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0

    modo_viaje: str = "CARGADO"
    modo_tiempos_logisticos: bool = True

    estadistica: str = "Sí"
    
    # 🛣️ ID de ruta específica (cuando hay múltiples)
    id_ruta: str | None = None


# =========================
# NORMALIZAR ESTADISTICAS
# =========================
def estadistica_activado(valor):
    if valor is None:
        return False
    return str(valor).strip().lower().replace("í", "i") in ["si", "sí", "true", "1"]


# =========================
# CARGA BASE
# =========================
ARCHIVOS = {
    "municipios": "municipios.xlsx",
    "vehiculos": "CONFIGURACION_VEHICULAR_LIMPIO.xlsx",
    "parametros": "MATRIZ_CAMBIOS_PARAMETROS_LIMPIO.xlsx",
    "costos_fijos": "COSTO_FIJO_ACTUALIZADO.xlsx",
    "peajes": "PEAJES_LIMPIO.xlsx",
    "rutas": "RUTA_DISTANCIA_LIMPIO.xlsx",
}

helper = SICETACHelper(ARCHIVOS["municipios"])

df_vehiculos = pd.read_excel(ARCHIVOS["vehiculos"])
df_parametros = pd.read_excel(ARCHIVOS["parametros"])
df_costos_fijos = pd.read_excel(ARCHIVOS["costos_fijos"])
df_peajes = pd.read_excel(ARCHIVOS["peajes"])
df_rutas = pd.read_excel(ARCHIVOS["rutas"])
df_indicadores = pd.read_excel("indice_cargue_descargue_resumen_mensual.xlsx")


# =========================
# UTIL
# =========================
def convertir_nativos(obj):
    if isinstance(obj, dict):
        return {k: convertir_nativos(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convertir_nativos(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


# =========================
# 🆕 ENDPOINT: LISTAR RUTAS DISPONIBLES
# =========================
@app.get("/rutas/disponibles")
def listar_rutas_disponibles(
    origen: str = Query(..., description="Nombre del municipio de origen"),
    destino: str = Query(..., description="Nombre del municipio de destino")
):
    """
    Lista todas las rutas disponibles entre un origen y destino.
    Útil cuando existen vías alternativas.
    """
    lista_rutas, info = helper.buscar_todas_las_rutas(origen, destino, df_rutas)
    
    if not lista_rutas:
        return JSONResponse(
            status_code=404,
            content={
                "encontradas": 0,
                "origen": origen,
                "destino": destino,
                "mensaje": info.get("mensaje", "No se encontraron rutas"),
                "requiere_distancias_manuales": True,
                "nota": "Para calcular esta ruta, debe proporcionar las distancias manuales en la petición"
            }
        )
    
    # Formatear respuesta
    rutas_formateadas = []
    for ruta in lista_rutas:
        rutas_formateadas.append({
            "id_sice": ruta.get("ID_SICE"),
            "km_total": ruta.get("km_total"),
            "distancias": {
                "km_plano": ruta.get("KM_PLANO", 0),
                "km_ondulado": ruta.get("KM_ONDULADO", 0),
                "km_montañoso": ruta.get("KM_MONTAÑOSO", 0),
                "km_urbano": ruta.get("KM_URBANO", 0),
                "km_despavimentado": ruta.get("KM_DESPAVIMENTADO", 0)
            }
        })
    
    return JSONResponse(content={
        "origen": info.get("origen_nombre"),
        "destino": info.get("destino_nombre"),
        "total_rutas": info.get("encontradas"),
        "rutas": rutas_formateadas
    })


# =========================
# 🆕 ENDPOINT: ESTADÍSTICAS DE SICETAC
# =========================
@app.get("/sicetac/estadisticas")
def obtener_estadisticas_sicetac():
    """
    Retorna estadísticas generales sobre las rutas registradas en SICETAC.
    """
    stats = helper.obtener_estadisticas_rutas(df_rutas)
    return JSONResponse(content=stats)


# =========================
# ENDPOINT PRINCIPAL
# =========================
@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):

    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise HTTPException(status_code=404, detail="Origen o destino no encontrado en la base de datos")

    cod_origen = origen_info["codigo_dane"]
    cod_destino = destino_info["codigo_dane"]
    vehiculo = data.vehiculo.strip().upper()

    # =========================
    # 🔍 BUSCAR RUTA EN SICETAC
    # =========================
    
    fila_ruta = None
    info_ruta = None
    
    # Si el usuario especificó un ID de ruta, usar esa
    if data.id_ruta:
        fila_ruta, info_busqueda = helper.buscar_ruta_por_id(data.id_ruta, df_rutas)
        if fila_ruta is None:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró la ruta con ID: {data.id_ruta}"
            )
        info_ruta = {
            "ruta_seleccionada_por_usuario": True,
            "id_ruta_seleccionada": data.id_ruta,
            **info_busqueda
        }
    else:
        # Búsqueda automática
        fila_ruta, info_ruta = helper.buscar_ruta(data.origen, data.destino, df_rutas)

    # =========================
    # 📏 PREPARAR DISTANCIAS
    # =========================
    
    distancias_disponibles = any([
        data.km_plano,
        data.km_ondulado,
        data.km_montañoso,
        data.km_urbano,
        data.km_despavimentado,
    ])

    if fila_ruta is None:
        # ❌ RUTA NO EXISTE EN SICETAC
        
        if not distancias_disponibles:
            # Usuario no proporcionó distancias manuales
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Ruta no registrada en SICETAC",
                    "mensaje": info_ruta.get("mensaje"),
                    "origen": info_ruta.get("nombre_origen"),
                    "destino": info_ruta.get("nombre_destino"),
                    "solucion": "Debe proporcionar las distancias manuales: km_plano, km_ondulado, km_montañoso, km_urbano, km_despavimentado",
                    "ejemplo": {
                        "km_plano": 100,
                        "km_ondulado": 50,
                        "km_montañoso": 30,
                        "km_urbano": 10,
                        "km_despavimentado": 0
                    }
                }
            )
        
        # Usuario SÍ proporcionó distancias manuales
        distancias = {
            "KM_PLANO": data.km_plano,
            "KM_ONDULADO": data.km_ondulado,
            "KM_MONTAÑOSO": data.km_montañoso,
            "KM_URBANO": data.km_urbano,
            "KM_DESPAVIMENTADO": data.km_despavimentado,
        }
        
        info_ruta["usando_distancias_manuales"] = True
        info_ruta["mensaje"] += " | Usando distancias proporcionadas manualmente."
        
    else:
        # ✅ RUTA EXISTE EN SICETAC
        
        if distancias_disponibles:
            # Usuario proporcionó distancias manuales aunque la ruta existe
            distancias = {
                "KM_PLANO": data.km_plano,
                "KM_ONDULADO": data.km_ondulado,
                "KM_MONTAÑOSO": data.km_montañoso,
                "KM_URBANO": data.km_urbano,
                "KM_DESPAVIMENTADO": data.km_despavimentado,
            }
            info_ruta["usando_distancias_manuales"] = True
            info_ruta["advertencia"] = "Se están usando distancias manuales en lugar de las de SICETAC"
        else:
            # Usar distancias de SICETAC
            distancias = {
                "KM_PLANO": fila_ruta.get("KM_PLANO", 0),
                "KM_ONDULADO": fila_ruta.get("KM_ONDULADO", 0),
                "KM_MONTAÑOSO": fila_ruta.get("KM_MONTAÑOSO", 0),
                "KM_URBANO": fila_ruta.get("KM_URBANO", 0),
                "KM_DESPAVIMENTADO": fila_ruta.get("KM_DESPAVIMENTADO", 0),
            }
            info_ruta["usando_distancias_manuales"] = False

    # =========================
    # 💰 CALCULAR SICETAC
    # =========================
    resultado = calcular_modelo_sicetac_extendido(
        origen=data.origen,
        destino=data.destino,
        configuracion=vehiculo,
        serie=data.mes,
        distancias=distancias,
        valor_peaje_manual=data.valor_peaje_manual,
        matriz_parametros=df_parametros,
        matriz_costos_fijos=df_costos_fijos,
        matriz_vehicular=df_vehiculos,
        rutas_df=df_rutas,
        peajes_df=df_peajes,
        carroceria_especial=data.carroceria,
        ruta_oficial=fila_ruta,  # Puede ser None si no existe
        horas_logisticas=data.horas_logisticas_personalizadas
    )

    resultado = convertir_nativos(resultado)

    # =========================
    # 📊 RESPUESTA
    # =========================
    llave_mercado = f"{cod_origen}-{cod_destino}-{vehiculo}"
    valor_mercado = obtener_valores_promedio_mercado_por_llave(llave_mercado)

    respuesta = {
        "SICETAC": resultado,
        "MODO_VIAJE": data.modo_viaje,
        "VALOR_MERCADO_RNDC": valor_mercado,
        "INFO_RUTA": info_ruta
    }

    # =========================
    # 🆕 ALERTAS
    # =========================
    alertas = []
    
    if info_ruta.get("total_rutas_disponibles", 0) > 1:
        alertas.append({
            "tipo": "multiples_rutas",
            "mensaje": f"Se encontraron {info_ruta.get('total_rutas_disponibles')} rutas alternativas. Para usar otra ruta, especifique 'id_ruta' en la petición.",
            "rutas_alternativas": info_ruta.get("rutas_alternativas", [])
        })
    
    if info_ruta.get("requiere_distancias_manuales"):
        alertas.append({
            "tipo": "ruta_no_registrada",
            "mensaje": "Esta ruta no está registrada en SICETAC. Se usaron las distancias manuales proporcionadas.",
            "recomendacion": "Verifique que las distancias sean correctas"
        })
    
    if info_ruta.get("usando_distancias_manuales") and fila_ruta is not None:
        alertas.append({
            "tipo": "distancias_sobrescritas",
            "mensaje": "Se proporcionaron distancias manuales que sobrescriben las de SICETAC",
            "nota": "Si no especifica distancias, se usarán las de SICETAC automáticamente"
        })
    
    if alertas:
        respuesta["ALERTAS"] = alertas

    # =========================
    # 📈 ESTADISTICAS
    # =========================
    if estadistica_activado(data.estadistica):
        respuesta.update({
            "ESTADISTICAS": obtener_estadisticas_completas(
                origen=data.origen,
                destino=data.destino,
                cod_origen=cod_origen,
                cod_destino=cod_destino
            ),
            "INDICADORES_ORIGEN": obtener_indicadores(cod_origen, vehiculo),
            "INDICADORES_DESTINO": obtener_indicadores(cod_destino, vehiculo),
            "COMPETITIVIDAD": evaluar_competitividad(cod_origen, cod_destino, vehiculo),
            "MESES_INDICADORES_ORIGEN": obtener_meses_disponibles_indicador(
                df_indicadores, cod_origen, vehiculo
            ),
            "MESES_INDICADORES_DESTINO": obtener_meses_disponibles_indicador(
                df_indicadores, cod_destino, vehiculo
            )
        })

    return JSONResponse(content=respuesta)


@app.get("/")
def root():
    return {
        "message": "API SICETAC funcionando", 
        "version": "2.0.0",
        "cambios_importantes": [
            "❌ Eliminada aproximación geográfica automática (causaba errores)",
            "✅ Manejo claro de rutas no registradas",
            "✅ Requiere distancias manuales cuando la ruta no existe",
            "✅ Detección de múltiples rutas alternativas",
            "✅ Endpoint GET /rutas/disponibles",
            "✅ Endpoint GET /sicetac/estadisticas"
        ]
    }


@app.get("/health")
def health():
    return {"status": "healthy", "version": "2.0.0"}
