# Sistema de soporte técnico

Este proyecto implementa un flujo básico de soporte técnico para recibir incidencias, derivarlas al técnico responsable y hacer seguimiento hasta el cierre.

## Funcionalidades

- Ingreso manual de tickets (simula los correos recibidos en `atencion@miempresa.com`).
- Derivación automática al técnico encargado según el contenido.
- Seguimiento con eventos de línea de tiempo.
- Dashboard con tiempos promedio y estado de cada incidencia.

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Accede a:
- `http://localhost:5000/` para crear y ver tickets.
- `http://localhost:5000/dashboard` para el reporte.

## Ingreso de correos (API)

Simula la llegada de un correo con:

```bash
curl -X POST http://localhost:5000/intake/email \
  -H "Content-Type: application/json" \
  -d '{"from": "cliente@dominio.com", "subject": "Problema de red", "body": "No hay conexión"}'
```
