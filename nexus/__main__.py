"""`python -m nexus` — run the server. That's the whole deployment story."""

import uvicorn

from .app import create_app
from .config import Settings


def main() -> None:
    settings = Settings()
    print(f"🦖 Nexus Core starting on {settings.host}:{settings.port}")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port,
                log_level="info")


if __name__ == "__main__":
    main()
