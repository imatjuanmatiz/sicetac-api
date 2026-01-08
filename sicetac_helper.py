# sicetac_helper.py
from __future__ import annotations

import logging
import unicodedata
from difflib import get_close_matches
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _norm_text(s: Any) -> str:
    s = "" if s is None else str(s)
    s = s.strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = " ".join(s.split())
    return s


def _to_native(x: Any) -> Any:
    try:
        if hasattr(x, "item"):
            return x.item()
    except Exception:
        pass
    return x


def _safe_int(x: Any) -> Optional[int]:
    try:
        if pd.isna(x):
            return None
        return int(x)
    except Exception:
        return None


class SICETACHelper:
    """
    Core:
    - Buscar municipios por nombre -> código DANE
    - Buscar rutas SOLO directas (origen->destino)
    - Ordenar por ID_SICE asc (vía principal = ID menor)
    - Exponer métodos compatibles con tu main.py:
        - buscar_todas_las_rutas(origen, destino, df_rutas)
        - buscar_todas_las_rutas_por_codigos(cod_origen, cod_destino, df_rutas)
        - buscar_ruta(origen, destino, df_rutas)
        - buscar_ruta_por_id(id_ruta, df_rutas)
        - obtener_municipio_por_codigo(codigo_dane)
    """

    def __init__(self, municipios_xlsx_path: str):
        self.municipios_path = municipios_xlsx_path
        self.df_municipios = pd.read_excel(municipios_xlsx_path)
        self.df_municipios.columns = [str(c).strip().lower() for c in self.df_municipios.columns]

        self.col_codigo = self._find_col(self.df_municipios, ["codigo_dane", "codigo", "dane"])
        self.col_depto = self._find_col(self.df_municipios, ["departamento", "depto"])
        self.col_nombre_oficial = self._find_col(self.df_municipios, ["nombre_oficial", "nombre", "municipio"])
        self.col_variaciones = [c for c in self.df_municipios.columns if c.startswith("variacion")]

        if self.col_nombre_oficial:
            self.df_municipios["_nombre_norm"] = self.df_municipios[self.col_nombre_oficial].map(_norm_text)
        else:
            self.df_municipios["_nombre_norm"] = ""

        for c in self.col_variaciones:
            self.df_municipios[f"_{c}_norm"] = self.df_municipios[c].map(_norm_text)

        logger.info(
            "✅ Municipios cargados. Columnas detectadas: codigo=%s, depto=%s, nombre=%s, variaciones=%s",
            self.col_codigo, self.col_depto, self.col_nombre_oficial, self.col_variaciones
        )

    @staticmethod
    def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        cols = set(df.columns)
        for c in candidates:
            if c in cols:
                return c
        return None

    # -------------------------
    # Municipios
    # -------------------------
    def buscar_municipio(self, nombre: str, cutoff: float = 0.86) -> Optional[Dict[str, Any]]:
        if not nombre or not self.col_codigo or not self.col_nombre_oficial:
            return None

        objetivo = _norm_text(nombre)

        # 1) Exacto nombre oficial
        hit = self.df_municipios[self.df_municipios["_nombre_norm"] == objetivo]
        if not hit.empty:
            fila = hit.iloc[0]
            res = self._fila_municipio_a_dict(fila)
            logger.info("✓ Municipio encontrado: %s", res)
            return res

        # 2) Exacto en variaciones
        for c in self.col_variaciones:
            coln = f"_{c}_norm"
            hit = self.df_municipios[self.df_municipios[coln] == objetivo]
            if not hit.empty:
                fila = hit.iloc[0]
                res = self._fila_municipio_a_dict(fila)
                res["coincidencia_aproximada"] = str(nombre).strip()
                logger.info("✓ Municipio encontrado: %s", res)
                return res

        # 3) Aproximado
        candidatos = list(self.df_municipios["_nombre_norm"].dropna().unique())
        for c in self.col_variaciones:
            candidatos += list(self.df_municipios[f"_{c}_norm"].dropna().unique())
        candidatos = [c for c in set(candidatos) if c]

        posibles = get_close_matches(objetivo, candidatos, n=1, cutoff=cutoff)
        if not posibles:
            return None

        mejor = posibles[0]
        hit = self.df_municipios[self.df_municipios["_nombre_norm"] == mejor]
        if hit.empty:
            for c in self.col_variaciones:
                coln = f"_{c}_norm"
                hit = self.df_municipios[self.df_municipios[coln] == mejor]
                if not hit.empty:
                    break

        if hit.empty:
            return None

        fila = hit.iloc[0]
        res = self._fila_municipio_a_dict(fila)
        res["coincidencia_aproximada"] = mejor
        logger.info("✓ Municipio encontrado: %s", res)
        return res

    def obtener_municipio_por_codigo(self, codigo_dane: Union[int, str]) -> Optional[Dict[str, Any]]:
        if not self.col_codigo or not self.col_nombre_oficial:
            return None
        cod = _safe_int(codigo_dane)
        if cod is None:
            return None
        hit = self.df_municipios[self.df_municipios[self.col_codigo].apply(_safe_int) == cod]
        if hit.empty:
            return None
        fila = hit.iloc[0]
        return self._fila_municipio_a_dict(fila)

    def _fila_municipio_a_dict(self, fila: pd.Series) -> Dict[str, Any]:
        out = {
            "codigo_dane": _to_native(fila.get(self.col_codigo)),
            "nombre_oficial": _to_native(fila.get(self.col_nombre_oficial)),
        }
        if self.col_depto:
            out["departamento"] = _to_native(fila.get(self.col_depto))
        return out

    # -------------------------
    # Rutas (df_rutas externo)
    # -------------------------
    @staticmethod
    def _detect_route_cols(df_rutas: pd.DataFrame) -> Dict[str, Optional[str]]:
        cols = {str(c).strip().upper(): c for c in df_rutas.columns}

        def pick(options: List[str]) -> Optional[str]:
            for o in options:
                if o in cols:
                    return cols[o]
            return None

        return {
            "COD_ORIGEN": pick(["CODIGO_DANE_ORIGEN", "COD_DANE_ORIGEN", "CODIGO_ORIGEN", "COD_ORIGEN"]),
            "COD_DESTINO": pick(["CODIGO_DANE_DESTINO", "COD_DANE_DESTINO", "CODIGO_DESTINO", "COD_DESTINO"]),
            "ID_SICE": pick(["ID_SICE", "ID", "IDSICE"]),
            "RUTA": pick(["RUTA"]),
            "VIA": pick(["VIA"]),
            "NOMBRE_SICE": pick(["NOMBRE_SICE", "NOMBRE", "NOMBRE_VIA", "NOMBRE_RUTA"]),
            "KM_PLANO": pick(["KM_PLANO"]),
            "KM_ONDULADO": pick(["KM_ONDULADO"]),
            "KM_MONTAÑOSO": pick(["KM_MONTAÑOSO", "KM_MONTANOSO"]),
            "KM_URBANO": pick(["KM_URBANO"]),
            "KM_DESPAV": pick(["KM_DESPAVIMENTADO", "KM_DESPAV", "KM_DESTAPADO"]),
        }

    @staticmethod
    def _km_total_from_row(row: pd.Series, m: Dict[str, Optional[str]]) -> float:
        def g(key: str) -> float:
            col = m.get(key)
            v = row.get(col, 0) if col else 0
            try:
                return float(v) if v is not None and not pd.isna(v) else 0.0
            except Exception:
                return 0.0

        return g("KM_PLANO") + g("KM_ONDULADO") + g("KM_MONTAÑOSO") + g("KM_URBANO") + g("KM_DESPAV")

    # ✅ ESTE ES EL MÉTODO QUE TU main.py ESPERA
    def buscar_todas_las_rutas(
        self,
        origen: str,
        destino: str,
        df_rutas: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Compatibilidad con main.py:
        - recibe nombres de municipios
        - resuelve códigos DANE
        - busca rutas directas por códigos
        - retorna lista y un dict info con origen_nombre/destino_nombre
        """
        mun_origen = self.buscar_municipio(origen)
        mun_destino = self.buscar_municipio(destino)

        if not mun_origen or not mun_destino:
            return [], {
                "mensaje": "No se encontró origen o destino en municipios",
                "origen_nombre": origen,
                "destino_nombre": destino,
                "origen": mun_origen,
                "destino": mun_destino
            }

        cod_origen = int(mun_origen["codigo_dane"])
        cod_destino = int(mun_destino["codigo_dane"])

        rutas, info_cod = self.buscar_todas_las_rutas_por_codigos(cod_origen, cod_destino, df_rutas)

        info = {
            "origen_nombre": mun_origen.get("nombre_oficial"),
            "destino_nombre": mun_destino.get("nombre_oficial"),
            "origen_codigo": cod_origen,
            "destino_codigo": cod_destino,
            **info_cod
        }
        return rutas, info

    def buscar_todas_las_rutas_por_codigos(
        self,
        cod_origen: int,
        cod_destino: int,
        df_rutas: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Busca SOLO rutas directas (origen -> destino).
        Retorna lista ordenada por ID_SICE asc (principal primero) + info.
        """
        m = self._detect_route_cols(df_rutas)
        if not m["COD_ORIGEN"] or not m["COD_DESTINO"]:
            return [], {"mensaje": "No se detectaron columnas de origen/destino en df_rutas", "detected": m}

        dfr = df_rutas.copy()
        dfr["_COD_O"] = pd.to_numeric(dfr[m["COD_ORIGEN"]], errors="coerce")
        dfr["_COD_D"] = pd.to_numeric(dfr[m["COD_DESTINO"]], errors="coerce")

        hit = dfr[(dfr["_COD_O"] == int(cod_origen)) & (dfr["_COD_D"] == int(cod_destino))].copy()
        if hit.empty:
            return [], {
                "mensaje": "No se encontraron rutas para el sentido origen→destino",
                "origen": int(cod_origen),
                "destino": int(cod_destino),
            }

        # Orden por ID asc (ruta principal = menor ID)
        if m["ID_SICE"]:
            hit["_ID"] = pd.to_numeric(hit[m["ID_SICE"]], errors="coerce")
            hit = hit.sort_values(["_ID"], ascending=True)
        else:
            hit["_KMT"] = hit.apply(lambda r: self._km_total_from_row(r, m), axis=1)
            hit = hit.sort_values(["_KMT"], ascending=True)

        rutas: List[Dict[str, Any]] = []
        for _, row in hit.iterrows():
            rutas.append({
                "ID_SICE": _to_native(row.get(m["ID_SICE"])) if m["ID_SICE"] else None,
                "RUTA": _to_native(row.get(m["RUTA"])) if m["RUTA"] else f"{cod_origen}-{cod_destino}",
                "VIA": _to_native(row.get(m["VIA"])) if m["VIA"] else None,
                "NOMBRE_SICE": _to_native(row.get(m["NOMBRE_SICE"])) if m["NOMBRE_SICE"] else None,
                "km_total": float(self._km_total_from_row(row, m)),
                "KM_PLANO": float(row.get(m["KM_PLANO"], 0) if m["KM_PLANO"] else 0),
                "KM_ONDULADO": float(row.get(m["KM_ONDULADO"], 0) if m["KM_ONDULADO"] else 0),
                "KM_MONTAÑOSO": float(row.get(m["KM_MONTAÑOSO"], 0) if m["KM_MONTAÑOSO"] else 0),
                "KM_URBANO": float(row.get(m["KM_URBANO"], 0) if m["KM_URBANO"] else 0),
                "KM_DESPAVIMENTADO": float(row.get(m["KM_DESPAV"], 0) if m["KM_DESPAV"] else 0),
            })

        return rutas, {
            "mensaje": "Rutas encontradas para el sentido origen→destino",
            "origen": int(cod_origen),
            "destino": int(cod_destino),
            "total_rutas": len(rutas),
            "id_principal": rutas[0].get("ID_SICE"),
            "ids_alternativos": [r.get("ID_SICE") for r in rutas[1:]],
        }

    def buscar_ruta(
        self,
        origen: str,
        destino: str,
        df_rutas: pd.DataFrame
    ) -> Tuple[Optional[pd.Series], Dict[str, Any]]:
        """
        Flujo completo: municipio -> códigos -> rutas -> fila principal + alternativas
        """
        rutas, info = self.buscar_todas_las_rutas(origen, destino, df_rutas)
        if not rutas:
            return None, {"error": "No se encontró ruta", "detalle": info}

        id_principal = rutas[0].get("ID_SICE")
        fila, info_id = self.buscar_ruta_por_id(str(id_principal), df_rutas)

        return fila, {
            "ruta_principal": rutas[0],
            "rutas_alternativas": rutas[1:],
            "detalle_rutas": info,
            "detalle_busqueda_id": info_id,
        }

    def buscar_ruta_por_id(self, id_ruta: str, df_rutas: pd.DataFrame) -> Tuple[Optional[pd.Series], Dict[str, Any]]:
        """
        Busca una fila por ID_SICE. Devuelve también origen/destino si existen columnas.
        """
        m = self._detect_route_cols(df_rutas)
        if not m["ID_SICE"]:
            return None, {"error": "No se detectó columna ID_SICE en df_rutas", "detected": m}

        dfr = df_rutas.copy()
        dfr["_ID"] = pd.to_numeric(dfr[m["ID_SICE"]], errors="coerce")

        try:
            target = int(str(id_ruta).strip())
        except Exception:
            return None, {"error": "ID inválido", "id_ruta": id_ruta}

        hit = dfr[dfr["_ID"] == target]
        if hit.empty:
            return None, {"error": "No se encontró ruta con ese ID", "id_ruta": target}

        fila = hit.iloc[0]

        # Si existen columnas de origen/destino, exponerlas (tu main a veces lo usa)
        origen = _safe_int(fila.get(m["COD_ORIGEN"])) if m["COD_ORIGEN"] else None
        destino = _safe_int(fila.get(m["COD_DESTINO"])) if m["COD_DESTINO"] else None

        info = {
            "id_sice": target,
            "origen": origen,
            "destino": destino,
            "ruta": _to_native(fila.get(m["RUTA"])) if m["RUTA"] else None,
            "via": _to_native(fila.get(m["VIA"])) if m["VIA"] else None,
            "nombre_sice": _to_native(fila.get(m["NOMBRE_SICE"])) if m["NOMBRE_SICE"] else None,
            "km_total": float(self._km_total_from_row(fila, m)),
        }
        return fila, info
