# Fuente del histórico de respaldo

El archivo `historical_fallback.csv.gz` se deriva del repositorio público
[`schochastics/football-data`](https://github.com/schochastics/football-data),
utilizado bajo la **Open Data Commons Attribution License (ODC-By 1.0)**.

Se incluye únicamente como respaldo compacto para que la interfaz pueda
arrancar cuando Football-Data.co.uk o ESPN estén temporalmente lentos. Los
datos remotos más recientes conservan prioridad cuando están disponibles.

El respaldo contiene resultados desde julio de 2021. Para Premier League,
LaLiga y Liga Portugal también conserva goles del primer tiempo y tarjetas
amarillas derivadas de los incidentes publicados. No fabrica córners del
primer tiempo: ese mercado queda sin pronóstico/rojo cuando no existe
cobertura reciente verificable.
