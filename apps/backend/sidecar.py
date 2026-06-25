import sys

import uvicorn


def main() -> None:
    uvicorn.run(
        "nyanko_api.main:app",
        host="127.0.0.1",
        port=0,
        log_level="info",
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    sys.exit(main())
