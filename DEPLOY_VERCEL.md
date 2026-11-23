# Publicar CRIS en Vercel

CRIS se publica en Vercel con su soporte nativo para Django (lo detecta por `manage.py`,
no necesita `vercel.json`). La base de datos es Postgres en **Neon**, conectada desde
el propio panel de Vercel. SQLite no sirve en Vercel porque su disco no guarda cambios.

Qué hace el proyecto en cada despliegue:

1. Vercel instala `requirements.txt` con Python 3.12 (`.python-version`).
2. Corre `build.py` (definido en `pyproject.toml`): aplica migraciones y crea el
   administrador si defines `CRIS_ADMIN_USERNAME` y `CRIS_ADMIN_PASSWORD`.
3. Corre `collectstatic` por su cuenta y sirve `/static/` desde su CDN.
4. Usa `config.settings.prod` (HTTPS obligatorio, cookies seguras, `DEBUG=False`).
   Los dominios `*.vercel.app` del despliegue se agregan solos a `ALLOWED_HOSTS` y
   `CSRF_TRUSTED_ORIGINS`.

---

## Paso 0. Aplicar los cambios en tu PC

```powershell
cd C:\ruta\a\CRIS
# descomprime CRIS-paso13-vercel.zip aquí, reemplazando archivos
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
python manage.py runserver   # todo debe verse igual que antes
```

## Paso 1. Subir el código a GitHub

1. En <https://github.com/new> crea un repositorio **privado** llamado `cris`
   (sin README ni .gitignore).
2. En la carpeta de CRIS:

```powershell
git add .
git commit -m "Preparar CRIS para Vercel"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/cris.git
git push -u origin main
```

`.gitignore` ya deja fuera `.venv`, `.env` y `db.sqlite3`. Revisa con `git status`
antes del commit que no aparezcan.

## Paso 2. Crear el proyecto en Vercel

1. Entra a <https://vercel.com> con tu cuenta de GitHub (plan Hobby, gratis).
2. **Add New… → Project** e importa el repositorio `cris`.
3. Framework Preset debe decir **Django** (si no, elígelo). Root Directory: `./`.
4. Abre **Environment Variables** y agrega:

| Variable | Valor |
|---|---|
| `DJANGO_SECRET_KEY` | una clave nueva (ver abajo). No reutilices la de tu `.env`. |
| `CRIS_ADMIN_USERNAME` | tu usuario para entrar a CRIS |
| `CRIS_ADMIN_PASSWORD` | tu contraseña (mínimo 10 caracteres) |
| `CRIS_ADMIN_EMAIL` | opcional |

Para generar la clave:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

5. Pulsa **Deploy**. Este primer build **va a fallar** con el mensaje
   `Falta DATABASE_URL`, porque aún no hay base de datos. Es lo esperado.

## Paso 3. Crear y conectar la base de datos (Neon)

1. En el proyecto: pestaña **Storage → Create Database → Neon** (Serverless Postgres).
2. Región: **Washington, D.C. (us-east-1)**, la misma zona donde corre Vercel por defecto.
3. Plan gratuito. Al crearla, **Connect** al proyecto `cris` con los entornos
   Production y Preview marcados. Vercel agrega `DATABASE_URL` sola.

## Paso 4. Volver a desplegar

**Deployments →** el último **→ ⋯ → Redeploy**. En el log del build debes ver las
migraciones (`Applying ... OK`) y `Administrador ... creado.`

Abre el dominio que te da Vercel (por ejemplo `https://cris-xxxx.vercel.app`) y entra
con el usuario del Paso 2. Después de entrar, **cambia la contraseña** desde el menú de
usuario y puedes borrar `CRIS_ADMIN_PASSWORD` de Vercel (el usuario ya existe y no se
vuelve a tocar).

Desde ahora, cada `git push` a `main` publica una versión nueva automáticamente.

---

## Opcional: pasar tus datos actuales (SQLite) a Neon

Si ya capturaste tareas, movimientos, etc. en tu PC y quieres conservarlos:

1. **No** definas `CRIS_ADMIN_USERNAME`/`CRIS_ADMIN_PASSWORD` en Vercel (tu usuario
   vendrá en los datos), o usa un nombre distinto.
2. Exporta desde tu PC (con el `.env` normal, sin `DATABASE_URL`):

```powershell
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e admin.logentry -e sessions --indent 2 -o datos.json
```

3. En Vercel: **Storage → tu base Neon → .env.local → Show secret** y copia el valor de
   `DATABASE_URL`. Agrégalo temporalmente a tu `.env` y carga los datos:

```powershell
python manage.py migrate
python manage.py loaddata datos.json
```

4. **Quita `DATABASE_URL` de tu `.env`** al terminar, para que tu PC vuelva a usar SQLite.
   Borra `datos.json`: contiene tus finanzas.

## Dominio propio (opcional)

**Settings → Domains** → agrega tu dominio y sigue los registros DNS que indica Vercel.
Luego agrega la variable `DJANGO_ALLOWED_HOSTS=tudominio.com` y vuelve a desplegar.

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| Build: `Falta DATABASE_URL` | La base Neon no está conectada al entorno (Paso 3). |
| Build: `KeyError: 'DJANGO_SECRET_KEY'` | Falta la variable en Vercel (Paso 2). |
| `Bad Request (400)` | El dominio no está en `ALLOWED_HOSTS`: agrégalo en `DJANGO_ALLOWED_HOSTS`. |
| `403 CSRF verification failed` | Dominio propio sin agregar: usa `DJANGO_ALLOWED_HOSTS` (o `DJANGO_CSRF_TRUSTED_ORIGINS=https://tudominio.com`). |
| Página sin estilos | Revisa en el log del build que `collectstatic` haya corrido. |
| Error 500 | **Deployments → Logs** del proyecto muestra el error de Django. |

Notas: los Previews de Vercel usan la misma base que Producción salvo que Neon cree
ramas por preview. El archivo de importación de Neko no puede pasar de 4.5 MB por
el límite de peticiones de Vercel.
