"""Ejemplo de uso real del Filtro de los Tres Candados con datos de Yahoo Finance.

Requiere: ``pip install yfinance pandas numpy``

Descarga el historico diario de un universo de ejemplo (componentes liquidos
del S&P 500) junto con el indice de referencia, construye la estructura
``datos_mercado`` que espera el screener y ejecuta el filtro con el candado
sectorial activado.
"""

from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from filtro_tres_candados import filtrar_tres_candados

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

UNIVERSO = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "UNH",
    "XOM", "JNJ", "PG", "AVGO", "HD", "MRK", "COST", "ABBV", "KO", "PEP",
]
INDICE_REFERENCIA = "^GSPC"  # S&P 500


def descargar_datos_mercado(tickers: list[str], indice: str) -> dict[str, dict[str, Any]]:
    """Construye ``datos_mercado`` descargando historicos y fundamentales.

    Las acciones cuya descarga falle simplemente se omiten: el screener ya
    gestiona de forma segura los tickers ausentes o con datos incompletos.
    """
    datos: dict[str, dict[str, Any]] = {}
    todos = tickers + [indice]
    # Descarga en bloque (una sola peticion HTTP para todos los historicos).
    historicos = yf.download(todos, period="2y", interval="1d", group_by="ticker",
                             auto_adjust=True, progress=False)

    for ticker in todos:
        try:
            historico = historicos[ticker][["Close", "Volume"]].dropna(subset=["Close"])
            entrada: dict[str, Any] = {"historico": historico}
            if ticker != indice:
                info = yf.Ticker(ticker).info
                entrada["market_cap"] = info.get("marketCap")
                entrada["sector"] = info.get("sector")
            datos[ticker] = entrada
        except Exception as exc:  # noqa: BLE001 - omitir tickers problematicos
            logging.warning("No se pudieron descargar datos de %s: %s", ticker, exc)
    return datos


if __name__ == "__main__":
    datos_mercado = descargar_datos_mercado(UNIVERSO, INDICE_REFERENCIA)
    resultado = filtrar_tres_candados(
        universo_acciones=UNIVERSO,
        datos_mercado=datos_mercado,
        ticker_indice_referencia=INDICE_REFERENCIA,
        activar_candado_sector=True,
    )
    print("\n=== Acciones que superan el Filtro de los Tres Candados ===")
    print(resultado.to_string(index=False) if not resultado.empty
          else "Ninguna accion supera el filtro.")
