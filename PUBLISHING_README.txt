OPSPILOT: ONE-PACKAGE GITHUB PUBLISHING (WINDOWS)

1. Download the all-in-one ZIP into Downloads.
2. Right-click ZIP > Extract All. Open the extracted opspilot_agent_platform folder.
3. Double-click PUBLISH_TO_GITHUB.cmd.
   Or open PowerShell inside that folder and run: .\PUBLISH_TO_GITHUB.cmd
4. If GitHub asks you to log in, follow the browser login steps.
5. Read the SUCCESS link in the console when complete.

NO DIRECTORY PATHS NEED TO BE ENTERED.

What it does:
- Creates a local isolated .venv using your Python 3.11+ installation.
- Installs the missing WebSocket dependency via uvicorn[standard].
- Tests the platform before committing it.
- Publishes source code to https://github.com/chinmaygit-lab/OpsPilot.
- Uses the signed-in GitHub CLI account; refuses a wrong account.
- Excludes .venv, local SQLite databases and secrets from Git.
- Does not publish the running localhost server to the internet.
- Does not use an AI API key or change your account credentials.

Requires: Python 3.11+, Git for Windows, and GitHub CLI (gh).
Install GitHub CLI if missing: winget install --id GitHub.cli -e
After installing tools, reopen your terminal (or Explorer).

This archive is a CLEAN SOURCE COPY. Your old 6 tasks and 5 events live in the
original SQLite database; they are NOT inside this downloadable archive.
Do not delete the old folder if you find it later.

Run locally after setup:
  $env:DEMO_MODE = '1'
  .\.venv\Scripts\python.exe -m uvicorn opspilot.api:app --reload
Open http://127.0.0.1:8000 and use demo-acme-owner.
Local demonstration credentials must never be used for public deployment.
