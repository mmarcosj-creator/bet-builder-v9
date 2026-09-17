# Hotfix V10.4.2 — histórico autocontenido

Esta versión elimina la dependencia obligatoria del archivo externo `historical_fallback.csv.gz`.

## Sube estos cuatro archivos a GitHub

1. `app.py`
2. `bet_builder_v8_1_robust.py`
3. `bet_forecaster_v10.py`
4. `embedded_history.py` (nuevo)

`embedded_history.py` contiene el mismo histórico comprimido y comprueba su integridad antes de usarlo. No genera partidos ni resultados sintéticos.

## Reinicio

1. Confirma el commit.
2. En Streamlit usa **Manage app → Clear cache → Reboot app**.
3. Comprueba que el encabezado muestre `V10.4.2`.
4. Pulsa **🐾 Generar pronósticos V10.4.2** una sola vez.

Si el encabezado todavía muestra V10.4.1, Streamlit no ha cargado el commit nuevo.
