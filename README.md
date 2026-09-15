# BET BUILDER V9 PRO FINAL

Paquete completo para reemplazar el repositorio anterior.

## Archivos raíz
- app.py
- bet_builder_v8_1_robust.py
- bet_builder_v9_market_optimizer.py
- requirements.txt
- scheduled_refresh.py
- README.md

No uses archivos con (1), (2) o nombres duplicados.

## Regla de cuota
- cuota real < 4.20: DESCARTAR
- cuota real >= 4.20 pero < CuotaRequerida: NO ALCANZA MARGEN
- cuota real >= CuotaRequerida: VÁLIDA según el modelo

## Backtest
La app incluye el botón EJECUTAR BACKTEST 7 DÍAS.
Por defecto usa S/100 y cuota simulada 4.20, máximo 30 apuestas,
una apuesta por partido y sin forzar volumen.

La cuota del backtest es una referencia hipotética; no es una cuota histórica
real del Bet Builder.
