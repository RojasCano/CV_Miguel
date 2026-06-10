"""Tests del Filtro de los Tres Candados con datos sinteticos deterministas.

Ejecutar con: ``python -m pytest screener/`` o ``python screener/test_filtro_tres_candados.py``
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from filtro_tres_candados import filtrar_tres_candados

SESIONES = 300
FECHAS = pd.bdate_range(end="2026-06-09", periods=SESIONES)
INDICE = "^TEST"


def _accion(
    precio_inicial: float,
    crecimiento_diario: float,
    volumen: float,
    market_cap: float,
    sector: str | None = "Tecnologia",
) -> dict:
    """Genera una accion sintetica con crecimiento geometrico constante."""
    cierres = precio_inicial * (1 + crecimiento_diario) ** np.arange(SESIONES)
    historico = pd.DataFrame(
        {"Close": cierres, "Volume": np.full(SESIONES, volumen)}, index=FECHAS
    )
    return {"historico": historico, "market_cap": market_cap, "sector": sector}


def _datos_base() -> dict:
    """Universo de prueba: el indice crece un 0.05% diario (~4.6% en 90 dias)."""
    return {
        INDICE: {"historico": _accion(4000, 0.0005, 0, 0, None)["historico"]},
        # Supera todo: alcista fuerte, liquida y de gran capitalizacion.
        "GANADORA": _accion(100, 0.003, 5_000_000, 50e9, "Tecnologia"),
        # Falla Candado 1A: small cap.
        "SMALLCAP": _accion(100, 0.003, 5_000_000, 0.5e9, "Tecnologia"),
        # Falla Candado 1B: volumen efectivo ridiculo.
        "ILIQUIDA": _accion(100, 0.003, 100, 50e9, "Tecnologia"),
        # Falla Candado 2: tendencia bajista (precio < SMA200, pendiente negativa).
        "BAJISTA": _accion(100, -0.002, 5_000_000, 50e9, "Energia"),
        # Falla Candado 2C: alcista pero mas debil que el indice (alpha negativo).
        "DEBIL": _accion(100, 0.0002, 5_000_000, 50e9, "Consumo"),
        # Datos corruptos: debe descartarse sin romper la ejecucion.
        "ROTA": {"historico": pd.DataFrame({"Close": [1.0]}, index=[FECHAS[0]])},
        # Refuerzos sectoriales para que la mediana de cada sector sea representativa.
        "TECH2": _accion(50, 0.0028, 4_000_000, 30e9, "Tecnologia"),
        "ENERGIA2": _accion(80, -0.0015, 4_000_000, 30e9, "Energia"),
        "CONSUMO2": _accion(60, 0.0003, 4_000_000, 30e9, "Consumo"),
    }


def test_candados_obligatorios() -> None:
    datos = _datos_base()
    resultado = filtrar_tres_candados(
        universo_acciones=[t for t in datos if t != INDICE],
        datos_mercado=datos,
        ticker_indice_referencia=INDICE,
    )
    aprobadas = set(resultado["Ticker"])
    assert aprobadas == {"GANADORA", "TECH2"}, aprobadas
    fila = resultado[resultado["Ticker"] == "GANADORA"].iloc[0]
    assert fila["Distancia SMA200 (%)"] > 0
    assert fila["Rendimiento 3M (%)"] > 0


def test_candado_sector() -> None:
    datos = _datos_base()
    resultado = filtrar_tres_candados(
        universo_acciones=[t for t in datos if t != INDICE],
        datos_mercado=datos,
        ticker_indice_referencia=INDICE,
        activar_candado_sector=True,
    )
    # Tecnologia es el unico sector en el Top 30% (3 sectores -> top 1).
    assert set(resultado["Ticker"]) == {"GANADORA", "TECH2"}
    assert (resultado["Sector"] == "Tecnologia").all()


def test_indice_ausente_lanza_error() -> None:
    datos = _datos_base()
    try:
        filtrar_tres_candados(["GANADORA"], datos, "^NOEXISTE")
    except ValueError:
        pass
    else:
        raise AssertionError("Debio lanzar ValueError por benchmark ausente")


if __name__ == "__main__":
    test_candados_obligatorios()
    test_candado_sector()
    test_indice_ausente_lanza_error()
    print("OK: todos los tests pasan")
