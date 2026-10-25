import mimetypes
import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PySide6.QtCore import QThread, Signal

from config import get_base_dir
from tools import TOOL_METADATA, execute_allowlisted_tool, validate_and_describe_tool_call


TOOL_SCHEMAS = {
    "get_system_troubleshooting_info": {
        "type": "object",
        "properties": {},
    },
    "check_file_exists": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "File or directory path to inspect."},
        },
        "required": ["file_path"],
    },
    "list_approved_folder": {
        "type": "object",
        "properties": {
            "folder_path": {"type": "string", "description": "Directory path to list."},
        },
        "required": ["folder_path"],
    },
    "run_predefined_diagnostic": {
        "type": "object",
        "properties": {
            "check_name": {
                "type": "string",
                "enum": ["disk_space", "env_check", "localhost_net"],
                "description": "Name of the predefined read-only diagnostic.",
            },
        },
        "required": ["check_name"],
    },
    "open_approved_target": {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Approved file path, notepad, or calc."},
        },
        "required": ["target"],
    },
}

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
RETIRED_GEMINI_MODELS = {
    "gemini-2.5-flash": DEFAULT_GEMINI_MODEL,
}


def get_gemini_model() -> str:
    configured_model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    return RETIRED_GEMINI_MODELS.get(configured_model, configured_model or DEFAULT_GEMINI_MODEL)


class GeminiWorker(QThread):
    status_update = Signal(str)
    response_ready = Signal(str, object)
    error_occurred = Signal(str)
    tool_approval_requested = Signal(dict)
    tool_executed_log = Signal(str)

    def __init__(
        self,
        history: list[types.Content],
        user_text: str,
        image_path: str | None,
        copied_snippet: str | None,
        tools_enabled: bool,
        disabled_tools: list[str],
    ):
        super().__init__()
        self.history = list(history)
        self.user_text = user_text
        self.image_path = image_path
        self.copied_snippet = copied_snippet
        self.tools_enabled = tools_enabled
        self.disabled_tools = list(disabled_tools)
        self._approval_event = threading.Event()
        self._approval_decision = False

    def set_tool_approval_decision(self, approved: bool) -> None:
        self._approval_decision = approved
        self._approval_event.set()

    def _make_user_content(self) -> types.Content:
        parts = [types.Part.from_text(text=self.user_text)]
        if self.copied_snippet:
            parts.append(types.Part.from_text(text=f"Copied text:\n{self.copied_snippet}"))
        if self.image_path:
            image_path = Path(self.image_path)
            mime_type, _ = mimetypes.guess_type(image_path.name)
            if not mime_type or not mime_type.startswith("image/"):
                raise ValueError(f"Unsupported image type: {image_path.suffix or 'unknown'}")
            parts.append(
                types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type)
            )
        return types.Content(role="user", parts=parts)

    def _tool_declarations(self) -> list[types.FunctionDeclaration]:
        declarations = []
        for name, schema in TOOL_SCHEMAS.items():
            if name in self.disabled_tools:
                continue
            declarations.append(
                types.FunctionDeclaration(
                    name=name,
                    description=TOOL_METADATA[name]["why"],
                    parameters_json_schema=schema,
                )
            )
        return declarations

    def _run_tool(self, name: str, args: dict) -> dict:
        proposal = validate_and_describe_tool_call(name, args, self.disabled_tools)
        if not proposal["allowed"]:
            self.tool_executed_log.emit(f"Blocked {name}: {proposal['error']}")
            return {"status": "blocked", "error": proposal["error"]}

        if proposal["mode"] == "requires_confirmation":
            self._approval_decision = False
            self._approval_event.clear()
            self.tool_approval_requested.emit(proposal)
            if not self._approval_event.wait(timeout=300):
                self.tool_executed_log.emit(f"Timed out waiting for approval: {name}")
                return {"status": "denied", "error": "Tool approval timed out."}
            if not self._approval_decision:
                self.tool_executed_log.emit(f"Denied {name}.")
                return {"status": "denied", "error": "The user denied this tool action."}

        result = execute_allowlisted_tool(name, args, self.disabled_tools)
        self.tool_executed_log.emit(f"{name}: {result}")
        return result

    def run(self) -> None:
        load_dotenv(get_base_dir() / ".env")
        if not os.environ.get("GEMINI_API_KEY"):
            self.error_occurred.emit("GEMINI_API_KEY is missing. Add it to the project .env file.")
            return

        client = None
        try:
            client = genai.Client()
            contents = self.history + [self._make_user_content()]
            model = get_gemini_model()
            declarations = self._tool_declarations() if self.tools_enabled else []
            config = types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=declarations)] if declarations else None,
                system_instruction=(
                    "Respond in clear, polished, professional English. Use a respectful, "
                    "supportive tone, explain ideas in an organized way, and adapt the detail "
                    "to the user's question. Avoid slang and overly casual phrasing."
                ),
            )

            for _ in range(10):
                self.status_update.emit("Connecting to Gemini...")
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                candidate = response.candidates[0] if response.candidates else None
                model_content = candidate.content if candidate else None
                if model_content:
                    contents.append(model_content)

                function_calls = [
                    part.function_call
                    for part in (model_content.parts if model_content else [])
                    if part.function_call is not None
                ]
                if not function_calls:
                    text = response.text
                    if not text:
                        raise RuntimeError("Gemini returned an empty response.")
                    self.response_ready.emit(text, model_content)
                    return

                function_responses = []
                for function_call in function_calls:
                    self.status_update.emit(f"Running {function_call.name}...")
                    result = self._run_tool(
                        function_call.name or "",
                        dict(function_call.args or {}),
                    )
                    function_responses.append(
                        types.Part.from_function_response(
                            name=function_call.name or "",
                            response=result,
                        )
                    )
                contents.append(types.Content(role="user", parts=function_responses))

            raise RuntimeError("Gemini exceeded the maximum number of tool-call rounds.")
        except Exception as exc:
            self.error_occurred.emit(f"Gemini request failed: {exc}")
        finally:
            if client is not None:
                client.close()
