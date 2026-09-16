# Forecaster Fútbol V10.3 Gatuno PRO

V10.3 es un sistema experimental de pronóstico **individual** por partido. Muestra seis mercados con semáforo simple y mantiene una auditoría prospectiva inmutable.

## Qué muestra

1. Resultado 1X2: local, empate o visitante.
2. Goles del primer tiempo: más/menos de 1.5.
3. Córners del primer tiempo: más/menos de 4.5.
4. Tarjetas amarillas totales: más/menos de 4.5.
5. El local marca: sí/no sobre 0.5.
6. El visitante marca: sí/no sobre 0.5.

No genera hándicaps asiáticos, combinadas ni cuotas estimadas.

## Significado de colores

- **VERDE:** el modelo superó su referencia fuera de muestra, cumple soporte, límite conservador y fiabilidad, la alineación está confirmada y no existe alerta alta de rotación.
- **AMARILLO:** señal intermedia o a la espera de alineación/contexto.
- **ROJO:** no recomendada; modelo sin ventaja fuera de muestra, soporte insuficiente o mercado no evaluable.
- **MEJOR OPCIÓN:** máximo una verde por partido. No significa certeza ni invita a combinar mercados.

## Corrección crítica frente a V10.2

V10.2 reconstruía colores usando solamente la probabilidad seleccionada. Eso podía convertir en verde un modelo que su propia validación marcaba como `NO SUPERA BASE OOS`. V10.3 conserva el semáforo del motor; la auditoría solo puede degradarlo y nunca promocionarlo.

## Auditoría y aprendizaje

- Congela la primera predicción emitida antes del inicio y nunca la sobrescribe.
- Cierra automáticamente resultados 1X2, goles, goles 1T, córners 1T y tarjetas cuando la fuente ofrece el dato verificable.
- Marca estadísticas ausentes como `NO_EVALUABLE`; no las cuenta como fallo ni acierto.
- Aprende de forma conservadora por mercado: con 60 resultados verdes puede degradar señales futuras si el rendimiento se deteriora.
- No publica una tasa ficticia de 0% cuando todavía no existen resultados cerrados.
- La etiqueta de consistencia exige 300 verdes resueltos, 30 días, al menos cuatro mercados con soporte y límite inferior Wilson de 95%. No equivale a rentabilidad sin cuotas reales.

## Fútbol argentino e interligas CONMEBOL

La hipótesis de mayor interrupción, tarjetas o menor producción de córners no se introduce como penalización fija. El origen del club, cruce de país, forma de tarjetas/córners, localía y competición son variables del modelo. Para córners 1T y tarjetas en cruces argentinos interliga, la señal queda bloqueada si el subgrupo no tiene al menos 30 antecedentes y no supera temporalmente su referencia.

## Instalación

```bash
pip install -r requirements.txt
streamlit run app.py
```

La primera actualización tarda porque descarga y valida históricos. Las aperturas siguientes leen la caché de inmediato; usa **Actualizar y auditar resultados** cuando quieras recalcular.

## Archivos principales

- `app.py`: interfaz y Excel simplificado.
- `bet_forecaster_v10.py`: variables prepartido, entrenamiento, calibración y pronósticos.
- `gatuno_audit.py`: historial inmutable, cierre de resultados y cortacircuito adaptativo.
- `scheduled_refresh.py`: actualización no interactiva.
- `self_test_v10_3.py`: pruebas offline de las protecciones críticas.
- `CRITERIOS_V10_3.md`: reglas estadísticas y decisiones de diseño.
- `VERIFICACION_V10_3.md`: hallazgos de auditoría y límites actuales.
- `ACTUALIZAR_A_V10_3.md`: pasos de actualización en GitHub/Streamlit.

## Advertencia honesta

Este software todavía debe acumular resultados prospectivos. Una tasa de acierto no demuestra beneficio; para medir rentabilidad se necesitan cuotas reales completas, registradas antes del partido, y reglas de liquidación equivalentes. No garantiza aciertos ni ganancias.
