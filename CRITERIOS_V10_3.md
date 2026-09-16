# Criterios de V10.3 Gatuno PRO

## 1. Regla principal

El objetivo no es producir muchas apuestas, sino abstenerse cuando no existe evidencia suficiente. Una probabilidad alta por sí sola no habilita una selección.

## 2. Datos prepartido

El motor utiliza únicamente información disponible antes del encuentro:

- Elo dinámico, forma con decaimiento temporal y localía;
- goles, goles de primer tiempo, córners y tarjetas a favor/en contra;
- posición y puntos por partido calculados secuencialmente;
- descanso, cantidad de partidos en 14 días y siguiente compromiso;
- liga, tipo de torneo, fase e importancia;
- riesgo de rotación y estado de alineación;
- origen doméstico aprendido de participaciones previas y cruce interliga.

La construcción secuencial impide usar el resultado futuro para generar sus propias variables.

## 3. Validación temporal

- Entrenamiento y validación se separan por fecha, nunca mediante una partición aleatoria principal.
- Las probabilidades se calibran con cortes anteriores.
- Cada modelo se compara contra una referencia simple de prevalencia/clase mayoritaria.
- Un modelo con mejora Brier `<= 0` o mala calibración queda `NO SUPERA BASE OOS` y todas sus señales son rojas.
- El resultado 1X2 exige además margen frente a la segunda opción.

## 4. Semáforo

### Mercado binario

- Verde inicial: probabilidad seleccionada >= 68%, límite conservador >= 59%, fiabilidad >= 66% y soporte >= 55.
- Amarillo inicial: probabilidad >= 58%, límite >= 50%, fiabilidad >= 50% y soporte >= 35.
- En otro caso: rojo.

### Resultado 1X2

- Verde inicial: probabilidad >= 49%, ventaja sobre segunda opción >= 11 puntos, límite >= 40%, fiabilidad >= 67% y soporte >= 70.
- Amarillo inicial: probabilidad >= 40%, ventaja >= 6 puntos, límite >= 32%, fiabilidad >= 50% y soporte >= 40.

### Compuertas posteriores

Aunque cumpla esos números, la señal se degrada o bloquea si:

- el modelo no supera la referencia fuera de muestra;
- falta cobertura estadística;
- la alineación no está confirmada;
- existe riesgo alto de rotación;
- el historial prospectivo reciente del mercado muestra deterioro con muestra suficiente;
- en un cruce argentino interliga, tarjetas/córners no superan la prueba específica del subgrupo.

## 5. Córners y fútbol argentino

Los córners son conteos agrupados y con dispersión, por lo que no deben tratarse como eventos independientes simples. V10.3:

- usa solamente conteos verificables del primer tiempo;
- exige cobertura mínima de competencia/grupo;
- valida el modelo en un tramo temporal posterior;
- identifica cruces argentinos con otras ligas de Libertadores/Sudamericana;
- exige 30+ cruces identificables;
- compara en fechas posteriores el ajuste del subgrupo contra la tasa general;
- si el ajuste no mejora Brier o queda mal calibrado, no lo aplica y bloquea el verde.

Esto permite que los datos confirmen tanto “menos” como “más” córners; no se codifica el prejuicio de que siempre habrá menos.

## 6. Tarjetas

Las tarjetas se modelan como **amarillas totales**. Se incluyen medias recientes propias/rivales, competición, localía y cruces interliga. En partidos argentinos contra otra liga, el verde requiere también validación temporal específica del subgrupo. Debe comprobarse que la casa liquide exactamente el mismo mercado.

## 7. Auditoría prospectiva

La clave de cada predicción incluye evento, mercado, línea, versión y estado del semáforo. La primera emisión de cada estado queda congelada. Así, una señal amarilla emitida días antes y la primera verde posterior a la alineación confirmada pueden auditarse sin sobrescribir la historia. El cierre almacena resultado real y fuente; no reescribe la predicción después del partido.

El ajuste histórico es unidireccional:

- nunca sube amarillo/rojo a verde;
- con menos de 60 verdes resueltos por mercado no modifica el modelo;
- con 60-99 puede bajar a amarillo si acierto <55% o Wilson inferior <45%;
- con 100+ puede bajar a rojo si acierto <48%.

## 8. Consistencia, no “homologación de ganancias”

El sistema solo declara `CONSISTENCIA_PREDICTIVA` cuando reúne:

- al menos 300 verdes resueltos;
- 30 días de observación;
- tasa verde >=65%;
- límite inferior Wilson 95% >=60%;
- cuatro mercados con al menos 30 verdes resueltos cada uno.

Esto no prueba rentabilidad. Para EV/ROI hacen falta cuotas reales históricas completas registradas antes del inicio, margen de la casa y reglas de liquidación.

## 9. Prácticas profesionales incorporadas

- datos amplios dentro y fuera del campo;
- modelos adaptables e iteración continua;
- calibración antes que exactitud bruta;
- especialización por mercado;
- validación temporal y comparación contra base;
- contexto humano verificable (once, rotación, calendario);
- abstención y auditoría transparente;
- ninguna copia de “picks” de apostadores famosos sin un registro público verificable.

Los nombres más citados públicamente —Tony Bloom/Starlizard, Matthew Benham/Smartodds, Haralabos Voulgaris y Billy Walters— no ofrecen un registro completo y auditable de cada apuesta que permita copiar selecciones. Se tomaron patrones de proceso, no supuestos “secretos”: Voulgaris describe acumular datos durante años, probar ideas y eliminar las que no predicen; Starlizard declara combinar datos, análisis, experiencia deportiva y modelos iterativos. Eso se traduce aquí en cortes temporales, compuertas OOS, alineaciones, auditoría y abstención.

## Fuentes metodológicas

- Starlizard, enfoque de datos, experiencia deportiva, modelos adaptables e iteración: https://starlizard.com/
- Walsh y Joshi, calibración frente a exactitud en apuestas: https://researchportal.bath.ac.uk/en/publications/machine-learning-for-sports-betting-should-forecasting-models-be-/
- Dixon y Coles, modelo dinámico de marcadores: https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/1467-9876.00065
- Yip et al., córners mediante distribución Poisson compuesta: https://research.polyu.edu.hk/en/publications/forecasting-number-of-corner-kicks-taken-in-association-football-/
- Izquierdo y Redondo, diferencias de estilos ofensivos Europa/Sudamérica: https://www.scielo.sa.cr/scielo.php?pid=S1659-097X2022000200025&script=sci_arttext
- Entrevista a Haralabos Voulgaris sobre probar, evaluar y descartar ideas no predictivas: https://www.theguardian.com/football/2024/feb/18/castellon-owner-bob-voulgaris-analytics-gambling-interview
- Perfil de Billy Walters y uso intensivo de análisis técnico/computacional: https://www.espn.com/espn/feature/story/_/id/12280555/how-billy-walters-became-sports-most-successful-controversial-bettor
