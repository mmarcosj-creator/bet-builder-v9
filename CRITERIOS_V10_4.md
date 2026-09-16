# Criterios de V10.4 Gatuno Adaptativo

## 1. Principio central

El sistema prioriza la abstención y la trazabilidad. Una probabilidad alta no basta: el modelo debe superar una referencia fuera de muestra y cumplir soporte, fiabilidad, límite conservador, alineación y contexto.

## 2. Datos y ausencia de fuga temporal

Las variables se construyen únicamente con información anterior al partido: Elo, forma temporal, localía, goles, goles 1T, córners, tarjetas, posición, descanso, carga, siguiente compromiso, torneo, fase, rotación, alineación y cruces interliga. Los partidos de una fecha se actualizan en bloque para no usar resultados futuros.

## 3. Validación del motor

- Separación cronológica entre entrenamiento, calibración y validación.
- Comparación con una base simple de prevalencia/clase mayoritaria.
- Probabilidades calibradas y medición con Brier/ECE.
- Conteos evaluados con MAE.
- Un modelo que no mejora su referencia no puede publicar verde.

## 4. Semáforo base

### Mercados binarios

- Verde: probabilidad >=68%, límite conservador >=59%, fiabilidad >=66% y soporte >=55.
- Amarillo: probabilidad >=58%, límite >=50%, fiabilidad >=50% y soporte >=35.
- En otro caso: rojo.

### Resultado 1X2

- Verde: probabilidad >=49%, margen frente a la segunda opción >=11 puntos, límite >=40%, fiabilidad >=67% y soporte >=70.
- Amarillo: probabilidad >=40%, margen >=6 puntos, límite >=32%, fiabilidad >=50% y soporte >=40.

La capa adaptativa no reemplaza estas reglas: solo puede endurecerlas.

## 5. Cierre de jornada

Cada evento/mercado se registra antes del kickoff. El cierre automático busca el resultado terminado y evalúa por separado:

- `RESULT_1X2`;
- `H1_GOALS_OU15`;
- `H1_CORNERS_OU45`;
- `YELLOW_CARDS_OU45`;
- `HOME_SCORE_OU05`;
- `AWAY_SCORE_OU05`.

Un dato ausente queda `NO_EVALUABLE`; no se convierte en fallo. Los registros iniciados no se reescriben.

## 6. Alerta semanal por mercado

Una ventana de siete días solo se considera accionable con al menos 20 verdes resueltos y 4 días activos. Se revisan cuatro señales:

1. brecha de acierto frente a la probabilidad media <= -12 puntos y desviación estandarizada <= -1.64;
2. al menos 3 días débiles con dos o más casos por día;
3. Brier >=0.25 y deterioro >=0.04 frente al periodo previo cuando existe comparación;
4. caída de acierto >=12 puntos frente a los 28 días anteriores, con al menos 30 casos previos.

Estados:

- `SIN_MUESTRA`: seguir recolectando;
- `ESTABLE`: sin deterioro consistente;
- `OBSERVAR`: señal temprana, sin ajuste;
- `ALERTA`: coinciden dos o más señales; propone endurecer verde;
- `CRITICA`: deterioro extremo con 30+ casos; propone pausar verdes 7 días.

## 7. Decisión humana y ajuste automático controlado

El sistema nunca aplica una propuesta en silencio:

- `APLICAR`: crea una política temporal y auditable;
- `OBSERVAR_7_DIAS`: no cambia criterios y bloquea una nueva pregunta hasta la revisión;
- `REVERTIR`: elimina la política activa y conserva el registro de la decisión.

Un endurecimiento eleva como máximo cinco puntos la probabilidad mínima, tres puntos el límite conservador y la fiabilidad, y diez unidades el soporte. Dura 14 días. Una pausa dura 7 días. Ambos cambios solo degradan verde a amarillo.

## 8. Separación entre aprendizaje y control

El entrenamiento aprende de marcadores y conteos reales completos. El controlador semanal usa acierto/fallo para vigilar calibración y filtrar señales. No cambia coeficientes del modelo a partir de una sola semana, porque eso favorecería sobreajuste y retroalimentación.

## 9. Fútbol argentino e interligas

No existe una penalización fija por nacionalidad. Córners y tarjetas se modelan con competición, localía, forma, origen y cruces interliga. El subgrupo argentino solo interviene con muestra identificable y mejora temporal fuera de muestra; si no mejora, no habilita verde.

## 10. Consistencia y rentabilidad

Una alerta semanal no “homologa” el sistema. La consistencia predictiva requiere al menos 300 verdes resueltos, 30 días, cuatro mercados con 30+ casos, acierto verde >=65% y Wilson inferior 95% >=60%.

La rentabilidad no puede calcularse con tasa de acierto sola. Requiere cuotas reales prepartido, margen de la casa, reglas de liquidación y ROI prospectivo. V10.4 no inventa cuotas.
