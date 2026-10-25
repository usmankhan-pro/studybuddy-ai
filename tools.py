import os
import platform
import subprocess
import sys
from pathlib import Path
import psutil

TOOL_MODE_READ_ONLY = "read_only"
TOOL_MODE_CONFIRM = "requires_confirmation"

SAFE_OPEN_EXTENSIONS = {".txt", ".pdf", ".md", ".csv", ".xlsx", ".docx", ".png", ".jpg", ".log"}
SAFE_APP_ALLOWLIST = {"notepad": "notepad.exe", "calc": "calc.exe"}

TOOL_METADATA = {
    "get_system_troubleshooting_info": {
        "mode": TOOL_MODE_READ_ONLY,
        "title": "System & OS Info",
        "why": "Check basic Windows version, Python runtime, CPU load, and available RAM.",
        "effect": "Read-only inspection of system resource metrics.",
    },
    "check_file_exists": {
        "mode": TOOL_MODE_READ_ONLY,
        "title": "Check File Existence",
        "why": "Verify whether a specific file path exists and check its size.",
        "effect": "Read-only check on the specified file path.",
    },
    "list_approved_folder": {
        "mode": TOOL_MODE_CONFIRM,
        "title": "List Folder Contents",
        "why": "View file names inside a directory to help troubleshoot missing or misplaced files.",
        "effect": "Reads up to 50 file/folder names in the target directory after your confirmation.",
    },
    "run_predefined_diagnostic": {
        "mode": TOOL_MODE_READ_ONLY,
        "title": "Run Predefined Diagnostic",
        "why": "Run a safe, built-in check on disk space, network DNS resolution, or environment variables.",
        "effect": "Executes a strictly predefined read-only Python check.",
    },
    "open_approved_target": {
        "mode": TOOL_MODE_CONFIRM,
        "title": "Open File or Built-in App",
        "why": "Open a safe document or built-in Windows utility (Notepad/Calculator) for you.",
        "effect": "Launches the default Windows viewer for the approved file or app.",
    },
}

def get_system_troubleshooting_info() -> dict:
    vm = psutil.virtual_memory()
    return {
        "status": "ok",
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python_version": platform.python_version(),
        "cpu_usage_percent": psutil.cpu_percent(interval=0.2),
        "ram_total_gb": round(vm.total / (1024**3), 2),
        "ram_available_gb": round(vm.available / (1024**3), 2),
        "ram_percent_used": vm.percent,
    }

def check_file_exists(file_path: str) -> dict:
    if not file_path or not isinstance(file_path, str):
        return {"status": "error", "error": "A valid non-empty file_path string is required."}
    if ".." in Path(file_path).parts:
        return {"status": "error", "error": "Relative parent traversal ('..') is not permitted."}
    try:
        p = Path(file_path).expanduser().resolve()
        exists = p.exists()
        info = {
            "status": "ok",
            "resolved_path": str(p),
            "exists": exists,
            "is_file": p.is_file() if exists else False,
            "is_dir": p.is_dir() if exists else False,
        }
        if exists and p.is_file():
            info["size_bytes"] = p.stat().st_size
        return info
    except Exception as e:
        return {"status": "error", "error": f"Could not inspect path: {e}"}

def list_approved_folder(folder_path: str) -> dict:
    if not folder_path or not isinstance(folder_path, str):
        return {"status": "error", "error": "A valid folder_path string is required."}
    if ".." in Path(folder_path).parts:
        return {"status": "error", "error": "Relative parent traversal ('..') is not permitted."}
    try:
        p = Path(folder_path).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            return {"status": "error", "error": f"Path is not a valid directory: {p}"}
        items = []
        for idx, entry in enumerate(sorted(p.iterdir(), key=lambda x: x.name.lower())):
            if idx >= 50:
                break
            items.append({"name": entry.name, "type": "dir" if entry.is_dir() else "file"})
        return {"status": "ok", "folder": str(p), "returned_count": len(items), "items": items}
    except PermissionError:
        return {"status": "error", "error": "Permission denied reading folder."}
    except Exception as e:
        return {"status": "error", "error": f"Error listing folder: {e}"}

def run_predefined_diagnostic(check_name: str) -> dict:
    allowed = {"disk_space", "env_check", "localhost_net"}
    if check_name not in allowed:
        return {"status": "error", "error": f"Invalid check_name '{check_name}'."}
    try:
        if check_name == "disk_space":
            usage = psutil.disk_usage(os.path.abspath(os.sep))
            return {
                "status": "ok",
                "check": "disk_space",
                "drive": os.path.abspath(os.sep),
                "total_gb": round(usage.total / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent_used": usage.percent,
            }
        elif check_name == "env_check":
            return {
                "status": "ok",
                "check": "env_check",
                "gemini_key_configured": bool(os.environ.get("GEMINI_API_KEY")),
                "executable": sys.executable,
            }
        elif check_name == "localhost_net":
            import socket
            return {"status": "ok", "check": "localhost_net", "localhost_resolved_ip": socket.gethostbyname("localhost")}
    except Exception as e:
        return {"status": "error", "error": f"Diagnostic failed: {e}"}

def open_approved_target(target: str) -> dict:
    if not target or not isinstance(target, str):
        return {"status": "error", "error": "Target must be a non-empty string."}
    cleaned = target.strip().lower()
    if cleaned in SAFE_APP_ALLOWLIST:
        exe = SAFE_APP_ALLOWLIST[cleaned]
        subprocess.Popen([exe])
        return {"status": "ok", "opened_application": exe}
    if ".." in Path(target).parts:
        return {"status": "error", "error": "Relative parent traversal ('..') is not permitted."}
    try:
        p = Path(target).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return {"status": "error", "error": f"File not found: {p}"}
        if p.suffix.lower() not in SAFE_OPEN_EXTENSIONS:
            return {"status": "error", "error": f"Extension '{p.suffix}' blocked for safety."}
        if sys.platform == "win32":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return {"status": "ok", "opened_file": str(p)}
    except Exception as e:
        return {"status": "error", "error": f"Could not open file: {e}"}

ALLOWLISTED_TOOLS = {
    "get_system_troubleshooting_info": get_system_troubleshooting_info,
    "check_file_exists": check_file_exists,
    "list_approved_folder": list_approved_folder,
    "run_predefined_diagnostic": run_predefined_diagnostic,
    "open_approved_target": open_approved_target,
}

def validate_and_describe_tool_call(name: str, args: dict, disabled_tools: list[str] | None = None) -> dict:
    disabled = set(disabled_tools or [])
    if name not in ALLOWLISTED_TOOLS:
        return {"allowed": False, "error": f"Tool '{name}' is not on the allowlist."}
    if name in disabled:
        return {"allowed": False, "error": f"Tool '{name}' is currently disabled in Settings."}
    if not isinstance(args, dict):
        return {"allowed": False, "error": "Tool arguments must be a dictionary."}
    meta = TOOL_METADATA[name]
    return {
        "allowed": True,
        "name": name,
        "args": args,
        "mode": meta["mode"],
        "title": meta["title"],
        "why": meta["why"],
        "effect": meta["effect"],
    }

def execute_allowlisted_tool(name: str, args: dict, disabled_tools: list[str] | None = None) -> dict:
    check = validate_and_describe_tool_call(name, args, disabled_tools)
    if not check["allowed"]:
        return {"status": "blocked", "error": check["error"]}
    try:
        return ALLOWLISTED_TOOLS[name](**args)
    except Exception as e:
        return {"status": "error", "error": f"Tool error: {e}"}
