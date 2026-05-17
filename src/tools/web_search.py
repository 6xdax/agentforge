"""Volcengine web search tool (web/web_summary/image)."""

import json
import os
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agent import tool_error, tool_result


APIKEY_ENDPOINT = "https://open.feedcoopapi.com/search_api/web_search"
TOP_ENDPOINT = "https://mercury.volcengineapi.com?Action=WebSearch&Version=2025-01-01"
ALLOWED_SEARCH_TYPES = {"web", "web_summary", "image"}
ALLOWED_TIME_RANGE = {"OneDay", "OneWeek", "OneMonth", "OneYear"}
ALLOWED_CONTENT_FORMATS = {"text", "markdown"}
ALLOWED_INDUSTRY = {"finance", "game"}


def _is_date_range(value: str) -> bool:
    """Validate YYYY-MM-DD..YYYY-MM-DD date range format."""
    if ".." not in value:
        return False
    start, end = value.split("..", 1)
    try:
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _validate_args(args: dict) -> str | None:
    """Return error message when args are invalid, otherwise None."""
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return "query is required and must be a non-empty string"
    if len(query.strip()) > 100:
        return "query length must be <= 100"

    search_type = args.get("search_type")
    if search_type not in ALLOWED_SEARCH_TYPES:
        return "search_type must be one of: web, web_summary, image"

    count = args.get("count")
    if count is not None:
        if not isinstance(count, int) or count <= 0:
            return "count must be a positive integer"
        max_count = 5 if search_type == "image" else 50
        if count > max_count:
            return f"count exceeds max for {search_type}: {max_count}"

    need_summary = args.get("need_summary")
    if search_type == "web_summary" and need_summary is not True:
        return "need_summary must be true when search_type is web_summary"

    time_range = args.get("time_range")
    if time_range is not None:
        if not isinstance(time_range, str):
            return "time_range must be a string"
        if time_range not in ALLOWED_TIME_RANGE and not _is_date_range(time_range):
            return "time_range must be OneDay/OneWeek/OneMonth/OneYear or YYYY-MM-DD..YYYY-MM-DD"

    content_formats = args.get("content_formats")
    if content_formats is not None and content_formats not in ALLOWED_CONTENT_FORMATS:
        return "content_formats must be one of: text, markdown"

    industry = args.get("industry")
    if industry is not None and industry not in ALLOWED_INDUSTRY:
        return "industry must be one of: finance, game"

    auth_mode = args.get("auth_mode", "apikey")
    if auth_mode not in {"apikey", "top"}:
        return "auth_mode must be apikey or top"

    if auth_mode == "apikey" and not args.get("api_key") and not os.getenv("VOLC_WEB_SEARCH_API_KEY"):
        return "api_key is required for auth_mode=apikey (or set VOLC_WEB_SEARCH_API_KEY)"

    if auth_mode == "top" and not isinstance(args.get("top_headers"), dict):
        return "top_headers (dict) is required for auth_mode=top; provide signed IAM headers"

    return None


def _build_payload(args: dict) -> dict:
    """Build request payload from tool args."""
    payload = {
        "Query": args["query"].strip(),
        "SearchType": args["search_type"],
    }

    if args.get("count") is not None:
        payload["Count"] = args["count"]

    filter_obj = args.get("filter")
    if isinstance(filter_obj, dict) and filter_obj:
        payload["Filter"] = filter_obj

    if args.get("need_summary") is not None:
        payload["NeedSummary"] = bool(args["need_summary"])

    if args.get("time_range"):
        payload["TimeRange"] = args["time_range"]

    if args.get("query_rewrite") is not None:
        payload["QueryControl"] = {"QueryRewrite": bool(args["query_rewrite"])}

    if args.get("content_formats"):
        payload["ContentFormats"] = args["content_formats"]

    if args.get("industry"):
        payload["Industry"] = args["industry"]

    # Optional raw merge for advanced fields from upstream docs.
    raw_payload = args.get("raw_payload")
    if isinstance(raw_payload, dict):
        payload.update(raw_payload)

    return payload


def _request_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    """Send POST JSON request and return parsed JSON response."""
    req = Request(
        url=url,
        method="POST",
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw_response": body}


def _handle(args: dict) -> str:
    """Handle web search calls."""
    err = _validate_args(args)
    if err:
        return tool_error(err)

    auth_mode = args.get("auth_mode", "apikey")
    payload = _build_payload(args)
    timeout = float(args.get("timeout", 20.0))

    if auth_mode == "apikey":
        url = args.get("endpoint") or APIKEY_ENDPOINT
        api_key = os.getenv("VOLC_WEB_SEARCH_API_KEY", "")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
    else:
        url = args.get("endpoint") or TOP_ENDPOINT
        headers = {"Content-Type": "application/json", **args.get("top_headers", {})}

    try:
        data = _request_json(url=url, headers=headers, payload=payload, timeout=timeout)
        metadata = data.get("ResponseMetadata") if isinstance(data, dict) else None
        error = metadata.get("Error") if isinstance(metadata, dict) else None
        if error:
            return tool_error(
                error.get("Message", "web search request failed"),
                code=error.get("Code"),
                code_n=error.get("CodeN"),
                response=data,
            )
        return tool_result(data)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return tool_error(
            f"HTTPError: {e.code}",
            status_code=e.code,
            response_body=body,
        )
    except URLError as e:
        return tool_error(f"URLError: {e.reason}")
    except Exception as e:
        return tool_error(str(e))


def register(registry):
    """Register volc web search tool."""
    registry.register(
        name="web_search",
        schema={
            "name": "web_search",
            "description": "Call Volcengine web search API (web/image) with APIKey or pre-signed TOP headers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (1-100 chars)",
                    },
                    "search_type": {
                        "type": "string",
                        "description": "Search type: web, image",
                        "enum": ["web", "image"],
                    },
                    "auth_mode": {
                        "type": "string",
                        "description": "Auth mode: apikey or top",
                        "enum": ["apikey", "top"],
                        "default": "apikey",
                    },
                    "top_headers": {
                        "type": "object",
                        "description": "Signed IAM headers for TOP mode (Authorization, X-Date, etc.)",
                    },
                    "endpoint": {
                        "type": "string",
                        "description": "Optional override endpoint URL",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Result count. image max 5, web max 50",
                    },
                    "filter": {
                        "type": "object",
                        "description": "Filter object from API docs, e.g. NeedContent/NeedUrl/Sites/BlockHosts/AuthInfoLevel",
                    },
                    "time_range": {
                        "type": "string",
                        "description": "OneDay/OneWeek/OneMonth/OneYear or YYYY-MM-DD..YYYY-MM-DD",
                    },
                    "query_rewrite": {
                        "type": "boolean",
                        "description": "Enable query rewrite in QueryControl",
                    },
                    "content_formats": {
                        "type": "string",
                        "description": "Content format for returned content: text or markdown",
                        "enum": ["text", "markdown"],
                    },
                    "industry": {
                        "type": "string",
                        "description": "Industry mode: finance or game",
                        "enum": ["finance", "game"],
                    },
                    "raw_payload": {
                        "type": "object",
                        "description": "Advanced raw payload merged into final request body",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "HTTP timeout seconds, default 20",
                        "default": 20,
                    },
                },
                "required": ["query", "search_type"],
            },
        },
        handler=_handle,
    )


register_web_search = register

__all__ = ["register", "register_web_search"]
