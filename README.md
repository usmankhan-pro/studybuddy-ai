<<<<<<< HEAD
# studybuddy-ai
A floating Windows desktop AI study and troubleshooting assistant built with Python, PySide6, and the Google Gemini API. Features a draggable robot mascot, modern Gemini-style dark UI, screenshot/clipboard context sharing, and safe allowlisted diagnostic tools.
=======
# StudyBuddy AI

A floating Windows desktop learning assistant built with Python, PySide6, and the Google Gemini API. The resizable chat panel includes a charcoal dark theme, left/right docking, screenshot and clipboard attachments, and optional allowlisted tools.

## Features

- Floating mascot, system tray controls, and configurable Windows shortcut.
- Resizable chat panel with left/right screen docking.
- Gemini-powered chat with Markdown formatting and saved local conversation history.
- Screenshot and clipboard attachments, staged for review before sending.
- Optional allowlisted local tools, with confirmation required for actions that open files or applications.

## Requirements

- Windows
- Python 3.10 or later
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)

## Setup

In PowerShell, from the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and replace the placeholder with your API key. Keep `.env` private; it is excluded by `.gitignore`. Do not paste your key into Python source, README files, screenshots, or public issue reports.

```ini
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.5-flash
```

Run the application:

```powershell
python main.py
```

## Build a Windows executable

```powershell
python generate_icon.py
pyinstaller --clean StudyBuddyAI.spec
```

The generated executable expects its environment configuration beside it. Configure the key locally in the output folder when needed; never commit or upload that `.env` file or a build containing embedded credentials.

## GitHub safety

Before publishing, run `git status --short` and confirm that `.env`, virtual environments, databases, and build output are not staged. The `.env.example` file contains placeholders only and documents the required settings.
>>>>>>> e24354e (Initial commit: StudyBuddy AI desktop assistant)
