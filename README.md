# Confluence OpenAPI Tool

A minimal FastAPI wrapper for interacting with Confluence Cloud pages. The server exposes a small REST API that AI agents can call. It is packaged so you can install it directly from GitHub and start the service from the command line.

## Installation

```bash
pip install git+https://github.com/Wenlin-AI/confluence-openapi-tool.git
```

## Configuration

Set the following environment variables (for example in a `.env` file):

- `CONFLUENCE_URL` – Base URL of your Confluence Cloud instance (`https://your-site.atlassian.net/`)
- `CONFLUENCE_USERNAME` – Username or email used for authentication
- `CONFLUENCE_TOKEN` – API token for authentication
- `CONFLUENCE_SPACE_KEY` – Space key where new pages are created
- `CONFLUENCE_PARENT_PAGE` – *(optional)* Parent page ID restricting write operations

## Running

After installing, launch the server with the bundled CLI:

```bash
confluence-openapi-tool --host 0.0.0.0 --port 8123
```

Navigate to `http://localhost:8123/docs` to explore the API.

## Docker

You can build an image straight from the GitHub repository:

```bash
docker build -t confluence-openapi-tool \
  https://github.com/Wenlin-AI/confluence-openapi-tool.git#main
```

Run the container with your environment variables:

```bash
docker run --env-file .env -p 8123:8123 confluence-openapi-tool
```

> **Warning**
> The default configuration enables CORS for all origins. Do **not** use this setting on a public server. Configure `allowed_origins` appropriately when deploying.

