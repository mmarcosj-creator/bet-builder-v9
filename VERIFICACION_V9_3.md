# Verificación técnica V9.3

Fecha: 2026-09-15

## Pruebas ejecutadas

- Compilación de los seis módulos Python: correcta.
- `self_test_v9_3.py`: correcto.
- 49 mercados definidos y 7 plantillas operativas de tres selecciones.
- Clasificación de fases: liga, fase liga/grupos, octavos, cuartos, semifinal y final.
- Detección sintética de congestión y siguiente partido prioritario.
- Bloqueo de mercado sensible bajo riesgo alto de rotación.
- Comparación sintética de once habitual frente a rotación alta.
- Firma exacta del builder y rechazo de firma distinta.
- Reglas de cuota: confirmar combinación, descartar bajo 4.20 y validar solo
  cuando se cumplen contexto, cupo y cuota requerida.

## Restricción del entorno de prueba

La interfaz Streamlit no se inició en este entorno porque el ejecutable no está
instalado aquí. El archivo `app.py` sí fue compilado correctamente. En el equipo
de destino se instala con `pip install -r requirements.txt` antes de ejecutar
`streamlit run app.py`.

## Alcance estadístico

Estas pruebas verifican lógica e integración; no demuestran rentabilidad. La
capa de alineaciones se valida prospectivamente porque no es correcto reconstruir
retroactivamente información que el sistema no almacenó antes de cada partido.
