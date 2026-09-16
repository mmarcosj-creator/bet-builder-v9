# Forecaster Fútbol V10.4 Gatuno Adaptativo

V10.4 es un sistema experimental de pronósticos **individuales** por partido. Cierra resultados, mide el desempeño por mercado y propone ajustes conservadores sin modificar criterios a escondidas.

## Pantalla principal

Cada encuentro muestra seis mercados separados:

1. Resultado 1X2: local, empate o visitante.
2. Goles del primer tiempo: más/menos de 1.5.
3. Córners del primer tiempo: más/menos de 4.5.
4. Tarjetas amarillas totales: más/menos de 4.5.
5. El local marca: sí/no sobre 0.5.
6. El visitante marca: sí/no sobre 0.5.

No genera hándicaps asiáticos, combinadas ni cuotas inventadas.

## Colores Gatunos

- 🟢 **Buena evidencia:** superó la referencia temporal y cumple probabilidad, límite conservador, fiabilidad, soporte, alineación y contexto.
- 🟡 **Precaución:** señal intermedia o una verde degradada por una compuerta de seguridad.
- 🔴 **No recomendada:** evidencia insuficiente, sin cobertura o modelo que no supera su referencia.
- ⭐ **Mejor del partido:** como máximo una verde; no significa certeza ni invita a combinar.

## Vigilante Gatuno de 7 días

El programa analiza por separado resultado, goles 1T, córners 1T, tarjetas, gol local y gol visitante. Una alerta requiere:

- al menos 20 verdes resueltos;
- actividad en al menos 4 días de la ventana;
- deterioro confirmado por más de una señal: brecha frente a la probabilidad prometida, Brier, repetición diaria o caída frente a los 28 días anteriores.

Cuando la evidencia es suficiente aparecen dos botones:

- **🐾 Aplicar ajuste seguro:** endurece temporalmente el verde o pausa verdes durante 7 días si la caída es crítica.
- **🔎 Observar 7 días:** no cambia nada y vuelve a revisar una semana después.

El ajuste queda registrado, tiene vencimiento y puede revertirse. Nunca promociona amarillo/rojo a verde y nunca modifica partidos iniciados.

## Qué aprende y qué no

El motor estadístico se reentrena con resultados reales completos. El Vigilante no reentrena con el simple bit “acertado/fallado”; usa ese resultado para controlar el semáforo y detectar mala calibración. Esto evita que una racha corta haga que el sistema persiga sus propios errores.

Una semana sirve como alarma temprana, no como certificación. La etiqueta de consistencia sigue exigiendo 300 verdes resueltos, 30 días, cuatro mercados con soporte y límite Wilson. Tampoco prueba rentabilidad: para ROI hacen falta cuotas reales guardadas antes del partido.

## Historial y migración

La primera predicción de cada evento/mercado se guarda antes del inicio. Un ajuste confirmado puede actualizar **solo el color de seguridad** mientras el partido siga pendiente. Al llegar el kickoff, la fila queda congelada.

Si existe `app_data_v10/historial_apuestas.csv`, V10.4 lo migra automáticamente al historial nuevo para conservar aciertos y fallos anteriores.

## Instalación

```bash
pip install -r requirements.txt
streamlit run app.py
```

La primera generación puede tardar porque construye la caché. Las aperturas siguientes cargan esa caché. Usa **Actualizar y auditar resultados** al cerrar la jornada.

## Archivos principales

- `app.py`: interfaz móvil Gatuno, decisiones y Excel.
- `bet_forecaster_v10.py`: variables, entrenamiento, calibración y pronósticos.
- `gatuno_audit.py`: historial prospectivo y cierre de resultados.
- `adaptive_monitor.py`: diagnóstico semanal, propuestas, políticas y reversión.
- `model_monitor.py`: deterioro de métricas fuera de muestra por submodelo.
- `scheduled_refresh.py`: actualización no interactiva.
- `self_test_v10_4.py`: pruebas de las protecciones adaptativas.
- `CRITERIOS_V10_4.md`: reglas estadísticas completas.
- `ACTUALIZAR_A_V10_4.md`: actualización desde V10.3.

## Advertencia

El programa es experimental. No garantiza aciertos ni ganancias. No persigas pérdidas y apuesta solo dinero que puedas perder.
