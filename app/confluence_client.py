import os
import logging
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

from dotenv import load_dotenv, find_dotenv
import html2text

# Load environment variables from .env file (search upward for .env)
dotenv_path = find_dotenv()
load_dotenv(dotenv_path)
logger.debug("Loaded environment variables from %s", dotenv_path)


class ConfluenceClient:
    """Simple client for interacting with Confluence Cloud."""

    def __init__(self) -> None:
        self.url = os.environ.get("CONFLUENCE_URL")
        self.username = os.environ.get("CONFLUENCE_USERNAME")
        # Prefer CONFLUENCE_API_TOKEN for compatibility with server.py, fallback to CONFLUENCE_TOKEN
        self.token = os.environ.get("CONFLUENCE_API_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
        self.space_key = os.environ.get("CONFLUENCE_SPACE_KEY")
        self.parent_page = os.environ.get("CONFLUENCE_PARENT_PAGE", None)

        logger.debug(
            "Env vars - URL: %s USERNAME: %s TOKEN_SET: %s",
            self.url,
            self.username,
            bool(self.token),
        )

        if not all([self.url, self.username, self.token]):
            raise RuntimeError(
                "CONFLUENCE_URL, CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN (or CONFLUENCE_TOKEN) must be set"
            )
        # Make sure url is not None before checking endswith
        if self.url and not self.url.endswith('/'):
            self.url += '/'
        self.session = requests.Session()
        if self.username is None or self.token is None:
            raise RuntimeError("Username and token must not be None")
        self.session.auth = (self.username, self.token)
        self.session.headers.update({"Content-Type": "application/json"})

    def _html_to_markdown(self, html: str) -> str:
        """Convert Confluence HTML content to Markdown."""
        return html2text.html2text(html)

    def _ensure_allowed(self, page_id: str) -> None:
        """Ensure the given page is within the allowed parent scope."""
        if not self.parent_page:
            return
        cql = f"id={page_id} and ancestor={self.parent_page}"
        rsp = self.search(cql, limit=1)
        if rsp.get("size", 0) == 0:
            raise HTTPException(
                status_code=403,
                detail="Operation not allowed on a page outside the configured parent scope",
            )

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
        json: Any = None,
    ) -> Dict[str, Any]:
        url = endpoint if endpoint.startswith("http") else f"{self.url}{endpoint}"
        logger.debug("Request %s %s params=%s json=%s", method, url, params, json)
        response = self.session.request(method, url, params=params, json=json)
        if not response.ok:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

    def _make_direct_request(self, url: str) -> Dict[str, Any]:
        response = self.session.get(url)
        if not response.ok:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

    def search(
        self,
        cql_query: str,
        batch_size: int = 25,
        limit: int = 100,
        cursor: Optional[str] = None,
        expand: Optional[List[str]] = None,
        cql_context: Optional[str] = None,
        excerpt: Optional[str] = None,
        include_archived_spaces: bool = False,
        exclude_current_spaces: bool = False,
    ) -> Dict[str, Any]:
        """Search Confluence using CQL with cursor-based pagination."""
        endpoint = f"{self.url}rest/api/search"
        params = {
            "cql": cql_query,
            "limit": min(batch_size, limit),
        }
        if cursor:
            params["cursor"] = cursor
        if cql_context:
            params["cqlcontext"] = cql_context
        if expand:
            params["expand"] = ",".join(expand)
        if excerpt:
            params["excerpt"] = excerpt
        if include_archived_spaces:
            params["includeArchivedSpaces"] = "true"
        if exclude_current_spaces:
            params["excludeCurrentSpaces"] = "true"

        response = self._make_request(endpoint, params)
        result = response.copy()
        all_results = response.get("results", [])
        results_count = len(all_results)

        while (
            "_links" in response
            and "next" in response["_links"]
            and results_count < limit
        ):
            next_link = response["_links"]["next"]
            if next_link.startswith("/"):
                base_url = self.url.rstrip("/") if self.url else ""
                next_url = f"{base_url}{next_link}"
            else:
                next_url = next_link
            response = self._make_direct_request(next_url)
            new_results = response.get("results", [])
            all_results.extend(new_results)
            results_count = len(all_results)

        result["results"] = all_results[:limit]
        result["size"] = len(result["results"])
        return result

    def get_page(self, page_id: str) -> Dict[str, Any]:
        endpoint = f"rest/api/content/{page_id}"
        return self._make_request(endpoint, params={"expand": "body.storage,version"})

    def _get_children_recursive(self, page_id: str) -> List[Dict[str, Any]]:
        """Recursively fetch all child pages for a page."""
        endpoint = f"rest/api/content/{page_id}/child/page"
        params = {"expand": "body.export_view,ancestors,version"}
        data = self._make_request(endpoint, params=params)
        base = data.get("_links", {}).get("base", "")
        children: List[Dict[str, Any]] = []
        for child in data.get("results", []):
            ancestors = child.get("ancestors", [])
            item = {
                "id": child.get("id"),
                "title": child.get("title"),
                "content": self._html_to_markdown(child["body"]["export_view"]["value"]),
                "url": base + child.get("_links", {}).get("webui", ""),
                "last_modified": child.get("version", {}).get("friendlyWhen"),
                "parent_page_id": ancestors[-1]["id"] if ancestors else None,
                "parent_page_title": ancestors[-1]["title"] if ancestors else None,
            }
            descendants = self._get_children_recursive(child["id"])
            if descendants:
                item["children"] = descendants
            children.append(item)
        return children

    def get_page_summary(self, page_id: str, include_children: bool = False) -> Dict[str, Any]:
        """Return key details for a page with content converted to Markdown."""
        endpoint = f"rest/api/content/{page_id}"
        expansions = ["body.export_view", "ancestors", "version"]
        data = self._make_request(endpoint, params={"expand": ",".join(expansions)})
        ancestors = data.get("ancestors", [])
        parent_id = ancestors[-1]["id"] if ancestors else None
        parent_title = ancestors[-1]["title"] if ancestors else None
        base = data.get("_links", {}).get("base", "")
        url = base + data.get("_links", {}).get("webui", "")
        page = {
            "id": data.get("id"),
            "title": data.get("title"),
            "content": self._html_to_markdown(data["body"]["export_view"]["value"]),
            "url": url,
            "last_modified": data.get("version", {}).get("friendlyWhen"),
            "parent_page_id": parent_id,
            "parent_page_title": parent_title,
            "modifier": data.get("version", {}).get("by", {}).get("displayName"),
        }
        if include_children:
            page["children"] = self._get_children_recursive(page_id)
        return page

    def list_pages(self) -> List[Dict[str, Any]]:
        cql = f"space={self.space_key} and type=page"
        if self.parent_page:
            cql += f" and ancestor={self.parent_page}"
        data = self.search(
            cql,
            limit=1000,
            expand=["title", "url", "content.body.export_view", "content.ancestors"],
        )
        filtered: List[Dict[str, Any]] = []
        for result in data.get("results", []):
            if "title" in result and "content" in result:
                ancestors = result["content"].get("ancestors", [])
                filtered.append(
                    {
                        "id": result["content"]["id"],
                        "title": result["title"],
                        "content": self._html_to_markdown(
                            result["content"]["body"]["export_view"]["value"]
                        ),
                        "url": data.get("_links", {}).get("base", "") + result["url"],
                        "last_modified": result.get("friendlyLastModified"),
                        "parent_page_id": ancestors[-1]["id"] if ancestors else None,
                        "parent_page_title": ancestors[-1]["title"] if ancestors else None,
                    }
                )
        return filtered

    def create_page(
        self, title: str, content: str, parent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.space_key:
            raise HTTPException(status_code=500, detail="CONFLUENCE_SPACE_KEY not set")

        if parent_id is None:
            parent_id = self.parent_page

        if self.parent_page:
            # ensure the chosen parent is within the allowed scope
            target_id = parent_id or self.parent_page
            if target_id != self.parent_page:
                cql = f"id={target_id} and ancestor={self.parent_page}"
                rsp = self.search(cql, limit=1)
                if rsp.get("size", 0) == 0:
                    raise HTTPException(
                        status_code=403,
                        detail="Parent page not within allowed scope",
                    )
        data = {
            "type": "page",
            "title": title,
            "space": {"key": self.space_key},
            "body": {"storage": {"value": content, "representation": "storage"}},
        }
        if parent_id:
            data["ancestors"] = [{"id": parent_id}]
        return self._make_request("rest/api/content", method="POST", json=data)

    def update_page(self, page_id: str, title: Optional[str], content: Optional[str]) -> Dict[str, Any]:
        self._ensure_allowed(page_id)
        page = self.get_page(page_id)
        version = page.get("version", {}).get("number", 1)
        new_version = version + 1
        data = {
            "id": page_id,
            "type": "page",
            "title": title or page["title"],
            "version": {"number": new_version},
            "body": {
                "storage": {
                    "value": content or page["body"]["storage"]["value"],
                    "representation": "storage",
                }
            },
        }
        return self._make_request(f"rest/api/content/{page_id}", method="PUT", json=data)

    def delete_page(self, page_id: str) -> None:
        self._ensure_allowed(page_id)
        self._make_request(f"rest/api/content/{page_id}", method="DELETE")

    def get_inline_comments(
        self, page_id: str, body_format: str | None = "storage"
    ) -> dict:
        """Fetch inline comments for the specified page."""
        endpoint = f"api/v2/pages/{page_id}/inline-comments"
        params = {"body-format": body_format} if body_format else None
        return self._make_request(endpoint, params=params)

    def reply_inline_comment(self, comment_id: str, body: str) -> dict:
        """Reply to an inline comment using the v2 API."""
        endpoint = "api/v2/inline-comments"
        data = {
            "parentCommentId": comment_id,
            "body": {
                "storage": {"value": body, "representation": "storage"}
            },
        }
        return self._make_request(endpoint, method="POST", json=data)

    def get_footer_comments(
        self, page_id: str, body_format: str | None = "storage"
    ) -> dict:
        """Get footer comments for a page."""
        endpoint = f"api/v2/pages/{page_id}/footer-comments"
        params = {"body-format": body_format} if body_format else None
        return self._make_request(endpoint, params=params)

    def add_footer_comment(self, page_id: str, body: str) -> dict:
        """Add a footer comment to a page."""
        endpoint = "api/v2/footer-comments"
        data = {
            "pageId": page_id,
            "body": {
                "storage": {"value": body, "representation": "storage"}
            },
        }
        return self._make_request(endpoint, method="POST", json=data)


def _print_page_summary(page: Dict[str, Any]) -> None:
    """Pretty print selected page summary fields."""
    from pprint import pprint

    pprint(page)


def _print_pages(pages: List[Dict[str, Any]]) -> None:
    """Pretty print a list of pages."""
    from pprint import pprint

    pprint(pages)


def main() -> None:
    """Run simple tests when executed as a script."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Confluence client")
    parser.add_argument("--list", action="store_true", help="List pages")
    parser.add_argument("--page-id", help="Show a single page summary")
    args = parser.parse_args()

    client = ConfluenceClient()

    if args.page_id:
        _print_page_summary(client.get_page_summary(args.page_id))
    else:
        pages = client.list_pages() if args.list or not args.page_id else []
        _print_pages(pages)


if __name__ == "__main__":
    main()
