from __future__ import annotations

import asyncio
import os

import uvicorn

from ..settings import settings as _settings


def main() -> None:
    loop_factory: str | type[asyncio.SelectorEventLoop]
    loop_factory = (
        asyncio.SelectorEventLoop
        if os.name == "nt"
        else "auto"
    )
    uvicorn.run(
        "baseia_extract.catalog.api:app",
        host=os.getenv("CATALOG_API_HOST", "127.0.0.1"),
        port=int(os.getenv("CATALOG_API_PORT", "8088")),
        loop=loop_factory,
    )


if __name__ == "__main__":
    main()
