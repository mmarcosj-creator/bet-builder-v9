# Criterios V9.3 — contexto, rotación y control del cupón

## Principio

La importancia de un torneo y la fuerza del once son variables distintas. Un
partido continental puede elevar la motivación, pero también un partido de liga
previo a una semifinal puede presentar rotaciones. V9.3 no usa etiquetas como
"Champions" para aumentar automáticamente la probabilidad.

## Base investigada

- La revisión sistemática de Julian, Page y Harper define congestión como
  partidos sucesivos con menos de 96 horas de recuperación y encuentra efectos
  no uniformes: la distancia total puede no cambiar, mientras otras variables
  físicas/tácticas sí pueden deteriorarse. Por eso V9.3 usa congestión como
  incertidumbre y no como una corrección determinista del marcador:
  https://pubmed.ncbi.nlm.nih.gov/33068272/
- El estudio sobre rotación en el Mundial 2018 confirma que selección del once,
  participación y ronda competitiva deben tratarse conjuntamente:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC8484307/
- UEFA publica onces específicos por encuentro y fase; esa confirmación es más
  fiable que inferir titulares por el nombre del torneo:
  https://www.uefa.com/uefachampionsleague/news/02a5-208b14a03cf8-b4d8a8bcc76b-1000--champions-league-semi-final-second-legs-starting-line-ups/
- Los manuales oficiales 2026 permiten distinguir el contexto reglamentario y
  las fases de Libertadores y Sudamericana, pero no sustituyen la alineación
  confirmada del partido:
  https://www.conmebol.com/documentos/manual-de-clubes-conmebol-libertadores-2026/
  y https://www.conmebol.com/documentos/manual-de-clubes-conmebol-sudamericana-2026/

## Variables nuevas

| Variable | Cálculo | Efecto |
|---|---|---|
| Fase competitiva | final, semifinal, cuartos, octavos, grupos, clasificación o desconocida | Puntaje de importancia 0–100 |
| Descanso | días desde el partido anterior | Alerta a 3 días o menos |
| Congestión | partidos en 7 y 14 días | Aumenta riesgo de cambios en el once |
| Próximo partido | días e importancia relativa | Penaliza si llega en 4 días o menos y es claramente más importante |
| Alineación | titulares publicados por ESPN | Debe estar `CONFIRMADA` |
| Fuerza del XI | continuidad y presencia de habituales respecto de 3–5 onces previos | Distingue once habitual de rotación |
| Sensibilidad | tipo de mercado | Bloquea líneas dependientes del once bajo riesgo de rotación |

## Escala de fase

| Fase | Importancia base |
|---|---:|
| Final | 100 |
| Semifinal | 94 |
| Cuartos | 90 |
| Octavos | 86 |
| Eliminatoria/playoff | 84 |
| Grupos/fase liga continental | 76–80 |
| Clasificación | 72 |
| Liga regular | 65 |
| Copa sin fase identificada | 62 |

La vuelta de una eliminatoria suma como máximo dos puntos. Una fase desconocida
reduce confianza. Estos puntajes ordenan contexto; no son probabilidades.

## Mercados sensibles a rotación

- Victoria o -1.5 del favorito.
- Dos o más goles del favorito.
- 5+, 6+ u 8+ córners del favorito.
- Gol, resultado o rango de goles del primer tiempo.
- Córners del primer tiempo.

Con riesgo alto se bloquea cualquier builder que incluya uno de estos mercados.
Con riesgo medio se bloquean dos o más mercados sensibles juntos.

## Guardas incorporadas

- Máximo tres selecciones reales.
- Suspendidos: `BTTS_CONTROL`, `RANGO_CORNER_CONTROL`, `EMPATE_CERRADO`,
  `EMPATE_CORNER_BAJO` y los tres nichos con 6+/8+ córners del favorito
  (`DOMINIO_SIN_GOLEADA`, `CORNER_ALTO_GOL_BAJO`, `FAV_CORNER_BTTS`).
- Córners del primer tiempo y rangos que equivalen a dos apuestas permanecen
  en laboratorio.
- Firma SHA-256 abreviada de los códigos exactos del builder.
- Mínimo tres alineaciones previas por equipo para afirmar que el XI es habitual.
- Alerta si la cuota real supera 1.75 veces la cuota justa calculada.
- Máximo dos apuestas por día y una por competición/día.
- Cuota real mínima 4.20 y umbral `CuotaRequerida` conservador.

## Lo que no cambia

- Probabilidad conjunta empírica; no se multiplican probabilidades marginales.
- Wilson, soporte efectivo, dependencia Phi/lift y estabilidad temporal.
- Entrenamiento solo con partidos anteriores a la fecha pronosticada.
- Backtest walk-forward sin usar el resultado futuro para seleccionar.

## Validación necesaria

Los datos de alineación y del próximo partido deben almacenarse en el momento
del pronóstico para poder auditarlos después. Hasta reunir una muestra
prospectiva suficiente, V9.3 debe considerarse experimental. La tasa de acierto
sola no basta: se deben reportar ROI con cuota real, calibración, drawdown,
intervalo de confianza y resultados por plantilla/competición/fase.
