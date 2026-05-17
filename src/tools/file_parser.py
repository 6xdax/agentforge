"""Document parsing using docling for PDF, DOCX, images, etc."""

import json
from pathlib import Path
from typing import Literal

from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption

from agent.errors import ToolError


def _detect_encoding(file_path: Path) -> Literal["utf-8", "gbk", "gb2312", "latin-1"]:
    """Detect file encoding by reading BOM or first bytes."""
    try:
        with open(file_path, "rb") as f:
            raw = f.read(4)
        # BOM signatures
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8"
        elif raw.startswith(b"\xff\xfe"):
            return "utf-16-le"
        elif raw.startswith(b"\xfe\xff"):
            return "utf-16-be"
        # Try to decode as utf-8, fallback to gbk
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.read(1024)
            return "utf-8"
        except UnicodeDecodeError:
            return "gbk"
    except Exception:
        return "utf-8"


# Initialize converter with default settings
_converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            do_ocr=False,
        )
    }
)


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
        suffix = path.suffix.lower()
        if suffix in [".txt", ".log", ".md", ".json", ".csv"]:
            encoding = _detect_encoding(path)
            return path.read_text(
                encoding=encoding,
                errors="ignore"
            )

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

if __name__ == "__main__":
    # Example usage
    import asyncio

    async def main():
        # text = await parse_document("/home/ubuntu/workspace/agentforge/projects/chatbot/backend/user_data/a4ad2faf-3e96-4aa9-b24f-cf7c84d641ce/1778942733054____.pdf")
        text = await parse_document("/home/ubuntu/workspace/agentforge/projects/chatbot/backend/user_data/a4ad2faf-3e96-4aa9-b24f-cf7c84d641ce/1778943419191_NetLog.txt")
        print(text)

    asyncio.run(main())