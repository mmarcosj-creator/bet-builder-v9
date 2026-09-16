# Verificación de V10.3 Gatuno PRO

## Dictamen

**V10.2 no estaba validado ni era fiable para apostar dinero.** V10.3 corrige fallos estructurales, pero todavía debe reunir una muestra prospectiva nueva antes de poder llamarse estable. No se promete rentabilidad.

## Evidencia encontrada en `V10_GATUNO_AUDITORIA.xlsx`

- 101 partidos y 606 pronósticos (seis por encuentro).
- 378 señales verdes, 32 amarillas y 196 rojas.
- Las 606 seguían `PENDIENTE`; por tanto, el 0% mostrado no era una tasa de fallo sino ausencia de resultados evaluados.
- Las 378 verdes tenían fiabilidad inferior a 50%.
- 277 verdes decían explícitamente `NO SUPERA BASE OOS`.
- 50 verdes tenían soporte inferior a 35.
- Goles 1T y tarjetas no superaban su referencia temporal, pero la interfaz los podía volver verdes por superar 60% de probabilidad seleccionada.

La causa fue confirmada en el código: la capa visual reemplazaba el semáforo robusto por reglas fijas de 60/50%, ignorando validación, fiabilidad, soporte y límite conservador.

## Referencia histórica de 100 partidos (V10.1)

La muestra reproducible incluida en `validacion_referencia` tuvo:

| Mercado | Acierto | Base mayoritaria | Lectura |
|---|---:|---:|---|
| Resultado 1X2 | 43% | 35% | Mejora descriptiva |
| Goles 1T U/O 1.5 | 63% | 63% | No añade exactitud |
| Tarjetas U/O 4.5 | 54% | 54% | No añade exactitud |
| Gol local 0.5 | 77% | 79% | Inferior a la base por exactitud |
| Gol visitante 0.5 | 70% | 72% | Inferior a la base por exactitud |

Esto no mide beneficio porque no existen cuotas históricas reales completas. También muestra por qué una tasa bruta puede engañar: 77% puede ser peor que una regla base de 79%. La calibración/Brier y la comparación fuera de muestra son obligatorias.

## Aprendizaje de los fallos proporcionados

- **Alavés–Valencia:** fallaron ganador Alavés y córners altos; acertaron under de goles y tarjetas. Señala que una pata 1X2 o de córners débil no debe contaminar mercados más estables.
- **Rayo–Espanyol:** fallaron empate/doble oportunidad, under 2.5 y córners altos de Rayo. Repite el problema de combinar mercados dependientes y líneas agresivas.
- **Elche–Real Madrid:** acertaron BTTS y protección del underdog, pero falló la línea alta de córners del Madrid. Refuerza el bloqueo por rotación/alineación y la modelización separada de córners.
- Otros ejemplos mostraron builders con tres patas acertadas y una o dos de resultado/córners falladas. V10.3 no genera combinadas.

Los partidos del archivo del día estaban aún pendientes al momento de la auditoría. No se etiquetaron retrospectivamente a mano para evitar sesgo de selección; el nuevo cierre automático empezará con emisiones congeladas V10.3.

## Protecciones verificadas offline

`self_test_v10_3.py` comprueba:

1. modelo que no supera base => rojo;
2. historial prepartido inmutable;
3. liquidación de los seis mercados;
4. máximo una mejor opción verde;
5. alineación no confirmada => no verde;
6. ausencia de resultados => `SIN DATOS`, no 0% ficticio.

Resultado de esta entrega: **5/5 pruebas críticas superadas**.

## Qué falta para declarar estabilidad

- 300 verdes resueltos y al menos 30 días;
- límite inferior Wilson de 95% >=60%;
- cobertura en cuatro mercados;
- revisión de calidad de la fuente de córners/tarjetas;
- si se quiere medir rentabilidad, capturar cuotas reales prepartido y reglas de liquidación.

Hasta entonces, el estado correcto es **RECOLECTANDO**, no “sistema fiable” ni “sistema rentable”.
