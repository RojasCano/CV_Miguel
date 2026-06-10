"""
Filtro de los Tres Candados — Screener de acciones de grado institucional.
===========================================================================

Implementa un cribado secuencial sobre un universo de acciones:

    Candado 1 (obligatorio)  -> Liquidez institucional (Market Cap y volumen efectivo).
    Candado 2 (obligatorio)  -> Tendencia (SMA 200), pendiente alcista y fuerza
                                relativa (alpha 3M) frente a un indice de referencia.
    Candado 3 (opcional)     -> Entorno sectorial: la accion debe pertenecer al
                                Top 30% de sectores por rendimiento mediano a 3 meses.

Formato de datos esperado (``datos_mercado``)
---------------------------------------------
Un diccionario indexado por ticker. Cada entrada debe contener:

    {
        "historico":  pd.DataFrame con DatetimeIndex ordenado ascendente y
                      columnas ["Close", "Volume"] (precios diarios ajustados),
        "market_cap": float  (capitalizacion en la divisa local),
        "sector":     str    (opcional; necesario solo para el Candado 3),
    }

El ticker del indice de referencia debe estar presente en ``datos_mercado``
con, al menos, la clave ``"historico"`` (columna ``Close``).

Las acciones con datos incompletos o corruptos se descartan de forma segura
sin interrumpir la ejecucion (se registra un WARNING via ``logging``).

Ejemplo rapido
--------------
>>> resultado = filtrar_tres_candados(
...     universo_acciones=["AAPL", "MSFT", "KO"],
...     datos_mercado=datos,
...     ticker_indice_referencia="^GSPC",
...     activar_candado_sector=True,
... )
>>> print(resultado)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parametros del algoritmo (centralizados para facilitar el ajuste fino)
# ---------------------------------------------------------------------------
MIN_MARKET_CAP: float = 1_000_000_000        # Candado 1A: > 1.000 M divisa local
MIN_VOLUMEN_EFECTIVO: float = 20_000_000     # Candado 1B: precio * vol. medio 20d
VENTANA_VOLUMEN: int = 20                    # Sesiones para el volumen medio
VENTANA_SMA: int = 200                       # Sesiones de la media movil
SESIONES_PENDIENTE: int = 5                  # Lookback para la pendiente de la SMA
DIAS_RENDIMIENTO: int = 90                   # Dias naturales para el rendimiento 3M
PERCENTIL_TOP_SECTORES: float = 0.30         # Candado 3: top 30% de sectores


@dataclass(frozen=True)
class MetricasAccion:
    """Metricas precalculadas de una accion, listas para evaluar los candados."""

    ticker: str
    precio_actual: float
    market_cap: float
    volumen_medio_20d: float
    sma_200: float
    sma_200_hace_5: float
    rendimiento_3m: float
    sector: Optional[str]

    @property
    def volumen_efectivo(self) -> float:
        """Volumen medio diario negociado en divisa (precio * volumen medio 20d)."""
        return self.precio_actual * self.volumen_medio_20d

    @property
    def distancia_sma200_pct(self) -> float:
        """Distancia porcentual del precio actual sobre su SMA 200."""
        return (self.precio_actual / self.sma_200 - 1.0) * 100.0


# ---------------------------------------------------------------------------
# Calculo de metricas (vectorizado con Pandas/NumPy)
# ---------------------------------------------------------------------------
def _rendimiento_3m(cierres: pd.Series) -> float:
    """Rendimiento porcentual en los ultimos ``DIAS_RENDIMIENTO`` dias naturales.

    Usa ``Series.asof`` para localizar el cierre disponible mas cercano (hacia
    atras) a la fecha objetivo, de modo que festivos y fines de semana no
    provoquen fallos por fechas inexistentes.
    """
    fecha_final = cierres.index[-1]
    fecha_inicial = fecha_final - pd.Timedelta(days=DIAS_RENDIMIENTO)
    precio_inicial = cierres.asof(fecha_inicial)
    if pd.isna(precio_inicial) or precio_inicial <= 0:
        raise ValueError("Historico insuficiente para calcular el rendimiento 3M")
    return (float(cierres.iloc[-1]) / float(precio_inicial) - 1.0) * 100.0


def _calcular_metricas(
    ticker: str,
    datos_accion: Mapping[str, Any],
) -> MetricasAccion:
    """Extrae y calcula todas las metricas de una accion en una sola pasada.

    Lanza ``KeyError``/``ValueError`` si faltan datos o el historico es corto;
    el llamador captura la excepcion y descarta la accion de forma segura.
    """
    historico: pd.DataFrame = datos_accion["historico"]
    cierres = historico["Close"].astype(float).dropna()
    volumenes = historico["Volume"].astype(float)

    if len(cierres) < VENTANA_SMA + SESIONES_PENDIENTE:
        raise ValueError(
            f"Historico insuficiente: {len(cierres)} sesiones "
            f"(minimo {VENTANA_SMA + SESIONES_PENDIENTE})"
        )

    # Operaciones vectorizadas: rolling de Pandas (C optimizado), sin bucles.
    sma_200 = cierres.rolling(window=VENTANA_SMA).mean()
    volumen_medio_20d = float(
        volumenes.rolling(window=VENTANA_VOLUMEN).mean().iloc[-1]
    )

    market_cap = float(datos_accion["market_cap"])
    sector = datos_accion.get("sector") or datos_accion.get("industry")

    metricas = MetricasAccion(
        ticker=ticker,
        precio_actual=float(cierres.iloc[-1]),
        market_cap=market_cap,
        volumen_medio_20d=volumen_medio_20d,
        sma_200=float(sma_200.iloc[-1]),
        sma_200_hace_5=float(sma_200.iloc[-(SESIONES_PENDIENTE + 1)]),
        rendimiento_3m=_rendimiento_3m(cierres),
        sector=str(sector) if sector else None,
    )

    # Validacion final: cualquier NaN invalida la accion.
    valores = (
        metricas.precio_actual,
        metricas.market_cap,
        metricas.volumen_medio_20d,
        metricas.sma_200,
        metricas.sma_200_hace_5,
        metricas.rendimiento_3m,
    )
    if any(pd.isna(v) for v in valores):
        raise ValueError("Metricas con valores NaN")
    return metricas


# ---------------------------------------------------------------------------
# Candados
# ---------------------------------------------------------------------------
def _pasa_candado_1(m: MetricasAccion) -> bool:
    """Candado 1 — Liquidez institucional."""
    return m.market_cap > MIN_MARKET_CAP and m.volumen_efectivo > MIN_VOLUMEN_EFECTIVO


def _pasa_candado_2(m: MetricasAccion, rendimiento_indice_3m: float) -> bool:
    """Candado 2 — Tendencia, pendiente de la SMA 200 y alpha frente al indice."""
    tendencia_alcista = m.precio_actual > m.sma_200
    pendiente_positiva = m.sma_200 > m.sma_200_hace_5
    alpha_positivo = m.rendimiento_3m > rendimiento_indice_3m
    return tendencia_alcista and pendiente_positiva and alpha_positivo


def _sectores_lideres(rendimientos_por_sector: dict[str, list[float]]) -> set[str]:
    """Candado 3 — Devuelve el conjunto de sectores en el Top 30% por mediana 3M."""
    if not rendimientos_por_sector:
        return set()
    medianas = pd.Series(
        {sector: float(np.median(r)) for sector, r in rendimientos_por_sector.items()}
    )
    umbral = medianas.quantile(1.0 - PERCENTIL_TOP_SECTORES)
    return set(medianas[medianas >= umbral].index)


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------
def filtrar_tres_candados(
    universo_acciones: Iterable[str],
    datos_mercado: Mapping[str, Mapping[str, Any]],
    ticker_indice_referencia: str,
    activar_candado_sector: bool = False,
) -> pd.DataFrame:
    """Aplica el Filtro de los Tres Candados sobre un universo de acciones.

    Parameters
    ----------
    universo_acciones
        Iterable de tickers a analizar (lista, claves de un dict, columna de
        un DataFrame, etc.).
    datos_mercado
        Diccionario ``{ticker: {"historico": DataFrame, "market_cap": float,
        "sector": str}}``. Debe incluir tambien el indice de referencia.
    ticker_indice_referencia
        Ticker del indice contra el que se mide la fuerza relativa
        (ej. ``'^GSPC'`` para el S&P 500, ``'^STOXX50E'`` para el EuroStoxx).
    activar_candado_sector
        Si es ``True``, exige ademas que la accion pertenezca al Top 30% de
        sectores por rendimiento mediano a 3 meses. Por defecto ``False``.

    Returns
    -------
    pd.DataFrame
        Columnas: ``Ticker``, ``Precio Actual``, ``Market Cap``,
        ``Distancia SMA200 (%)``, ``Rendimiento 3M (%)`` y ``Sector``,
        ordenado por rendimiento 3M descendente. Vacio si nada supera el filtro.

    Raises
    ------
    ValueError
        Si no es posible calcular el rendimiento del indice de referencia
        (sin el benchmark el Candado 2 no es evaluable).
    """
    universo = [str(t) for t in universo_acciones]

    # --- Benchmark: imprescindible para el Candado 2C -----------------------
    try:
        cierres_indice = (
            datos_mercado[ticker_indice_referencia]["historico"]["Close"]
            .astype(float)
            .dropna()
        )
        rendimiento_indice_3m = _rendimiento_3m(cierres_indice)
    except Exception as exc:  # noqa: BLE001 - se relanza con contexto claro
        raise ValueError(
            f"No se pudo calcular el rendimiento del indice "
            f"'{ticker_indice_referencia}': {exc}"
        ) from exc

    logger.info(
        "Benchmark %s | Rendimiento 3M: %.2f%%",
        ticker_indice_referencia,
        rendimiento_indice_3m,
    )

    candidatas: list[MetricasAccion] = []
    rendimientos_por_sector: dict[str, list[float]] = {}

    for ticker in universo:
        if ticker == ticker_indice_referencia:
            continue
        # Robustez: cualquier fallo (datos faltantes, historico corto, tipos
        # corruptos...) descarta la accion sin detener el screening.
        try:
            metricas = _calcular_metricas(ticker, datos_mercado[ticker])
        except Exception as exc:  # noqa: BLE001 - descarte seguro por diseno
            logger.warning("Descartada %s por datos invalidos: %s", ticker, exc)
            continue

        # El Candado 3 se calcula sobre TODO el universo con datos validos,
        # no solo sobre las supervivientes de los candados 1 y 2.
        if metricas.sector:
            rendimientos_por_sector.setdefault(metricas.sector, []).append(
                metricas.rendimiento_3m
            )

        # Cribado secuencial: descarte inmediato al fallar un candado.
        if not _pasa_candado_1(metricas):
            continue
        if not _pasa_candado_2(metricas, rendimiento_indice_3m):
            continue
        candidatas.append(metricas)

    # --- Candado 3 (opcional) ----------------------------------------------
    if activar_candado_sector:
        lideres = _sectores_lideres(rendimientos_por_sector)
        logger.info("Sectores lideres (Top %.0f%%): %s",
                    PERCENTIL_TOP_SECTORES * 100, sorted(lideres))
        candidatas = [m for m in candidatas if m.sector in lideres]

    # --- Salida --------------------------------------------------------------
    resultado = pd.DataFrame(
        [
            {
                "Ticker": m.ticker,
                "Precio Actual": round(m.precio_actual, 2),
                "Market Cap": m.market_cap,
                "Distancia SMA200 (%)": round(m.distancia_sma200_pct, 2),
                "Rendimiento 3M (%)": round(m.rendimiento_3m, 2),
                "Sector": m.sector,
            }
            for m in candidatas
        ],
        columns=[
            "Ticker",
            "Precio Actual",
            "Market Cap",
            "Distancia SMA200 (%)",
            "Rendimiento 3M (%)",
            "Sector",
        ],
    )
    if not resultado.empty:
        resultado = resultado.sort_values(
            "Rendimiento 3M (%)", ascending=False
        ).reset_index(drop=True)

    logger.info(
        "Screening completado: %d/%d acciones superan el filtro",
        len(resultado),
        len(universo),
    )
    return resultado
