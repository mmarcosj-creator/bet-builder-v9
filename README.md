# GATUNO V15 CLEAN

## Objetivo
Instalación limpia separada de la V14/V10.4.2. No reutiliza `app_data_v10` ni cachés antiguas.

## Flujo nuevo
1. Genera pronósticos y congela la versión/criterios usados.
2. Después del cierre intenta resolver resultados reales.
3. Clasifica el desempeño por mercado: resultado, goles 1T, corners 1T, tarjetas, gol local y gol visitante.
4. El Vigilante Gatuno observa una ventana de 7 días.
5. Si detecta deterioro repetido, crea una PROPUESTA.
6. El usuario decide:
   - Aplicar ajuste temporal y reversible durante 7 días.
   - Observar 7 días adicionales sin cambiar el criterio.
7. Nunca se reescribe un pronóstico histórico con un criterio nuevo.

## Importante
- La alineación NO bloquea la señal.
- Si no existe dato confiable de corners 1T, ese resultado queda sin resolver; no se inventa.
- La semana sirve como alerta temprana. El sistema exige también repetición en varios días y diferencia respecto de la probabilidad esperada.
- Los ajustes son temporales, registrados y reversibles.

## Archivos
- app.py
- bet_builder_v8_1_robust.py
- bet_forecaster_v10.py
- bet_builder_v9_3_context.py
- gatuno_audit.py
- adaptive_monitor.py
- model_monitor.py
- embedded_history.py
- requirements.txt
