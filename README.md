# Forecaster Fútbol V10.1 PRO

V10.1 reemplaza el antiguo optimizador de combinadas por pronósticos
individuales y auditables. No genera una cuota imaginaria, no usa hándicap
asiático y no etiqueta un equipo como favorito mediante una aproximación.

## Qué muestra por partido

1. Resultado 1X2: local, empate o visitante.
2. Goles del primer tiempo: más/menos de 1.5.
3. Córners del primer tiempo: más/menos de 4.5, únicamente cuando existen
   conteos reales y validación suficiente.
4. Tarjetas amarillas totales: más/menos de 4.5.
5. El equipo local marca o no marca (línea 0.5).
6. El equipo visitante marca o no marca (línea 0.5).

Los seis mercados se muestran juntos para estudiar el encuentro, no para
recomendar que se combinen.

## Semáforo

- **VERDE:** probabilidad, límite conservador, soporte, calibración temporal y
  contexto superan todos los umbrales.
- **AMARILLO:** evidencia intermedia.
- **ROJO:** mercado muy riesgoso, modelo que no supera la base, datos
  insuficientes o contexto incierto.

Un verde no garantiza acierto ni rentabilidad. Si un modelo no mejora el
Brier/MAE de la referencia en datos posteriores, V10 limita su fiabilidad y
no permite que aparezca verde o amarillo.

## Datos y criterios

- Elo previo al partido y ventaja de localía.
- Forma con decaimiento temporal y separación local/visitante.
- Posición y puntos por partido calculados antes de cada encuentro.
- Campaña actual y memoria reducida de la campaña previa.
- Goles, goles al descanso, córners y tarjetas a favor/en contra.
- Descanso, partidos en 14 días, fase competitiva, siguiente compromiso,
  riesgo de rotación y alineación confirmada cuando está disponible.
- Interacción de clubes argentinos contra otra liga en Libertadores o
  Sudamericana. No aplica una reducción fija: exige 30 antecedentes
  comparables antes de ajustar córners 1T y valida la señal fuera de muestra.

## Instalación y Streamlit Cloud

Sube todos estos archivos a la raíz del repositorio sin `(1)` ni nombres
duplicados. En Streamlit Community Cloud selecciona `app.py` como archivo
principal.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

La primera ejecución puede tardar porque descarga y resume el histórico. Las
siguientes reutilizan cachés. El botón **Actualizar pronósticos** elimina de la
vista los partidos que ya comenzaron y usa la ventana desde el momento actual.

Si vienes de V9.3, sigue `ACTUALIZAR_DESDE_V9_3.md` para reemplazar los
archivos desde GitHub móvil y reiniciar Streamlit.

## Auditoría de 100 partidos

```bash
python self_test_v10.py
```

El script fija primero el corte temporal, sortea 100 partidos posteriores con
semilla reproducible y guarda detalle, resumen y validación en
`self_test_output/`. No calcula ganancias sin las cuotas reales históricas de
cada mercado: hacerlo con una cuota supuesta produciría un ROI ficticio.

## Límites

- Las tarjetas se modelan como amarillas `HY + AY`; la liquidación de rojas y
  dobles amarillas depende de las reglas de cada casa.
- Si ESPN no entrega córners del primer tiempo, el mercado aparece como
  `SIN PRONÓSTICO`.
- Las probabilidades son experimentales. La viabilidad económica solo puede
  evaluarse con cuotas reales archivadas y un backtest completamente fuera de
  muestra.
