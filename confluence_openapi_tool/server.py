from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx


class Settings(BaseModel):
    url: str
    username: str
    token: str
    space_key: str
    parent_page: Optional[str] = None
    allowed_origins: Optional[str] = "*"


def load_settings() -> Settings:
    try:
        return Settings(
            url=os.environ["CONFLUENCE_URL"],
            username=os.environ["CONFLUENCE_USERNAME"],
            token=os.environ["CONFLUENCE_TOKEN"],
            space_key=os.environ["CONFLUENCE_SPACE_KEY"],
            parent_page=os.getenv("CONFLUENCE_PARENT_PAGE"),
            allowed_origins=os.getenv("ALLOWED_ORIGINS", "*")
        )
    except KeyError as exc:
        missing = exc.args[0]
        raise RuntimeError(f"Missing required environment variable: {missing}")


class PageCreate(BaseModel):
    title: str
    body: str


class PageUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="Confluence OpenAPI Tool")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origins] if settings.allowed_origins != "*" else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def get_client() -> httpx.AsyncClient:
        auth = (settings.username, settings.token)
        return httpx.AsyncClient(auth=auth, base_url=settings.url.rstrip("/") + "/wiki/rest/api")

    @app.get("/pages/{page_id}")
    async def get_page(page_id: str):
        async with await get_client() as client:
            resp = await client.get(f"/content/{page_id}", params={"expand": "body.storage,version"})
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()

    @app.get("/pages")
    async def list_pages(limit: int = 25):
        async with await get_client() as client:
            resp = await client.get("/content", params={"type": "page", "spaceKey": settings.space_key, "limit": limit})
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()

    @app.post("/pages")
    async def create_page(page: PageCreate):
        payload = {
            "type": "page",
            "title": page.title,
            "space": {"key": settings.space_key},
            "body": {"storage": {"value": page.body, "representation": "storage"}},
        }
        if settings.parent_page:
            payload["ancestors"] = [{"id": settings.parent_page}]
        async with await get_client() as client:
            resp = await client.post("/content", json=payload)
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()

    @app.put("/pages/{page_id}")
    async def update_page(page_id: str, update: PageUpdate):
        async with await get_client() as client:
            current = await client.get(f"/content/{page_id}", params={"expand": "version"})
            if current.status_code >= 400:
                raise HTTPException(status_code=current.status_code, detail=current.text)
            data = current.json()
            version = data["version"]["number"] + 1
            payload = {
                "id": page_id,
                "type": "page",
                "title": update.title or data["title"],
                "version": {"number": version},
                "body": {"storage": {"value": update.body or data.get("body", {}).get("storage", {}).get("value", ""), "representation": "storage"}}
            }
            resp = await client.put(f"/content/{page_id}", json=payload)
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()

    return app
