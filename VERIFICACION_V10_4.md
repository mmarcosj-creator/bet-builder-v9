# Verificación V10.4 Gatuno Adaptativo

## Resultado

La versión compila y las pruebas offline de seguridad pasaron. El sistema ya puede detectar deterioro por mercado, crear una propuesta, esperar confirmación, aplicar una compuerta temporal, sincronizar pronósticos aún no iniciados y revertir el cambio.

## Pruebas ejecutadas

Las 7 pruebas de `self_test_v10_4.py` cubren estas protecciones (una prueba comprueba dos condiciones):

1. una muestra de 12 casos no dispara ajuste;
2. 35 casos con deterioro fuerte generan propuesta;
3. observar siete días no crea una política;
4. aplicar solo degrada verde a amarillo;
5. una señal amarilla nunca se promociona;
6. la política puede revertirse;
7. solo se sincronizan registros futuros pendientes;
8. el historial anterior de V10.3 se migra sin perder el resultado liquidado.

`self_test_v10_3.py`:

1. compuerta fuera de muestra;
2. historial único por evento/mercado;
3. liquidación de los seis mercados;
4. protección por alineación y mejor opción;
5. ausencia de una tasa ficticia cuando no hay evaluados;
6. fallo aislado de un submodelo;
7. restauración de límites del modo rápido.

Además, `py_compile` valida la sintaxis de la aplicación, el motor, auditoría, monitor adaptativo, monitor OOS y actualizador programado.

## Correcciones frente al fragmento recibido

- El archivo recibido terminaba a mitad del panel de auditoría y no era ejecutable como entrega completa.
- Cambiar el texto a `V10.4-TRAZABLE` no implementaba adaptación.
- `model_monitor.py` solo diagnosticaba; ahora `adaptive_monitor.py` gestiona propuestas y decisiones.
- Se corrigió la interpretación de valores booleanos de `SuperaBase` guardados como texto.
- Se eliminó el descenso histórico silencioso: ahora requiere confirmación.
- Se evita contar dos veces el mismo evento/mercado si cambia el color antes del kickoff.
- Se agregó migración del historial V10.3 anterior.
- Se restauró la identidad Gatuno y sus emojis en la interfaz.

## Límites pendientes

- Las pruebas demuestran funcionamiento del flujo, no capacidad predictiva ni rentabilidad.
- La calidad real solo podrá medirse con resultados prospectivos acumulados.
- Una alerta de siete días es preventiva; la consistencia exige 300 verdes y 30 días.
- Sin cuotas reales prepartido no existe cálculo válido de ROI o pérdida monetaria.
- El cierre de córners/tarjetas depende de que la fuente entregue estadísticas verificables; si faltan, queda `NO_EVALUABLE`.
