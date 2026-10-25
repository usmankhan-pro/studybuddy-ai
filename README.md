# StudyBuddy AI

A floating Windows desktop study and troubleshooting assistant built with Python, PySide6, and the Google Gemini API.

StudyBuddy AI provides a resizable chat panel alongside your work, with a floating mascot, optional screenshot and clipboard context, and user-approved local tools.

## Features

- Floating mascot, system tray controls, and configurable Windows shortcut.
- Resizable chat panel with left/right screen docking and a charcoal dark theme.
- Gemini-powered chat with Markdown formatting and local SQLite conversation history.
- Screenshot and clipboard attachments staged for review before sending.
- Optional allowlisted local tools, with confirmation required before opening files or applications.

## Requirements

- Windows
- Python 3.10 or later
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)

## Setup

Open PowerShell in the project folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and replace the placeholder with your API key:

```ini
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.5-flash
```

Keep `.env` private. It is excluded by `.gitignore`; never put your API key in Python source, the README, screenshots, or public issue reports.

Launch the app:

```powershell
python main.py
```

## Build a Windows executable

```powershell
python generate_icon.py
pyinstaller --clean StudyBuddyAI.spec
```

Configure your API key locally for the packaged app when needed. Never commit or upload a `.env` file or a build containing embedded credentials.

## Publishing safely

Before pushing changes, check `git status --short` and confirm `.env`, virtual environments, local databases, and build output are not staged. `.env.example` should contain placeholders only.
