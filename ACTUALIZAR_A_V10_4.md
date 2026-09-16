# Actualizar a V10.4 Gatuno Adaptativo

## Antes de reemplazar archivos

1. Descarga desde la app el respaldo del historial si ya tienes resultados acumulados.
2. Conserva la carpeta `app_data_v10` si existe. No la borres.
3. En GitHub evita nombres como `app(1).py`: el archivo principal debe llamarse exactamente `app.py`.

## Archivos que debes subir o reemplazar

- `app.py`
- `adaptive_monitor.py` (nuevo)
- `gatuno_audit.py`
- `model_monitor.py`
- `bet_forecaster_v10.py`
- `bet_builder_v8_1_robust.py`
- `bet_builder_v9_3_context.py`
- `scheduled_refresh.py`
- `requirements.txt`

Los documentos y pruebas son recomendables, pero no son necesarios para arrancar la pantalla.

## En GitHub desde el celular

1. Abre el repositorio y toca **Add file → Upload files**.
2. Selecciona los archivos de V10.4.
3. Comprueba que no queden duplicados con `(1)`, `(2)` o nombres truncados.
4. Escribe `Actualizar a V10.4 Gatuno Adaptativo` y confirma **Commit changes**.
5. Streamlit reiniciará la aplicación. Si no lo hace, entra en **Manage app → Reboot**.

## Primera apertura

Pulsa **🐾 Generar pronósticos V10.4** una vez. Después la app abre desde caché. Al terminar una jornada, pulsa **Actualizar y auditar resultados**.

Si había un `historial_apuestas.csv` anterior, V10.4 lo migra automáticamente. Aun así, conserva tu respaldo fuera de Streamlit porque el almacenamiento local de Community Cloud puede reiniciarse.

## Cómo usar una alerta

- **🐾 Aplicar ajuste seguro:** empieza a filtrar futuras verdes del mercado indicado.
- **🔎 Observar 7 días:** no toca criterios y espera nueva evidencia.
- **↩️ Revertir:** desactiva un ajuste activo.

No edites manualmente `politica_adaptativa.json`, `propuestas_ajuste.csv` ni `historial_ajustes.csv`; la interfaz los gestiona y deja trazabilidad.
