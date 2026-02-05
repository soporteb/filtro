# Sistema de soporte técnico

Este proyecto implementa un flujo básico de soporte técnico para recibir incidencias, derivarlas al técnico responsable y hacer seguimiento hasta el cierre.

## Funcionalidades

- Ingreso manual de tickets (simula los correos recibidos en `atencion@miempresa.com`).
- Derivación manual por el encargado de asignaciones.
- Seguimiento con eventos de línea de tiempo.
- Dashboard con tiempos promedio y estado de cada incidencia.
- Módulos por perfil: administrador, derivador y técnico.

Roles y funciones:
- Administrador: visualiza todo el tablero y puede cerrar tickets.
- Derivador: asigna manualmente los tickets a cada técnico.
- Técnico: ve solo sus tickets asignados y puede cerrar los propios.

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Accede a:
- `http://localhost:5000/login` como puerta de entrada obligatoria.
- `http://localhost:5000/` para crear y ver tickets (requiere sesión activa).
- `http://localhost:5000/dashboard` para el reporte (requiere sesión activa).

Rutas de acceso por rol:
- `http://localhost:5000/login/admin`
- `http://localhost:5000/login/dispatcher`
- `http://localhost:5000/login/technician`

## Ingreso de correos (API)

Simula la llegada de un correo con:

```bash
curl -X POST http://localhost:5000/intake/email \
  -H "Content-Type: application/json" \
  -d '{"from": "cliente@dominio.com", "subject": "Problema de red", "body": "No hay conexión"}'
```
