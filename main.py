from fastapi import FastAPI, HTTPException, Query, Response
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
app = FastAPI(title="API SICETAC", version="2.1.0")

# =========================
# MODELO INPUT
# =========================
class ConsultaInput(BaseModel):
    origen: str | None = None
    destino: str | None = None
    id_ruta: str | None = None

    vehiculo: str = "C3S3"
    mes: int = 202601
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0
    horas_logisticas_personalizadas: float | None = None

    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0

    modo_viaje: str = "CARGADO"
    estadistica: str = "Sí"


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
def estadistica_activado(valor):
    if valor is None:
        return False
    return str(valor).strip().lower().replace("í", "i") in ["si", "sí", "true", "1"]


def convertir_nativos(obj):
    if isinstance(obj, dict):
        return {k: convertir_nativos(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convertir_nativos(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


def traducir_configuracion_analisis(vehiculo_sicetac: str) -> str:
    """
    Traduce configuración de SICETAC (ej. C3S3) a configuración usada en estadísticas (ej. 3S3),
    usando el archivo CONFIGURACION_VEHICULAR_LIMPIO.xlsx (col: CONFIGURACION_ANALISIS).

    Fallback: quita 'C'.
    """
    v = (vehiculo_sicetac or "").strip().upper().replace(" ", "")
    if df_vehiculos is None or df_vehiculos.empty:
        return v.replace("C", "")

    tmp = df_vehiculos.copy()
    tmp.columns = [str(c).strip().upper() for c in tmp.columns]

    if "TIPO_VEHICULO" not in tmp.columns or "CONFIGURACION_ANALISIS" not in tmp.columns:
        return v.replace("C", "")

    tmp["TIPO_VEHICULO"] = tmp["TIPO_VEHICULO"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)
    tmp["CONFIGURACION_ANALISIS"] = tmp["CONFIGURACION_ANALISIS"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)

    hit = tmp[tmp["TIPO_VEHICULO"] == v]
    if hit.empty:
        return v.replace("C", "")

    return str(hit.iloc[0]["CONFIGURACION_ANALISIS"]).strip().upper().replace(" ", "").replace("C", "")


def obtener_nombre_ruta(fila_ruta):
    if fila_ruta is None:
        return "Ruta no especificada"

    km_plano = float(fila_ruta.get("KM_PLANO", 0))
    km_ondulado = float(fila_ruta.get("KM_ONDULADO", 0))
    km_montañoso = float(fila_ruta.get("KM_MONTAÑOSO", 0))
    km_urbano = float(fila_ruta.get("KM_URBANO", 0))
    km_despav = float(fila_ruta.get("KM_DESPAVIMENTADO", 0))
    km_total = km_plano + km_ondulado + km_montañoso + km_urbano + km_despav

    distancias = {
        "Plana": km_plano,
        "Ondulada": km_ondulado,
        "Montañosa": km_montañoso,
        "Urbana": km_urbano,
        "Despavimentada": km_despav
    }

    tipo_principal = max(distancias.items(), key=lambda x: x[1])[0]
    porcentaje = (distancias[tipo_principal] / km_total * 100) if km_total > 0 else 0

    nombre = f"Vía {tipo_principal}"
    if porcentaje > 60:
        nombre += f" ({porcentaje:.0f}%)"

    if "NOMBRE_RUTA" in fila_ruta.index and pd.notna(fila_ruta.get("NOMBRE_RUTA")):
        nombre = str(fila_ruta["NOMBRE_RUTA"])

    return nombre


# =========================
# ENDPOINT: BUSCAR RUTA POR ID
# =========================
@app.get("/ruta/{id_ruta}")
def obtener_ruta_por_id(id_ruta: str):
    fila_ruta, info = helper.buscar_ruta_por_id(id_ruta, df_rutas)

    if fila_ruta is None:
        raise HTTPException(status_code=404, detail=info.get("error"))

    origen_muni = helper.obtener_municipio_por_codigo(info["origen"])
    destino_muni = helper.obtener_municipio_por_codigo(info["destino"])

    return JSONResponse(content={
        "id_ruta": info["id_sice"],
        "origen": {
            "codigo": info["origen"],
            "nombre": origen_muni["nombre_oficial"] if origen_muni is not None else "Desconocido",
            "departamento": origen_muni.get("departamento") if origen_muni is not None else None
        },
        "destino": {
            "codigo": info["destino"],
            "nombre": destino_muni["nombre_oficial"] if destino_muni is not None else "Desconocido",
            "departamento": destino_muni.get("departamento") if destino_muni is not None else None
        },
        "nombre_ruta": obtener_nombre_ruta(fila_ruta),
        "km_total": info["km_total"],
        "distancias": {
            "km_plano": float(fila_ruta.get("KM_PLANO", 0)),
            "km_ondulado": float(fila_ruta.get("KM_ONDULADO", 0)),
            "km_montañoso": float(fila_ruta.get("KM_MONTAÑOSO", 0)),
            "km_urbano": float(fila_ruta.get("KM_URBANO", 0)),
            "km_despavimentado": float(fila_ruta.get("KM_DESPAVIMENTADO", 0))
        }
    })


# =========================
# ENDPOINT: LISTAR RUTAS
# =========================
@app.get("/rutas/disponibles")
def listar_rutas_disponibles(
    origen: str = Query(..., description="Nombre del municipio de origen"),
    destino: str = Query(..., description="Nombre del municipio de destino")
):
    lista_rutas, info = helper.buscar_todas_las_rutas(origen, destino, df_rutas)

    if not lista_rutas:
        return JSONResponse(
            status_code=404,
            content={
                "encontradas": 0,
                "origen": origen,
                "destino": destino,
                "mensaje": info.get("mensaje", "No se encontraron rutas"),
                "requiere_distancias_manuales": True
            }
        )

    rutas_formateadas = []
    for ruta in lista_rutas:
        id_ruta = ruta.get("ID_SICE")
        fila = df_rutas[df_rutas["ID_SICE"] == id_ruta].iloc[0]

        rutas_formateadas.append({
            "id_sice": str(id_ruta),
            "nombre_ruta": obtener_nombre_ruta(fila),
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
        "total_rutas": len(rutas_formateadas),
        "rutas": rutas_formateadas,
        "recomendacion": "Para cálculos más rápidos, use el parámetro 'id_ruta' directamente"
    })


# =========================
# ENDPOINT PRINCIPAL
# =========================
@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):

    # -------------------------
    # 1) Resolver ruta
    # -------------------------
    if data.id_ruta:
        fila_ruta, info_ruta = helper.buscar_ruta_por_id(data.id_ruta, df_rutas)
        if fila_ruta is None:
            raise HTTPException(status_code=404, detail=f"No se encontró la ruta con ID: {data.id_ruta}")

        cod_origen = int(fila_ruta["codigo_dane_origen"])
        cod_destino = int(fila_ruta["codigo_dane_destino"])

        origen_muni = helper.obtener_municipio_por_codigo(cod_origen)
        destino_muni = helper.obtener_municipio_por_codigo(cod_destino)

        origen_nombre = origen_muni["nombre_oficial"] if origen_muni is not None else "Desconocido"
        destino_nombre = destino_muni["nombre_oficial"] if destino_muni is not None else "Desconocido"

        info_ruta_response = {
            "metodo_busqueda": "directo_por_id",
            "ruta_id": data.id_ruta,
            "nombre_ruta": obtener_nombre_ruta(fila_ruta),
            "ruta_encontrada": True,
            "mensaje": f"Ruta {data.id_ruta} ({origen_nombre} → {destino_nombre})"
        }

    elif data.origen and data.destino:
        origen_info = helper.buscar_municipio(data.origen)
        destino_info = helper.buscar_municipio(data.destino)

        if not origen_info or not destino_info:
            raise HTTPException(status_code=404, detail="Origen o destino no encontrado en la base de datos")

        cod_origen = int(origen_info["codigo_dane"])
        cod_destino = int(destino_info["codigo_dane"])
        origen_nombre = origen_info.get("nombre_oficial")
        destino_nombre = destino_info.get("nombre_oficial")

        lista_rutas, info_busqueda = helper.buscar_todas_las_rutas_por_codigos(cod_origen, cod_destino, df_rutas)

        if not lista_rutas:
            distancias_disponibles = any([
                data.km_plano, data.km_ondulado, data.km_montañoso,
                data.km_urbano, data.km_despavimentado
            ])

            if not distancias_disponibles:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Ruta no registrada en SICETAC",
                        "origen": origen_nombre,
                        "destino": destino_nombre,
                        "solucion": "Proporcione las distancias manualmente o verifique el origen/destino"
                    }
                )

            fila_ruta = None
            info_ruta_response = {
                "metodo_busqueda": "distancias_manuales",
                "ruta_encontrada": False,
                "usando_distancias_manuales": True,
                "mensaje": f"Ruta {origen_nombre} → {destino_nombre} no registrada. Usando distancias manuales."
            }
        else:
            # IMPORTANTE: asumimos que helper ya devuelve ordenado por ID_SICE asc (principal primero)
            id_ruta_seleccionada = lista_rutas[0]["ID_SICE"]
            fila_ruta = df_rutas[df_rutas["ID_SICE"] == id_ruta_seleccionada].iloc[0]

            info_ruta_response = {
                "metodo_busqueda": "por_origen_destino",
                "ruta_id": str(id_ruta_seleccionada),
                "nombre_ruta": obtener_nombre_ruta(fila_ruta),
                "ruta_encontrada": True,
                "total_rutas_disponibles": len(lista_rutas),
                "mensaje": f"Ruta encontrada: {origen_nombre} → {destino_nombre}"
            }

            if len(lista_rutas) > 1:
                info_ruta_response["rutas_alternativas"] = []
                for ruta_alt in lista_rutas[1:]:
                    id_alt = ruta_alt["ID_SICE"]
                    fila_alt = df_rutas[df_rutas["ID_SICE"] == id_alt].iloc[0]
                    info_ruta_response["rutas_alternativas"].append({
                        "id_sice": str(id_alt),
                        "nombre_ruta": obtener_nombre_ruta(fila_alt),
                        "km_total": float(ruta_alt.get("km_total", 0))
                    })

                info_ruta_response["mensaje"] += f" ({len(lista_rutas)} rutas disponibles)"
                info_ruta_response["recomendacion"] = f"Para cálculos futuros más rápidos, use: id_ruta='{id_ruta_seleccionada}'"
    else:
        raise HTTPException(status_code=400, detail="Debe proporcionar 'id_ruta' O 'origen' y 'destino'")

    # -------------------------
    # 2) Preparar distancias
    # -------------------------
    vehiculo_sicetac = data.vehiculo.strip().upper().replace(" ", "")
    vehiculo_stats = traducir_configuracion_analisis(vehiculo_sicetac)  # ✅ 3S3

    distancias_manuales = any([
        data.km_plano, data.km_ondulado, data.km_montañoso,
        data.km_urbano, data.km_despavimentado
    ])

    if fila_ruta is not None and not distancias_manuales:
        distancias = {
            "KM_PLANO": float(fila_ruta.get("KM_PLANO", 0)),
            "KM_ONDULADO": float(fila_ruta.get("KM_ONDULADO", 0)),
            "KM_MONTAÑOSO": float(fila_ruta.get("KM_MONTAÑOSO", 0)),
            "KM_URBANO": float(fila_ruta.get("KM_URBANO", 0)),
            "KM_DESPAVIMENTADO": float(fila_ruta.get("KM_DESPAVIMENTADO", 0)),
        }
    else:
        distancias = {
            "KM_PLANO": data.km_plano,
            "KM_ONDULADO": data.km_ondulado,
            "KM_MONTAÑOSO": data.km_montañoso,
            "KM_URBANO": data.km_urbano,
            "KM_DESPAVIMENTADO": data.km_despavimentado,
        }
        info_ruta_response["usando_distancias_manuales"] = True

    # -------------------------
    # 3) Calcular SICETAC (SIEMPRE con vehiculo_sicetac)
    # -------------------------
    resultado = calcular_modelo_sicetac_extendido(
        origen=origen_nombre,
        destino=destino_nombre,
        configuracion=vehiculo_sicetac,
        serie=data.mes,
        distancias=distancias,
        valor_peaje_manual=data.valor_peaje_manual,
        matriz_parametros=df_parametros,
        matriz_costos_fijos=df_costos_fijos,
        matriz_vehicular=df_vehiculos,
        rutas_df=df_rutas,
        peajes_df=df_peajes,
        carroceria_especial=data.carroceria,
        ruta_oficial=fila_ruta,
        horas_logisticas=data.horas_logisticas_personalizadas
    )

    resultado = convertir_nativos(resultado)

    # -------------------------
    # 4) Respuesta base
    # -------------------------
    llave_mercado = f"{cod_origen}-{cod_destino}-{vehiculo_sicetac}"
    valor_mercado = obtener_valores_promedio_mercado_por_llave(llave_mercado)

    respuesta = {
        "SICETAC": resultado,
        "MODO_VIAJE": data.modo_viaje,
        "VALOR_MERCADO_RNDC": valor_mercado,
        "INFO_RUTA": info_ruta_response,
        "VEHICULO": {
            "sicetac": vehiculo_sicetac,
            "estadisticas": vehiculo_stats
        }
    }

    # -------------------------
    # 5) Estadísticas/contexto (SIEMPRE con vehiculo_stats)
    # -------------------------
    if estadistica_activado(data.estadistica):
        try:
            respuesta.update({
                "ESTADISTICAS": obtener_estadisticas_completas(cod_origen, cod_destino),

                "INDICADORES_ORIGEN": obtener_indicadores(cod_origen, vehiculo_stats),
                "INDICADORES_DESTINO": obtener_indicadores(cod_destino, vehiculo_stats),
                "COMPETITIVIDAD": evaluar_competitividad(cod_origen, cod_destino, vehiculo_stats),
                "MESES_INDICADORES_ORIGEN": obtener_meses_disponibles_indicador(df_indicadores, cod_origen, vehiculo_stats),
                "MESES_INDICADORES_DESTINO": obtener_meses_disponibles_indicador(df_indicadores, cod_destino, vehiculo_stats),
            })
        except Exception as e:
            respuesta["ESTADISTICAS"] = {
                "warning": "No se pudieron generar estadísticas/contexto",
                "error": str(e),
                "vehiculo_stats": vehiculo_stats
            }

    return JSONResponse(content=respuesta)


# ✅ Render health-check puede usar HEAD / (evita 405)
@app.head("/")
def head_root():
    return Response(status_code=200)


@app.get("/")
def root():
    return {"message": "API SICETAC", "version": "2.1.0"}


@app.get("/health")
def health():
    return {"status": "healthy", "version": "2.1.0"}
