<#
.SYNOPSIS
    Installs non-blocking Git hooks (post-commit and post-merge) to keep Graphify code graphs auto-updated.
.DESCRIPTION
    Creates or updates .git/hooks/post-commit and .git/hooks/post-merge to run:
    graphify extract . && graphify cluster-only .
    silently in the background. Also ensures graphify-out/ is added to .gitignore.
.PARAMETER RepoRoot
    Target repository root path. Defaults to current directory.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = $PWD.Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedRoot = Resolve-Path -Path $RepoRoot
$gitDir = Join-Path $resolvedRoot ".git"

if (!(Test-Path $gitDir)) {
    Write-Error "Directory is not a Git repository root: $resolvedRoot"
    exit 1
}

# In worktrees or submodules, .git might be a file pointing to gitdir
$gitItem = Get-Item -Path $gitDir -Force
if ($gitItem -isnot [System.IO.DirectoryInfo]) {
    $gitContent = (Get-Content $gitDir -Raw).Trim()
    if ($gitContent -match "^gitdir:\s*(.+)$") {
        $gitHooksDir = Join-Path (Resolve-Path (Join-Path $resolvedRoot $Matches[1])) "hooks"
    } else {
        $gitHooksDir = Join-Path $gitDir "hooks"
    }
} else {
    $gitHooksDir = Join-Path $gitDir "hooks"
}

if (!(Test-Path $gitHooksDir)) {
    New-Item -ItemType Directory -Path $gitHooksDir -Force | Out-Null
}

$hookMarker = "# --- GRAPHIFY-AUTO-SYNC-HOOK ---"
$hookSnippet = @"

$hookMarker
(
  export PATH="`$HOME/.local/bin:`$PATH"
  if command -v graphify >/dev/null 2>&1; then
    if [ -d "graphify-out" ]; then
      graphify update .
    else
      graphify extract . && graphify cluster-only .
    fi
  fi
) >/dev/null 2>&1 &
"@

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$hookFiles = @("post-commit", "post-merge")

foreach ($hookName in $hookFiles) {
    $hookPath = Join-Path $gitHooksDir $hookName
    if (Test-Path $hookPath) {
        $existing = Get-Content -Path $hookPath -Raw
        if ($existing -notmatch [regex]::Escape($hookMarker)) {
            $newContent = $existing.TrimEnd() + "`n" + $hookSnippet + "`n"
            # Write with LF encoding and NO BOM for POSIX sh compatibility in Git on Windows
            [System.IO.File]::WriteAllText($hookPath, $newContent.Replace("`r`n", "`n"), $utf8NoBom)
            Write-Host "Updated hook: $hookPath" -ForegroundColor Green
        } else {
            # Rewrite without BOM to ensure valid executable format
            $cleanContent = $existing.Replace("`r`n", "`n")
            [System.IO.File]::WriteAllText($hookPath, $cleanContent, $utf8NoBom)
            Write-Host "Hook already configured (ensured no-BOM): $hookPath" -ForegroundColor Cyan
        }
    } else {
        $newContent = "#!/bin/sh`n" + $hookSnippet.TrimStart() + "`n"
        [System.IO.File]::WriteAllText($hookPath, $newContent.Replace("`r`n", "`n"), $utf8NoBom)
        Write-Host "Created hook: $hookPath" -ForegroundColor Green
    }
}

# Update .gitignore to avoid committing graphify-out
$gitignorePath = Join-Path $resolvedRoot ".gitignore"
$ignoreEntry = "graphify-out/"

if (Test-Path $gitignorePath) {
    $gitignoreContent = Get-Content -Path $gitignorePath -Raw
    if ($gitignoreContent -notmatch "(?m)^/?graphify-out/?$") {
        $updatedGitignore = $gitignoreContent.TrimEnd() + "`n$ignoreEntry`n"
        [System.IO.File]::WriteAllText($gitignorePath, $updatedGitignore, [System.Text.Encoding]::UTF8)
        Write-Host "Added $ignoreEntry to .gitignore" -ForegroundColor Green
    } else {
        Write-Host "$ignoreEntry is already in .gitignore" -ForegroundColor Cyan
    }
} else {
    [System.IO.File]::WriteAllText($gitignorePath, "$ignoreEntry`n", [System.Text.Encoding]::UTF8)
    Write-Host "Created .gitignore with $ignoreEntry" -ForegroundColor Green
}

Write-Host "Graphify Git automation successfully installed for: $resolvedRoot" -ForegroundColor Green
