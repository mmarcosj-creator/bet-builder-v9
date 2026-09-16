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
