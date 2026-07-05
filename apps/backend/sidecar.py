import sys

import uvicorn

from nyanko_api.config import get_settings
from nyanko_api.instance import resolve_port


def main() -> None:
    # Escuchar en el puerto configurado (fijo, p. ej. 8765) para que coincida con el
    # redirect_uri registrado en AniList/MAL; con fallback a uno libre si está ocupado.
    # Se fija settings.api_port para que la lifespan escriba el puerto real al port file.
    settings = get_settings()
    port = resolve_port(settings.api_host, settings.api_port)
    settings.api_port = port
    uvicorn.run(
        "nyanko_api.main:app",
        host=settings.api_host,
        port=port,
        log_level="info",
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    sys.exit(main())
