# CRIS Management

<p>
  Sistema personal de administración para organizar tareas, finanzas y la vida diaria en un solo lugar.
</p>

---

## ¿Qué es CRIS?

**CRIS Management** es una aplicación web personal construida con Django. Reúne en un mismo
panel varias herramientas del día a día: pendientes, dinero, compras y hogar. Cada una funciona
como un **módulo** independiente.

El sistema está pensado para crecer. Cada módulo vive en su propia carpeta y se registra en un
solo lugar, así que se pueden agregar, quitar, encender o apagar sin tocar el resto de la aplicación.

## Características generales

- **Panel de inicio** con acceso rápido a todos los módulos activos.
- **Inicio de sesión** y cambio de contraseña; cada usuario ve solo su propia información.
- **Diseño responsivo** que funciona en computadora y celular.
- **Tema claro y oscuro**, que recuerda la preferencia de cada usuario.
- **Interfaz en español** (México), con fechas y moneda locales.
- **Módulos activables** mediante una variable de entorno.
- **Pruebas automatizadas** y revisión de estilo en cada cambio (GitHub Actions).
- **Listo para la nube**: se publica en Vercel con base de datos PostgreSQL.

## Módulos

| Módulo | Descripción | Estado |
|---|---|---|
| **Tareas** | Pendientes con prioridad, fecha límite, etiquetas y estatus. | Activo |
| **Finanzas** | Cuentas, movimientos, categorías, pagos recurrentes, importación de CSV y candado con contraseña. | Activo |
| **Compras** | Listas del súper por pasillo, catálogo de productos con historial de precios y presupuesto. | Desactivado |
| **Hogar** | Servicios y recibos, vehículos, mantenimientos, recordatorios, garantías e inventario. | Desactivado |

> Los módulos desactivados ya están construidos, pero no se muestran. Ver
> [Activar o desactivar módulos](#activar-o-desactivar-módulos).

## Tecnologías

- **Backend:** Python 3.12+ y Django 5.2
- **Base de datos:** SQLite en desarrollo y PostgreSQL (Neon) en producción
- **Frontend:** plantillas de Django, CSS propio y JavaScript sin frameworks
- **Calidad:** pytest, pytest-django y Ruff
- **Despliegue:** Vercel

## Estructura del proyecto

```
CRIS/
├── apps/                 # Un paquete por módulo
│   ├── accounts/         # Usuarios, inicio de sesión y contraseña
│   ├── core/             # Panel de inicio y registro de módulos
│   ├── tasks/            # Tareas
│   ├── finance/          # Finanzas
│   ├── shopping/         # Compras
│   └── household/        # Hogar
├── config/
│   ├── settings/         # base, dev, test y prod
│   ├── urls.py
│   └── wsgi.py
├── static/               # CSS, JavaScript e imágenes
├── templates/            # Plantillas compartidas y de cada módulo
├── tests/                # Pruebas automatizadas
├── build.py              # Script de despliegue (migraciones y administrador)
├── manage.py
├── requirements.txt      # Dependencias de la aplicación
└── requirements-dev.txt  # Dependencias de desarrollo y pruebas
```

## Instalación local

**Requisitos:** Python 3.12 o superior y Git.

```powershell
# 1. Clonar el repositorio
git clone https://github.com/TU_USUARIO/cris.git
cd cris

# 2. Crear y activar el entorno virtual
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. Instalar dependencias
pip install -r requirements-dev.txt

# 4. Configurar variables de entorno
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux

# 5. Crear la base de datos y un usuario
python manage.py migrate
python manage.py createsuperuser

# 6. Iniciar el servidor
python manage.py runserver
```

Después, abre <http://127.0.0.1:8000> e inicia sesión.

## Variables de entorno

Se definen en el archivo `.env` local o en el panel de Vercel. **El archivo `.env` nunca se sube a Git.**

| Variable | Descripción |
|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta de Django. Usa una distinta y larga en producción. |
| `DJANGO_ALLOWED_HOSTS` | Dominios permitidos, separados por coma. |
| `DATABASE_URL` | Opcional. Conexión a PostgreSQL. Si no se define, se usa SQLite. |
| `CRIS_DISABLED_MODULES` | Módulos apagados, separados por coma (p. ej. `shopping,household`). |
| `CRIS_ADMIN_USERNAME` / `CRIS_ADMIN_PASSWORD` | Opcionales. Crean el administrador inicial al desplegar. |

## Activar o desactivar módulos

Los módulos se controlan con `CRIS_DISABLED_MODULES`. Un módulo apagado desaparece del panel
y sus direcciones dejan de existir; los datos guardados no se borran.

```env
# Apagar Compras y Hogar
CRIS_DISABLED_MODULES=shopping,household

# Todos los módulos activos
CRIS_DISABLED_MODULES=
```

Reinicia el servidor (o vuelve a desplegar) después de cambiarla.

## Pruebas y calidad de código

```powershell
pytest                 # Ejecuta todas las pruebas
ruff check .           # Revisa errores y estilo
ruff format .          # Da formato al código
```

Las mismas revisiones corren automáticamente en GitHub Actions con cada `push` y *pull request*.

## Comandos útiles

| Comando | Para qué sirve |
|---|---|
| `python manage.py generar_recurrentes` | Genera los movimientos de los pagos recurrentes que ya vencieron. |
| `python manage.py crear_admin` | Crea el administrador con `CRIS_ADMIN_USERNAME` y `CRIS_ADMIN_PASSWORD`. |
| `python manage.py makemigrations` | Crea migraciones después de cambiar modelos. |

## Despliegue

CRIS se publica en **Vercel** con base de datos **PostgreSQL en Neon**. En cada despliegue se
instalan las dependencias, se aplican las migraciones y se publican los archivos estáticos de
forma automática.

La guía paso a paso está en [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md).

## Agregar un módulo nuevo

1. Crea la app dentro de `apps/` con sus modelos, vistas, URLs y plantillas.
2. Agrégala a `INSTALLED_APPS` en `config/settings/base.py`.
3. Registra sus URLs en `config/urls.py`.
4. Añádela a la lista `MODULES` de `apps/core/modules.py` (nombre, descripción, icono y color).
5. Escribe sus pruebas en `tests/` y ejecuta `pytest`.

## Autor

Desarrollado por **Cristopher** como sistema de uso personal.
