import os
import uvicorn
from app.server import create_app


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.server:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
