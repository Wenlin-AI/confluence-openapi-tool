import uvicorn
import typer


def main(host: str = "127.0.0.1", port: int = 8123) -> None:
    """Start Confluence OpenAPI Tools server."""
    uvicorn.run("app.server:create_app", host=host, port=port, factory=True)


def entrypoint() -> None:
    typer.run(main)


if __name__ == "__main__":
    entrypoint()
