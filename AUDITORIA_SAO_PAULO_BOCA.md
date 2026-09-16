# Auditoría São Paulo vs Boca Juniors

## Error de V9.3

V9.3 eligió a Boca Juniors como favorito con `MODELO_SIN_CUOTA`, aunque las
cuotas reales aportadas fueron São Paulo 2.28, empate 3.00 y Boca 3.45. El
mercado favorecía a São Paulo. Por ello no es fiable conservar builders cuya
definición dependa de ese favorito aproximado.

## Corrección aplicada

- eliminado el rol favorito/underdog del nuevo producto;
- eliminados hándicaps asiáticos y combinadas automáticas;
- eliminada la cuota estimada;
- probabilidades separadas para 1X2, goles 1T, córners 1T, tarjetas y gol de
  cada equipo;
- cuota real solo como dato externo opcional para retirar margen, nunca como
  salida inventada;
- semáforo condicionado a validación cronológica y cobertura.

## Qué no puede concluirse de las capturas

Las imágenes no muestran una cotización completa del mismo Bet Builder de
V9.3, por lo que no se puede comparar `2.856895` con un precio real de esa
combinación. Sí permiten demostrar que la asignación de favorito era errónea y
que las cuotas teóricas no seguían la estructura de precios de la casa.
