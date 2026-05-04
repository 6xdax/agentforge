"""JSON Schema validation and retry loop for reliable tool calling.

Three-layer approach:
1. Prompt optimization (soft constraint)
2. JSON Schema validation (hard constraint)
3. Validate-clean-retry loop (fallback mechanism)

Requires jsonschema package: pip install jsonschema
"""

import asyncio
import json
import re
from typing import Any, Callable, Optional

from agent.errors import jittered_backoff

# Try to import jsonschema, provide clear error if missing
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


class SchemaValidationError(Exception):
    """Raised when tool output fails schema validation."""
    def __init__(self, message: str, validation_error: Any = None):
        super().__init__(message)
        self.validation_error = validation_error


class SchemaValidator:
    """Validates tool call arguments against JSON Schema with retry support.
    
    Usage:
        schema = {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}
            },
            "required": ["city", "date"],
            "additionalProperties": False
        }
        validator = SchemaValidator(schema)
        
        # Returns validated dict or raises SchemaValidationError
        result = validator.validate_and_retries(raw_model_output)
    """
    
    def __init__(
        self,
        schema: dict,
        max_retries: int = 3,
        base_delay: float = 1.0,
        clean_fn: Optional[Callable[[str], str]] = None,
    ):
        """Initialize validator.
        
        Args:
            schema: JSON Schema to validate against
            max_retries: Maximum retry attempts after validation failure
            base_delay: Base delay for exponential backoff
            clean_fn: Optional custom cleaning function for malformed output
        """
        if not HAS_JSONSCHEMA:
            raise ImportError(
                "jsonschema is required for SchemaValidator. "
                "Install it with: pip install jsonschema"
            )
        self.schema = schema
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.clean_fn = clean_fn or self._default_clean

    def _coerce_retry_output(self, retry_output: Any) -> Optional[str]:
        """Normalize retry callback output.

        Returning None signals that the caller chose not to retry.
        """
        if retry_output is None:
            return None
        if isinstance(retry_output, str):
            return retry_output
        raise SchemaValidationError(
            "retry_feedback_fn must return a string or None"
        )
    
    def _default_clean(self, raw: str) -> str:
        """Clean common LLM output artifacts before JSON parsing.
        
        Handles:
        - Markdown code blocks (```json ... ```)
        - Trailing commas
        - Unescaped quotes inside strings
        - Invisible unicode characters
        """
        text = raw.strip()
        
        # Strip markdown code blocks
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        
        # Remove trailing commas before closing braces/brackets
        text = re.sub(r",(\s*[}\]])", r"\1", text)
        
        # Attempt to fix common quote issues
        # Replace single quotes used as string delimiters with double quotes
        # Only if it looks like a JSON object/array
        if text.startswith(("{", "[")):
            try:
                # First try as-is
                json.loads(text)
            except json.JSONDecodeError:
                # Try fixing single quotes
                # This is a simple heuristic: replace outer single quotes
                if text.startswith("{") and text.endswith("}"):
                    # Replace 'key': with "key":
                    text = re.sub(r"'([^']+)':", r'"\1":', text)
                    # Replace 'value' at value positions (not already fixed)
                    text = re.sub(r':\s*\'([^\']*)\'', r': "\1"', text)
        
        return text.strip()
    
    def _extract_json(self, raw: str) -> dict:
        """Extract JSON object/array from raw model output."""
        if not isinstance(raw, str):
            raise SchemaValidationError(
                f"Expected raw model output to be str, got {type(raw).__name__}"
            )
        cleaned = self.clean_fn(raw)
        
        # Try direct parse first
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown
        json_match = re.search(
            r"\{[^{}]*(?:\{[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}[^{}]*)*\}",
            cleaned,
            re.DOTALL
        )
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        raise SchemaValidationError(
            f"Failed to parse JSON from model output: {cleaned[:200]}"
        )
    
    def validate(self, instance: dict) -> dict:
        """Validate instance against schema.
        
        Args:
            instance: Parsed JSON dict to validate
            
        Returns:
            Validated instance
            
        Raises:
            SchemaValidationError: If validation fails
        """
        try:
            jsonschema.validate(instance=instance, schema=self.schema)
        except jsonschema.ValidationError as e:
            raise SchemaValidationError(
                f"Schema validation failed: {e.message}",
                validation_error=e
            )
        return instance
    
    async def validate_and_retries(
        self,
        raw_model_output: str,
        retry_feedback_fn: Optional[Callable[[int, str], Optional[str]]] = None,
    ) -> dict:
        """Parse and validate model output with retry loop.
        
        Flow:
        1. Parse JSON from raw output
        2. Validate against schema
        3. On failure, optionally retry with feedback
        
        Args:
            raw_model_output: Raw string output from LLM
            retry_feedback_fn: Optional fn(attempt, error_msg) -> new_model_output.
                If provided, will retry after validation failure.
            
        Returns:
            Validated and parsed dict
            
        Raises:
            SchemaValidationError: If all retries exhausted
        """
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                parsed = self._extract_json(raw_model_output)
                return self.validate(parsed)
            except SchemaValidationError as e:
                last_error = e
                
                if attempt < self.max_retries and retry_feedback_fn:
                    # Apply backoff before retry
                    delay = jittered_backoff(attempt, base=self.base_delay)
                    await asyncio.sleep(delay)
                    
                    # Get feedback and retry
                    next_output = self._coerce_retry_output(retry_feedback_fn(
                        attempt + 1,
                        str(last_error),
                    ))
                    if next_output is None:
                        break
                    raw_model_output = next_output
        
        raise last_error


def create_tool_schema(
    name: str,
    description: str,
    properties: dict,
    required: list[str] = None,
    additional_properties: bool = False,
) -> dict:
    """Helper to create a tool schema dict.
    
    Args:
        name: Tool name
        description: Tool description
        properties: Schema properties dict
        required: List of required property names
        additional_properties: If False, reject unknown fields
        
    Returns:
        OpenAI-format tool schema
    """
    schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = required
    
    return {
        "name": name,
        "description": description,
        "parameters": schema,
    }
