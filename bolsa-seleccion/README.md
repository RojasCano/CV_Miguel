# 🔐 Bolsa Selección — Filtro de los Tres Candados

Aplicación web para cribar acciones de los principales mercados del mundo
(América, Europa y Asia) con el algoritmo **Filtro de los Tres Candados**:

1. **Liquidez institucional** — Market cap > 1.000 M y volumen efectivo medio
   de 20 sesiones > 20 M (divisa local).
2. **Tendencia y fuerza relativa** — Precio > SMA 200, SMA 200 con pendiente
   alcista y rendimiento 3M superior al del índice de referencia
   (S&P 500, EURO STOXX 50 o Nikkei 225 según el mercado).
3. **Entorno sectorial (opcional)** — La acción debe pertenecer al Top 30 % de
   sectores por rendimiento mediano a 3 meses.

Los precios y volúmenes se descargan en tiempo real de Yahoo Finance. La
capitalización es un valor aproximado embebido (todo el universo son large
caps) para mantener la respuesta rápida.

## Estructura

| Archivo | Descripción |
|---|---|
| `index.html` | Interfaz web (estática, sin dependencias) |
| `api/screen.py` | Función serverless que ejecuta el screening |
| `api/filtro_tres_candados.py` | Núcleo del algoritmo (pandas/numpy vectorizado) |
| `api/universos.py` | Universos curados e índices por mercado |

## Desplegar en Vercel (una sola vez)

1. Entra en **[vercel.com/new](https://vercel.com/new)** con tu cuenta.
2. Importa este repositorio (`Bolsa_Seleccion`) y pulsa **Deploy** (no hay
   que configurar nada: Vercel detecta la API Python automáticamente).
3. Al terminar tendrás tu URL pública: `https://bolsa-seleccion.vercel.app`
   (o similar). Cada push a `main` redespliega solo.

## Probar en local sin Vercel

```bash
pip install -r requirements.txt
python api/screen.py america            # screening de América (JSON)
python api/screen.py europa --sector    # Europa con candado sectorial
```

> Herramienta educativa: no constituye recomendación de inversión.
