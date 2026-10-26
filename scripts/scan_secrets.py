"""Scan an allowlisted source snapshot without exposing local secrets to the scanner.

The official Gitleaks image receives only explicitly selected text sources, in a
read-only mount with networking disabled. Staging is retained under ignored
.artifacts for inspection; no user files or directories are deleted.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = (
    "ghcr.io/gitleaks/gitleaks:v8.30.0"
    "@sha256:691af3c7c5a48b16f187ce3446d5f194838f91238f27270ed36eef6359a574d9"
)
EXCLUDED = {
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "test-results",
    "playwright-report",
}
SUFFIXES = {
    ".py",
    ".sh",
    ".conf",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".css",
    ".html",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".lock",
    ".Dockerfile",
}


def stage_sources():
    """Copy source text only; never recurse into .env, dependencies, volumes or Git."""
    parent = ROOT / ".artifacts"
    parent.mkdir(exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="source-scan-", dir=parent)).resolve()
    assert target.is_relative_to(parent.resolve())
    paths = [
        ROOT / name
        for name in [
            "README.md",
            "AGENTS.md",
            "Makefile",
            "compose.yaml",
            ".env.example",
            ".gitignore",
            ".gitattributes",
            ".dockerignore",
            ".gitleaks.toml",
            "SAMSEL_Industrial_Intelligence_CODEX_MASTER_IMPLEMENTATION.md",
        ]
    ]
    for directory in ["apps", "scripts", "packages", "infra", "docs", ".github", "simulator"]:
        for path in (ROOT / directory).rglob("*"):
            relative = path.relative_to(ROOT)
            if not set(relative.parts) & EXCLUDED and path.is_file() and path.suffix in SUFFIXES:
                paths.append(path)
    for source in paths:
        if source.is_symlink():
            raise SystemExit("Refusing source symlink in secret scan.")
        destination = target / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    print(f"Staged {len(paths)} source files; local credentials excluded.")
    return target


def main():
    """Run the fixed scanner with no network, privileges, or writable source mount."""
    target = stage_sources()
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "-v",
            f"{target}:/repo:ro",
            IMAGE,
            "dir",
            "/repo",
            "--config",
            "/repo/.gitleaks.toml",
            "--redact",
            "--no-banner",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
