# OpsPilot standalone publisher: automatically uses the folder containing this script.
# No machine-specific paths, no destructive Git operations, no token collection.
$ErrorActionPreference = 'Stop'
$Repository = 'chinmaygit-lab/OpsPilot'
$ExpectedOwner = 'chinmaygit-lab'

function Check-Last([string]$Name) {
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE). Nothing further will be published." }
}

try {
    Set-Location -LiteralPath $PSScriptRoot
    if (-not (Test-Path -LiteralPath '.\pyproject.toml') -or
        -not (Test-Path -LiteralPath '.\opspilot\api.py')) {
        throw 'The ZIP was not extracted completely. Re-extract it and run this launcher from inside the project.'
    }
    Write-Host '=== OpsPilot: install and verify ===' -ForegroundColor Cyan
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Python 3.11+ was not found. Install Python and reopen the terminal.'
    }
    & python -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"; print(sys.version)'
    Check-Last 'Python version check'
    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe')) {
        & python -m venv .venv
        Check-Last 'Virtual environment creation'
    }
    $Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    & $Python -m pip install -e '.[dev]'
    Check-Last 'Dependency installation'
    & $Python -c 'import websockets; print(websockets.__version__)'
    Check-Last 'WebSocket support check'
    & $Python -m pytest -q
    Check-Last 'Automated tests'

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git is missing. Install Git for Windows and reopen the terminal.'
    }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw 'GitHub CLI is missing. Run: winget install --id GitHub.cli -e, then reopen the terminal.'
    }
    Write-Host '=== GitHub authentication ===' -ForegroundColor Cyan
    # cmd returns the status without raising a PowerShell error for an unauthenticated gh.
    & cmd.exe /d /c 'gh auth status -h github.com >nul 2>nul'
    if ($LASTEXITCODE -ne 0) {
        & gh auth login -h github.com -p https -w
        Check-Last 'GitHub browser login'
    }
    & gh auth setup-git
    Check-Last 'GitHub Git credentials setup'
    $Account = (& gh api user --jq .login).Trim()
    Check-Last 'GitHub account verification'
    if ($Account -ne $ExpectedOwner) {
        throw "GitHub is logged into '$Account', but target owner is '$ExpectedOwner'. No changes published. Log into the correct account first."
    }

    Write-Host '=== Prepare GitHub source (no local database or secrets) ===' -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath '.\.git')) {
        & git init -b main
        Check-Last 'git init'
    }
    # Stage a strict allowlist from this known ZIP, never arbitrary files in data/.
    $Allowed = @(
        '.gitignore', '.github', '.agents', 'Dockerfile', 'LICENSE',
        'README.md', 'RELEASE_MANIFEST.json', 'VERIFICATION.md',
        'compose.yaml', 'docs', 'opspilot', 'pyproject.toml',
        'samples', 'scripts', 'tests', 'PUBLISH_TO_GITHUB.cmd',
        'PUBLISH_TO_GITHUB.ps1', 'PUBLISHING_README.txt'
    )
    & git add -- $Allowed
    Check-Last 'Git staging'
    $StagedPaths = @(& git diff --cached --name-only)
    Check-Last 'Git staged-file inspection'
    $Sensitive = @($StagedPaths | Where-Object {
        $_ -match '(^|/)(data/|\.venv/|\.env($|\.)|.*\.(db|sqlite|sqlite3|pem|p12|key|bak)$)'
    })
    if ($Sensitive.Count -gt 0) {
        throw ('Stopped: sensitive files staged: ' + ($Sensitive -join ', '))
    }
    & git diff --cached --check
    Check-Last 'Whitespace safety check'
    Write-Host ('Files staged: ' + $StagedPaths.Count)
    if ($StagedPaths.Count -gt 0) {
        $Name = & git config user.name
        if (-not $Name) {
            & git config user.name $Account
            Check-Last 'Local Git author name'
        }
        $Email = & git config user.email
        if (-not $Email) {
            $UserId = (& gh api user --jq .id).Trim()
            Check-Last 'GitHub user ID'
            & git config user.email "$UserId+$Account@users.noreply.github.com"
            Check-Last 'Local Git author email'
        }
        & git commit -m 'feat: publish OpsPilot agent platform with WebSocket fixes'
        Check-Last 'Git commit'
    }

    Write-Host '=== Publish PUBLIC repository ===' -ForegroundColor Cyan
    $CurrentBranch = ((& git symbolic-ref HEAD) -replace "^refs/heads/", "").Trim()
    Check-Last 'Current Git branch'
    if (-not $CurrentBranch) { throw 'No Git branch to push.' }
    $Remotes = @(& git remote)
    Check-Last 'Read Git remotes'
    if ($Remotes -contains 'origin') {
        $Origin = (& git remote get-url origin).Trim()
        Check-Last 'Read Git origin'
        if ($Origin -notmatch '(^|[:/])chinmaygit-lab/OpsPilot(\.git)?$') {
            throw "Existing remote '$Origin' is different; refusing to overwrite it."
        }
        & git push -u origin $CurrentBranch
        Check-Last 'Push existing origin'
    } else {
        & cmd.exe /d /c 'gh repo view chinmaygit-lab/OpsPilot --json name --jq .name >nul 2>nul'
        $Exists = ($LASTEXITCODE -eq 0)
        if ($Exists) {
            & git remote add origin "https://github.com/$Repository.git"
            Check-Last 'Set GitHub origin'
            # Never force-push over preexisting GitHub history.
            & git push -u origin $CurrentBranch
            Check-Last 'Push to existing GitHub repository'
        } else {
            & gh repo create $Repository --public --source . --remote origin --push `
              --description 'Multi-tenant agent operations platform with live analytics, connectors, and human-approved tools'
            Check-Last 'Create and push public GitHub repository'
        }
    }
    Write-Host "SUCCESS: https://github.com/$Repository" -ForegroundColor Green
    Write-Host 'GitHub hosts the source code; the dashboard remains local.'
} catch {
    Write-Host ('STOPPED: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
