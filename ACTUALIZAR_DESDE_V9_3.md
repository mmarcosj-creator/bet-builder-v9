# Actualizar el repositorio desde V9.3

## Archivos que debes reemplazar

Sube a la raíz del repositorio estos archivos con el nombre exacto:

- `app.py`
- `bet_builder_v8_1_robust.py`
- `bet_builder_v9_3_context.py`
- `bet_forecaster_v10.py`
- `scheduled_refresh.py`
- `self_test_v10.py`
- `requirements.txt`

También puedes subir `README.md`, `CRITERIOS_V10.md` y
`VERIFICACION_V10.md` como documentación.

## Desde el teléfono en GitHub

1. Abre el repositorio y pulsa **Add file > Upload files**.
2. Selecciona los archivos anteriores.
3. Si GitHub muestra el mismo nombre, confirma que se reemplace la versión
   existente. No permitas sufijos `(1)` o `(2)`.
4. Escribe `Actualizar a V10.1` en **Commit changes** y confirma el commit en
   la rama `main`.
5. En Streamlit Community Cloud abre **Manage app** y pulsa **Reboot app**.
6. Espera la primera descarga de datos y comprueba que el título diga
   `Forecaster Fútbol V10 PRO`.

El archivo antiguo `bet_builder_v9_market_optimizer.py` ya no es importado por
la nueva aplicación. Puedes conservarlo como respaldo, pero no debe ser el
archivo principal de Streamlit.

## Comprobación

- Deben aparecer seis mercados juntos por partido.
- No debe aparecer `CuotaJustaModelo`, cuota estimada ni hándicap asiático.
- Los partidos ya iniciados no deben mostrarse.
- La sección de validación debe indicar qué mercados superan o no la base.
- Un mercado que no supera la base debe quedar rojo.
