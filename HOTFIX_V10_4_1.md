# Hotfix V10.4.1 — primera ejecución

La captura con los mensajes `ESPN no devolvió partidos` y `No se obtuvo histórico utilizable` indica que fallaron la fuente remota y el archivo de respaldo no estaba disponible en el despliegue.

## Archivos mínimos que debes reemplazar

1. `app.py`
2. `bet_builder_v8_1_robust.py`
3. `bet_forecaster_v10.py`
4. `self_test_v10_4.py` (recomendado)
5. `historical_fallback.csv.gz` (nuevo y obligatorio en la raíz)

El archivo `historical_fallback.csv.gz` debe quedar al mismo nivel que `app.py`, no dentro de otra carpeta descargada.

## Después de subirlos

1. Confirma el commit en GitHub.
2. Abre Streamlit y entra en **Manage app**.
3. Pulsa **Reboot app**.
4. Si aún muestra el error anterior, usa **Clear cache** y reinicia otra vez.
5. Pulsa **🐾 Generar pronósticos V10.4.1** una sola vez.

## Qué corrige

- agrega encabezado compatible en las solicitudes JSON a ESPN;
- recupera calendarios día por día cuando ESPN rechaza un intervalo;
- consulta competiciones en paralelo para reducir el tiempo de espera;
- usa `fixtures.csv` de Football-Data como calendario europeo secundario;
- busca el histórico de respaldo tanto en `bundled_data/` como junto a `app.py`.

Si las dos fuentes de calendario están realmente caídas, la aplicación mostrará un error explícito y no fabricará partidos.
