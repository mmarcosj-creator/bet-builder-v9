# Criterios técnicos V10.1

## 1. Separación entre probabilidad y precio

`1 / probabilidad` es una cuota teórica sin margen, no una predicción de la
cuota que ofrecerá Betsafe. V10.1 no publica cuotas. La función
`remove_margin()` solo sirve para auditar un mercado real completo introducido
por el usuario.

## 2. Construcción sin fuga temporal

Cada fila se genera antes de actualizar el estado con su resultado. Los
partidos de una misma fecha se actualizan en bloque. Las posiciones, forma,
Elo, descanso y promedios de competencia contienen únicamente observaciones
anteriores.

## 3. Modelos y calibración

- Clasificación logística regularizada para 1X2 y mercados binarios.
- Regresión de Poisson regularizada para conteos esperados.
- Ponderación temporal para reducir la influencia de temporadas antiguas.
- Calibración sigmoide binaria y calibración por temperatura para 1X2,
  ajustadas con predicciones fuera de muestra.
- Evaluación final sobre el tramo cronológico más reciente reservado.

## 4. Regla de abstención

La aplicación no obliga a escoger. Un mercado queda rojo si no supera la
referencia fuera de muestra, la calibración es deficiente, la muestra es
pequeña, falta alineación/contexto o no existen datos homogéneos.

## 5. Nicho argentino interliga

El origen del club se aprende de su participación previa en una liga doméstica.
En Libertadores/Sudamericana se crean interacciones para:

- club argentino local;
- club argentino visitante;
- rival de otro país;
- resultado, goles y tarjetas;
- córners del primer tiempo.

Para córners 1T, la tasa del subgrupo se encoge hacia la tasa de la competencia
y su peso nunca supera 45 %. Solo se activa con 30 o más cruces identificados.
Si la hipótesis no mejora el Brier en el tramo temporal reservado, no puede
producir un semáforo verde.

Esto evita convertir una observación táctica razonable en una regla universal.

## 6. Umbrales de color

Los mercados binarios requieren, para verde, probabilidad seleccionada ≥ 68 %,
límite conservador ≥ 59 %, fiabilidad ≥ 66 % y soporte ≥ 55. El 1X2 usa
umbrales específicos y exige una separación clara sobre la segunda opción.

Los umbrales no se optimizan contra un solo día de resultados.

## 7. Auditoría real (V10.3)

Cada pronóstico se guarda en `historial_apuestas.csv` **antes** del inicio del
partido (`auditoria_v10.registrar_pronosticos`). Al llegar el `KickoffUTC`, la
fila queda congelada: un recálculo posterior no puede modificar un pronóstico
ya jugado.

La resolución es automática (`auditoria_v10.resolver_pendientes`): se cruza
cada fila pendiente, por nombre de equipo y fecha, contra el histórico y el
contexto de córners 1T que el propio motor ya descarga. Si el partido no
aparece en ninguna fuente pasados 5 días desde el kickoff, la fila se marca
`SIN_DATO`; nunca se inventa un resultado ni se deja pendiente indefinidamente.

Las métricas (`auditoria_v10.calcular_metricas`) se reportan por mercado y por
color, con intervalo de Wilson y Brier score, y nunca muestran "0.0%" cuando
no hay evaluados (se muestra `SIN DATOS`). Por debajo de 30 casos evaluados la
tasa se marca explícitamente como no concluyente.

**No existe ninguna "alarma de sistema validado y estable".** Una ventana de
7 días con ~20 selecciones no tiene potencia estadística suficiente para
distinguir habilidad real de varianza normal en fútbol; declarar el sistema
"graduado" sobre esa base violaría directamente la sección 6 de este
documento. La auditoría mide desempeño pasado; no certifica desempeño futuro.

## 8. Monitor de calidad del modelo (`model_monitor.py`)

El aprendizaje real ya ocurre en cada corrida: `train_models()` reajusta cada
submodelo con el histórico completo, que crece con los resultados reales
(goles, tarjetas, córners) de los partidos ya jugados. Ese es el mecanismo de
aprendizaje — no un reentrenamiento sobre el bit binario "acertó/falló" de
una apuesta, que descartaría el marcador real y arriesgaría retroalimentación
sobre los propios errores de calibración del sistema.

Lo que aporta este módulo, sin reescribir umbrales ni reentrenar por fuera de
`train_models()`:

- **Registro histórico de métricas** (`model_metrics_log.csv`): Brier/MAE,
  ECE y `SuperaBase` de cada submodelo, corrida a corrida.
- **Detección de degradación**: compara la corrida más reciente contra la
  mediana de las últimas 10 corridas del mismo submodelo. Si empeora más de
  15% o un modelo que antes superaba la base deja de hacerlo, se muestra un
  aviso visible en la app. Nunca oculta la degradación ni la corrige sola.
- **Contraste calibración prometida vs. real**: cruza la probabilidad mínima
  que cada color promete (68% verde, 59% amarillo) contra la tasa de acierto
  real medida por `auditoria_v10.calcular_metricas()`. Es puramente
  informativo — la decisión de qué hacer con una brecha la toma una persona,
  no el código.

## 9. Puntos medios: error real de goles y tarjetas esperados

Además del semáforo (que exige cruzar un umbral, p. ej. "MAS DE 4.5"), el
motor también produce cuatro números continuos por partido: goles esperados
local, goles esperados visitante, goles esperados 1T y tarjetas esperadas.
Reducir esto a un acierto/fallo binario tiraría información: un promedio de
4.8 tarjetas frente a un resultado real de 5 es un error pequeño, y frente a
uno de 10 es un error grande, aunque ambos casos "fallen" el umbral de 4.5.

`auditoria_v10.registrar_puntos_medios()` guarda estos cuatro valores por
partido antes del kickoff y los congela igual que el historial de mercados.
`auditoria_v10.resolver_puntos_medios()` los compara después contra el
marcador y las tarjetas reales del histórico ya descargado, calculando el
error absoluto de cada uno. `auditoria_v10.calcular_metricas_puntos_medios()`
agrega el MAE (error absoluto medio) por métrica, con el mismo criterio de
honestidad del resto del sistema: "SIN DATOS" si N=0, nunca un MAE fabricado.
