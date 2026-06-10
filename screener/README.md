# Filtro de los Tres Candados

Screener de acciones en Python que aplica tres filtros secuenciales sobre un
universo masivo de tickers y devuelve solo los que cumplen criterios estrictos
de liquidez, tendencia y (opcionalmente) fuerza sectorial.

## Los tres candados

| Candado | Tipo | Criterios |
|---|---|---|
| **1 — Liquidez institucional** | Obligatorio | Market Cap > 1.000 M · Volumen efectivo medio 20d (precio × volumen) > 20 M |
| **2 — Tendencia y fuerza relativa** | Obligatorio | Precio > SMA 200 · SMA 200 con pendiente alcista (vs. hace 5 sesiones) · Rendimiento 3M > rendimiento 3M del índice de referencia |
| **3 — Entorno sectorial** | Opcional (`activar_candado_sector=True`) | El sector de la acción está en el Top 30% por rendimiento mediano a 3 meses |

## Instalación

```bash
pip install -r screener/requirements.txt
```

## Uso

```python
from screener import filtrar_tres_candados

resultado = filtrar_tres_candados(
    universo_acciones=["AAPL", "MSFT", "KO"],
    datos_mercado=datos,            # ver formato abajo
    ticker_indice_referencia="^GSPC",
    activar_candado_sector=True,
)
print(resultado)
```

`datos_mercado` es un diccionario por ticker (debe incluir también el índice):

```python
{
    "AAPL": {
        "historico": df,            # DataFrame diario con columnas Close y Volume
        "market_cap": 2.9e12,
        "sector": "Technology",
    },
    "^GSPC": {"historico": df_indice},
}
```

La salida es un `DataFrame` con `Ticker`, `Precio Actual`, `Market Cap`,
`Distancia SMA200 (%)`, `Rendimiento 3M (%)` y `Sector`, ordenado por
rendimiento 3M descendente.

Un ejemplo completo con descarga real de datos vía Yahoo Finance está en
[`ejemplo_uso.py`](ejemplo_uso.py).

## Robustez

Las acciones con datos faltantes o corruptos (sin volumen, sin market cap,
histórico insuficiente…) se descartan de forma segura con un `WARNING` en el
log, sin detener el screening. Solo la ausencia del índice de referencia lanza
una excepción (`ValueError`), ya que sin benchmark el Candado 2 no es evaluable.

## Tests

```bash
cd screener && python3 test_filtro_tres_candados.py
# o bien: python -m pytest screener/
```
