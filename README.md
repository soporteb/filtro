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

Funciones adicionales:
- Administrador: gestiona técnicos (crear, editar, deshabilitar) desde la sección "Técnicos".
- Administrador: crea credenciales para derivadores y técnicos desde la sección "Credenciales".
- Técnico: agrega comentarios de atención, puede cerrar o devolver/reasignar incidencias.
- Se registra la última sesión (last login) de cada usuario.
- Las fechas se almacenan en horario de Lima (Perú).
- Exportación en CSV compatible con Excel para tickets cerrados.

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
- `http://localhost:5000/admin/technicians` (solo administrador)
- `http://localhost:5000/admin/credentials` (solo administrador)

Credenciales iniciales:
- Administrador: `admin@miempresa.com` / `admin123` (cambiar una vez instalado).

## Ingreso de correos (API)

Simula la llegada de un correo con:

```bash
curl -X POST http://localhost:5000/intake/email \
  -H "Content-Type: application/json" \
  -d '{"from": "cliente@dominio.com", "subject": "Problema de red", "body": "No hay conexión"}'
```
