# Verificación V10.1

## Diagnóstico del archivo V9.3

En `São Paulo vs Boca Juniors`, V9.3 registró:

- `FuenteFavorito = MODELO_SIN_CUOTA`;
- favorito: Boca Juniors;
- cuota del favorito: vacía;
- `CuotaJustaModelo = 2.856895` para una combinada de tres patas.

Las capturas reales mostraron 1X2 de São Paulo 2.28, empate 3.00 y Boca 3.45.
Al retirar proporcionalmente el margen, el mercado representaba
aproximadamente 41.31 %, 31.39 % y 27.30 %. Por tanto, la dirección de favorito
de V9.3 era contraria al mercado y contaminaba las patas que dependían de
`favorito/underdog`.

La cifra `1 / P_Conjunta` de V9.3 era una cuota teórica sin margen; no era una
estimación verificada de Betsafe. V10.1 la elimina.

## Lectura de las cuotas reales aportadas

| Mercado | Cuotas | Probabilidad sin margen aproximada |
|---|---:|---:|
| 1X2 São Paulo / empate / Boca | 2.28 / 3.00 / 3.45 | 41.31 % / 31.39 % / 27.30 % |
| Goles FT más/menos 2.5 | 2.62 / 1.43 | 35.31 % / 64.69 % |
| Goles 1T más/menos 1.5 | 3.70 / 1.24 | 25.10 % / 74.90 % |
| São Paulo marca/no marca | 1.36 / 2.95 | 68.45 % / 31.55 % |
| Boca marca/no marca | 1.60 / 2.25 | 58.44 % / 41.56 % |

Estas probabilidades describen el mercado en ese momento; no demuestran que
una selección tenga valor ni sustituyen un modelo fuera de muestra.

## Validación local reproducible

Prueba realizada con 2,969 partidos de Premier League, LaLiga, Liga Portugal y
Süper Lig entre 09/08/2024 y 14/09/2026. Se generaron 2,733 filas con variables
prepartido. El tramo final reservado tuvo 278 encuentros.

| Modelo | Brier modelo | Brier base | Mejora | Estado |
|---|---:|---:|---:|---|
| Resultado 1X2 | 0.6271 | 0.6519 | +3.80 % | Supera base OOS |
| Goles 1T U/O 1.5 | 0.2328 | 0.2303 | -1.06 % | No supera base |
| Tarjetas U/O 4.5 | 0.2365 | 0.2341 | -1.01 % | No supera base |
| Local marca | 0.1547 | 0.1651 | +6.30 % | Supera base OOS |
| Visitante marca | 0.2071 | 0.2109 | +1.77 % | Supera base OOS |

La conclusión correcta no es que V10.1 “ya gana”: hay señal modesta en 1X2 y
goles por equipo, mientras que goles 1T y tarjetas todavía no muestran ventaja
frente a la referencia en esta muestra. V10.1 impide que los dos últimos
mercados pasen a verde/amarillo hasta que una actualización sí supere la base.

## Muestra aleatoria temporal de 100 partidos

El corte fue 03/05/2026 y el sorteo utilizó semilla `20260916`.

| Mercado | Aciertos | Tasa | Referencia mayoritaria |
|---|---:|---:|---:|
| Resultado 1X2 | 43/100 | 43 % | 35 % |
| Goles 1T U/O 1.5 | 63/100 | 63 % | 63 % |
| Tarjetas U/O 4.5 | 54/100 | 54 % | 54 % |
| Gol local 0.5 | 77/100 | 77 % | 79 % |
| Gol visitante 0.5 | 70/100 | 70 % | 72 % |

No se calcula una ganancia apostando 100 por selección porque no se archivaron
las cuotas reales históricas completas de esos cinco mercados. Usar 4.20, una
“cuota justa” o cualquier precio supuesto produciría un beneficio ficticio.

## Alcance del nicho argentino

La literatura encontrada respalda diferencias de estilo entre ligas
sudamericanas y europeas, pero no demuestra una regla universal de menos
córners para clubes argentinos ante rivales extranjeros. V10.1 lo implementa
como hipótesis comprobable:

1. identifica el país por participación doméstica previa;
2. separa Libertadores/Sudamericana y localía;
3. exige 30 cruces antes de ajustar córners 1T;
4. encoge el efecto hacia la media de la competencia;
5. lo bloquea si no mejora el Brier en validación temporal.

La eficacia específica de este nicho solo podrá informarse después de que el
histórico ESPN reúna suficiente cobertura homogénea de córners 1T y tarjetas.
