# Nyanko

Aplicación de escritorio para consultar AniList y detectar anime reproducido localmente.

## Arquitectura nueva

- `apps/desktop`: Tauri 2 + React + TypeScript.
- `apps/backend`: API local FastAPI, SQLite, cliente AniList y detectores.
- `legacy/`: aplicación Django histórica, conservada temporalmente como referencia.

El frontend se comunica exclusivamente con `http://127.0.0.1:8765`. El backend no
escucha interfaces de red externas.

## Desarrollo

Requisitos: Node 20+, Rust estable y Python 3.11+.

```powershell
python -m venv apps/backend/.venv
apps/backend/.venv/Scripts/Activate.ps1
python -m pip install -e "apps/backend[dev]"
Copy-Item apps/backend/.env.example apps/backend/.env
Copy-Item apps/desktop/.env.example apps/desktop/.env
npm install
npm run dev
```

En Windows, `build.rs` genera el recurso `.ico` dentro de `OUT_DIR`; no es necesario
copiar iconos binarios al repositorio para ejecutar `tauri dev`.

Registra en AniList la URI de retorno
`http://127.0.0.1:8765/api/auth/callback` y completa `apps/backend/.env`. Nunca
incluyas el secreto OAuth en Git ni en el bundle de Tauri.

## Comprobaciones

```powershell
python -m pytest apps/backend/tests
npm run check
npm run build:sidecar
npm run build
```

## Estado del MVP

- Interfaz de biblioteca y filtros.
- OAuth y consultas de lista de AniList mediante el servicio local.
- Actualización de progreso.
- Detección de la ventana activa en Windows y extracción básica del episodio.
- WebSocket local para eventos de reproducción.

El backend incluye un modelo local canónico, registro de proveedores y un adaptador
de AniList. Las rutas neutrales (`/api/providers`, `/api/library` y `/api/media`) son
las consumidas por el frontend; las rutas antiguas de AniList se conservan
temporalmente como compatibilidad.

Las credenciales, cachés y sincronizaciones se aíslan por proveedor y cuenta. La base
normalizada conserva títulos alternativos, temporadas, episodios y copias remotas;
la cuenta principal determina el estado canónico local.

El gestor de Ajustes permite conectar varias cuentas, elegir la principal y definir
la dirección de sincronización. El cliente selecciona la credencial activa para cada
consulta y mutación sin mezclar cachés.

MyAnimeList está disponible como importación de solo lectura mediante OAuth PKCE. La
configuración y las limitaciones están documentadas en
[`docs/MYANIMELIST.md`](docs/MYANIMELIST.md). Antes de distribuir esta integración se
debe validar el flujo con una aplicación registrada y revisar las políticas vigentes.
Las obras importadas se asocian de forma conservadora con AniList usando títulos
alternativos, año, formato y episodios; las coincidencias ambiguas no se fusionan.
La bandeja de Ajustes permite confirmar, descartar y revertir estas asociaciones.

La WebExtension para Chromium y Firefox está en [`apps/extension`](apps/extension).
Usa emparejamiento de un solo uso, tokens rotatorios por instalación y controles de
privacidad por sitio. Consulta su [README](apps/extension/README.md).

El backlog completo, prioridades y criterios de entrega están en
[`PENDIENTE.md`](PENDIENTE.md).
