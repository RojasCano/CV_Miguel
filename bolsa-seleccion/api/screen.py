"""Funcion serverless de Vercel: ejecuta el Filtro de los Tres Candados.

GET /api/screen?mercado=america|europa|asia&sector=0|1

Devuelve JSON con el resultado completo del screening: estado de cada candado
por accion, rendimiento del indice de referencia y sectores lideres.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf  # noqa: E402

from filtro_tres_candados import (  # noqa: E402
    _calcular_metricas,
    _pasa_candado_1,
    _pasa_candado_2,
    _rendimiento_3m,
    _sectores_lideres,
)
from universos import MERCADOS  # noqa: E402


def ejecutar_screening(mercado: str, candado_sector: bool) -> dict:
    """Descarga datos en tiempo real y aplica los tres candados al mercado."""
    cfg = MERCADOS[mercado]
    universo = cfg["universo"]
    indice = cfg["indice"]

    datos = yf.download(
        list(universo) + [indice],
        period="2y",
        interval="1d",
        auto_adjust=True,
        group_by="ticker",
        progress=False,
        threads=True,
    )

    cierres_indice = datos[indice]["Close"].dropna()
    rendimiento_indice = _rendimiento_3m(cierres_indice)

    filas: list[dict] = []
    rendimientos_sector: dict[str, list[float]] = {}

    for ticker, info in universo.items():
        try:
            historico = datos[ticker][["Close", "Volume"]].dropna(subset=["Close"])
            m = _calcular_metricas(ticker, {
                "historico": historico,
                "market_cap": info["market_cap"],
                "sector": info["sector"],
            })
        except Exception as exc:  # descarte seguro: la fila informa del motivo
            filas.append({
                "ticker": ticker,
                "nombre": info["nombre"],
                "sector": info["sector"],
                "error": str(exc),
            })
            continue

        rendimientos_sector.setdefault(m.sector, []).append(m.rendimiento_3m)
        filas.append({
            "ticker": ticker,
            "nombre": info["nombre"],
            "sector": m.sector,
            "precio": round(m.precio_actual, 2),
            "market_cap": m.market_cap,
            "dist_sma200": round(m.distancia_sma200_pct, 2),
            "rendimiento_3m": round(m.rendimiento_3m, 2),
            "candado1": _pasa_candado_1(m),
            "candado2": _pasa_candado_2(m, rendimiento_indice),
        })

    lideres = sorted(_sectores_lideres(rendimientos_sector))
    for fila in filas:
        if "error" in fila:
            continue
        fila["candado3"] = fila["sector"] in lideres if candado_sector else None
        fila["pasa"] = bool(
            fila["candado1"] and fila["candado2"] and fila["candado3"] is not False
        )

    filas.sort(key=lambda f: f.get("rendimiento_3m", float("-inf")), reverse=True)

    return {
        "mercado": mercado,
        "nombre_mercado": cfg["nombre"],
        "indice": indice,
        "nombre_indice": cfg["nombre_indice"],
        "rendimiento_indice_3m": round(rendimiento_indice, 2),
        "candado_sector_activo": candado_sector,
        "sectores_lideres": lideres if candado_sector else [],
        "nota": cfg.get("nota", ""),
        "acciones": filas,
    }


class handler(BaseHTTPRequestHandler):  # noqa: N801 - nombre requerido por Vercel
    def do_GET(self):  # noqa: N802
        try:
            qs = parse_qs(urlparse(self.path).query)
            mercado = qs.get("mercado", ["america"])[0].lower()
            candado_sector = qs.get("sector", ["0"])[0] in ("1", "true")
            if mercado not in MERCADOS:
                estado, cuerpo = 400, {
                    "error": f"Mercado desconocido: {mercado}. "
                             f"Validos: {', '.join(MERCADOS)}"
                }
            else:
                cuerpo = ejecutar_screening(mercado, candado_sector)
                estado = 200
        except Exception as exc:  # noqa: BLE001 - el frontend muestra el error
            estado, cuerpo = 500, {
                "error": f"No se pudo completar el screening: {exc}"
            }

        payload = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        # Cachea el resultado 5 min en el CDN: el screening usa datos diarios.
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    # Prueba local: python api/screen.py [america|europa|asia] [--sector]
    mercado_cli = sys.argv[1] if len(sys.argv) > 1 else "america"
    resultado = ejecutar_screening(mercado_cli, "--sector" in sys.argv)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
