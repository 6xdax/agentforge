"""Document parsing using docling for PDF, DOCX, images, etc."""

import json
from pathlib import Path

from docling.document_converter import DocumentConverter

from agent.errors import ToolError


# Initialize converter with default settings
_converter = DocumentConverter()


async def parse_document(file_path: str, max_text_length: int = 100000) -> str:
    """Parse a document using docling and return its text content.

    Supports: PDF, DOCX, PPTX, XLSX, HTML, TXT, images, etc.

    Args:
        file_path: Path to the document file
        max_text_length: Maximum text length to return (truncate if exceeded)

    Returns:
        Extracted text content from the document

    Raises:
        ToolError: If file cannot be read or parsed
    """
    path = Path(file_path)

    if not path.exists():
        raise ToolError(f"File not found: {file_path}")

    if not path.is_file():
        raise ToolError(f"Not a file: {file_path}")

    try:
        result = _converter.convert(str(path.absolute()))
        text = result.document.export_to_text()

        if len(text) > max_text_length:
            text = text[:max_text_length] + f"\n\n[Truncated - original length: {len(text)} chars]"

        return text

    except Exception as exc:
        raise ToolError(f"Failed to parse document: {exc}")


def get_document_schema() -> dict:
    """Return the tool schema for document parsing."""
    return {
        "name": "parse_document",
        "description": "Parse and extract text content from documents (PDF, DOCX, PPTX, XLSX, HTML, TXT, images). Returns the full text content of the document.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the document file to parse",
                },
                "max_text_length": {
                    "type": "integer",
                    "description": "Maximum text length to return (default: 100000)",
                    "default": 100000,
                },
            },
            "required": ["file_path"],
        },
    }


async def _handle(args: dict) -> str:
    """Handle document parsing calls."""
    try:
        result = await parse_document(args.get("file_path", ""), args.get("max_text_length", 100000))
        return json.dumps({"content": result, "success": True})
    except ToolError as e:
        return json.dumps({"error": str(e), "success": False})


# Self-registration
def register(registry):
    """Register the document parsing tool with the registry."""
    registry.register(
        name="parse_document",
        schema=get_document_schema(),
        handler=_handle,
    )


register_parse_document = register

__all__ = ["register", "register_parse_document", "parse_document"]