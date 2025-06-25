from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.confluence_client import ConfluenceClient


class PageCreate(BaseModel):
    title: str
    content: str
    parent_id: Optional[str] = Field(None, description="Parent page ID")


class PageUpdate(BaseModel):
    title: Optional[str] = Field(None, description="New title")
    content: Optional[str] = Field(None, description="New content in storage format")


def create_app() -> FastAPI:
    client = ConfluenceClient()
    app = FastAPI(
        title="Confluence toolset",
        description=(
            "This API toolset is created to provide AI agents with the ability to "
            "work with confluence pages in limited scope. Scope is limited under "
            "certain parent page and modifications work only under that page"
        ),
        version="0.0.1",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/pages", summary="List pages")
    def list_pages():
        return client.list_pages()

    @app.get("/pages/{page_id}", summary="Read page")
    def read_page(page_id: str, include_children: bool = False):
        return client.get_page_summary(page_id, include_children=include_children)

    @app.post("/pages", summary="Create page")
    def create_page(data: PageCreate):
        return client.create_page(data.title, data.content, data.parent_id)

    @app.put("/pages/{page_id}", summary="Update page")
    def update_page(page_id: str, data: PageUpdate):
        return client.update_page(page_id, data.title, data.content)

    @app.delete("/pages/{page_id}", summary="Delete page")
    def remove_page(page_id: str):
        client.delete_page(page_id)
        return {"status": "deleted"}

    @app.get("/search", summary="Search pages")
    def search(cql: str, limit: int = 100):
        return client.search(cql_query=cql, limit=limit)

    @app.get(
        "/pages/{page_id}/inline-comments",
        summary="List inline comments for a page",
    )
    def list_inline_comments(page_id: str, body_format: str = "storage"):
        return client.get_inline_comments(page_id, body_format=body_format)

    @app.post(
        "/inline-comments/{comment_id}/reply",
        summary="Reply to an inline comment",
    )
    def reply_inline(comment_id: str, body: str):
        return client.reply_inline_comment(comment_id, body)

    @app.get(
        "/pages/{page_id}/footer-comments",
        summary="List footer comments for a page",
    )
    def list_footer_comments(page_id: str, body_format: str = "storage"):
        return client.get_footer_comments(page_id, body_format=body_format)

    @app.post(
        "/pages/{page_id}/footer-comments",
        summary="Add a footer comment to a page",
    )
    def add_footer_comment(page_id: str, body: str):
        return client.add_footer_comment(page_id, body)

    return app
