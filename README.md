# BET BUILDER V9.3 CONTEXT PRO

Versión conservadora de V9.2. Conserva la probabilidad conjunta directa, el
control de dependencia, el backtest walk-forward y la cuota real mínima 4.20,
pero añade una capa explícita de contexto competitivo y rotación.

## Archivos de ejecución

- `app.py`
- `bet_builder_v8_1_robust.py`
- `bet_builder_v9_3_context.py`
- `bet_builder_v9_3_context_optimizer.py`
- `scheduled_refresh.py`
- `self_test_v9_3.py`
- `CRITERIOS_V9_3.md`
- `requirements.txt`

No mezclar estos archivos con copias `(1)` o `(2)` ni con el optimizador V9.2.

## Inicio

```bash
pip install -r requirements.txt
python self_test_v9_3.py
streamlit run app.py
```

El acceso directo anterior puede conservarse si ejecuta `streamlit run app.py`
desde esta carpeta.

## Regla operativa

Una combinación solo puede llegar a `VALIDA` si cumple todo lo siguiente:

1. Máximo tres selecciones reales.
2. Líneas idénticas a las generadas y firma de combinación coincidente.
3. Estado previo `COTIZAR`, alineación confirmada, línea base de al menos tres
   onces anteriores por equipo y cupo de cartera.
4. Sin alerta alta de rotación en mercados sensibles.
5. Cuota real igual o mayor que 4.20 y que `CuotaRequerida`.
6. Sin dislocación extrema entre cuota real y cuota justa que sugiera un
   error de mercado, línea o tipo de hándicap.

La aplicación permite como máximo dos partidos por día y uno por competición.
No aumenta la probabilidad por el solo hecho de ser Champions, Libertadores o
Sudamericana. Usa la fase real, la carga y el siguiente compromiso.

## Estados importantes

- `ESPERAR_ALINEACION`: reejecutar cerca del comienzo del partido.
- `VIGILAR_SIN_BASELINE_XI`: el once existe, pero aún no hay tres alineaciones
  previas para distinguir titulares habituales de rotación.
- `COTIZAR`: puede reproducirse exactamente en la casa para conocer la cuota.
- `LABORATORIO`: mercado sin validación homogénea suficiente.
- `DESCARTAR_CONTEXTO`: rotación o condición competitiva incompatible.
- `CONFIRMAR_COMBINACION`: falta confirmar que las líneas son idénticas.
- `REVISAR_PRECIO_MAPPING`: probable confusión de mercado o línea.
- `VALIDA`: supera los filtros estadísticos y económicos; no garantiza ganar.

## Límites honestos

La alineación confirmada de ESPN se consulta únicamente cerca del partido. El
archivo `app_data_v9_3/lineup_history.json` se forma prospectivamente y permite
comparar cada once con hasta cinco alineaciones previas. El riesgo de rotación
también depende de que ESPN publique el calendario y la fase. Cuando faltan
datos, la confianza disminuye; no se completa la información por suposición.

El backtest histórico sigue siendo sin fuga temporal. La nueva capa de
alineaciones/calendario no se atribuye retroactivamente a fechas en las que el
sistema no almacenó esa información. Debe validarse prospectivamente y con
cuotas reales registradas; 300–500 apuestas es una muestra de control razonable,
no una promesa de rentabilidad.

## Juego responsable

No usar crédito ni dinero destinado a vivienda, alimentos, servicios o
obligaciones. No incrementar el importe para recuperar pérdidas. Este software
es experimental y puede perder el total apostado.
