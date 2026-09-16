# Actualizar tu aplicación a V10.3 Gatuno PRO

## En GitHub desde el celular

1. Abre el repositorio que usa tu aplicación de Streamlit.
2. Pulsa **Add file → Upload files**.
3. Sube estos archivos con sus nombres exactos:
   - `app.py`
   - `bet_forecaster_v10.py`
   - `gatuno_audit.py` (nuevo)
   - `bet_builder_v8_1_robust.py`
   - `bet_builder_v9_3_context.py`
   - `scheduled_refresh.py`
   - `self_test_v10_3.py`
   - `requirements.txt`
4. Confirma **Commit changes** sobre la rama `main`.
5. En Streamlit, abre **Manage app → Reboot app**.
6. Al abrir, pulsa una vez **Generar pronósticos V10.3**. Después la pantalla cargará desde caché.

GitHub sustituye los archivos del mismo nombre. No conserves copias con `(1)`, `(2)` o nombres diferentes, porque Python no las importará.

## Historial

V10.3 crea `app_data_v10/historial_pronosticos_v103.csv`. El historial antiguo de V10.2 no se importa como evidencia porque sus señales verdes fueron recalculadas incorrectamente y no tenían una identidad estable por evento/mercado/línea.

En Streamlit Community Cloud el almacenamiento local puede reiniciarse al redesplegar. Para una auditoría permanente, programa `scheduled_refresh.py` en una máquina o flujo con volumen persistente y conserva el CSV. No alteres manualmente predicciones ya emitidas.

## Uso diario

- Abre la aplicación: mostrará la última caché inmediatamente.
- Pulsa **Actualizar y auditar resultados** después de terminar partidos o cerca del inicio para revisar alineaciones.
- Apuesta, si decides hacerlo, solo en una selección verde y evita convertir las seis filas en combinada.
- Descarga el Excel para conservar una copia de auditoría.

## Comprobación local opcional

```bash
python self_test_v10_3.py
streamlit run app.py
```
