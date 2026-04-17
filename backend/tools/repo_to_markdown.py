#!/usr/bin/env python3
"""
repo_to_markdown.py

Generate a single Markdown file from one or more project directories.
The Markdown includes:
1. Project/folder structure
2. File contents (for code/text files)
3. Nice formatting for LLM context ingestion

Example:
    python repo_to_markdown.py ./backend ./frontend -o project_context.md

Optional:
    python repo_to_markdown.py ./src ./docs -o context.md --max-file-size-kb 512
"""

from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path
from typing import Iterable, List, Set, Tuple
from datetime import datetime


# -------------------------------
# Default configuration
# -------------------------------

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".output",
    "coverage",
    ".idea",
    ".vscode",
    "target",
    "bin",
    "obj",
    ".gradle",
    ".DS_Store",
}

DEFAULT_IGNORE_FILES = {
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dll",
    "*.exe",
    "*.class",
    "*.jar",
    "*.war",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.7z",
    "*.rar",
    "*.pdf",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.bmp",
    "*.ico",
    "*.webp",
    "*.mp4",
    "*.mp3",
    "*.wav",
    "*.mov",
    "*.avi",
    "*.mkv",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.otf",
    "*.eot",
    "*.lock",
}

# Common code/text extensions that are usually useful for LLM context
DEFAULT_INCLUDE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".kt", ".kts", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh",
    ".cs",
    ".go",
    ".rs",
    ".php",
    ".rb",
    ".swift",
    ".dart",
    ".lua",
    ".sh", ".bash", ".zsh", ".ps1", ".bat",
    ".sql",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".xml",
    ".json", ".jsonc",
    ".yaml", ".yml",
    ".toml",
    ".ini", ".cfg", ".conf",
    ".env", ".env.example",
    ".md", ".txt", ".rst",
    ".dockerfile",  # some repos use extensionless Dockerfile too
    ".graphql", ".gql",
    ".proto",
}

# Some common extensionless filenames useful for context
DEFAULT_INCLUDE_FILENAMES = {
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    "README",
    "README.md",
    "README.txt",
    "LICENSE",
    "Procfile",
    ".gitignore",
    ".dockerignore",
    ".editorconfig",
    ".prettierrc",
    ".eslintrc",
    ".npmrc",
    ".nvmrc",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "Pipfile.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "next.config.js",
    "next.config.ts",
    "webpack.config.js",
    "webpack.config.ts",
    "jest.config.js",
    "jest.config.ts",
}


# -------------------------------
# Utility helpers
# -------------------------------

def normalize_extensions(exts: Iterable[str]) -> Set[str]:
    """
    Normalize extensions to start with a dot where applicable.
    Example: 'py' -> '.py'
    """
    normalized = set()
    for ext in exts:
        ext = ext.strip()
        if not ext:
            continue
        if ext.startswith("."):
            normalized.add(ext.lower())
        else:
            normalized.add(f".{ext.lower()}")
    return normalized


def is_binary_file(path: Path, sample_size: int = 4096) -> bool:
    """
    Basic binary detection:
    - If file contains NULL bytes, treat as binary.
    - If decoding as UTF-8 fails badly, treat as binary.
    """
    try:
        with path.open("rb") as f:
            chunk = f.read(sample_size)
        if b"\x00" in chunk:
            return True
        try:
            chunk.decode("utf-8")
            return False
        except UnicodeDecodeError:
            # Could still be text in other encoding, but for LLM context
            # we keep the logic simple and safe.
            return True
    except Exception:
        return True


def should_ignore_file(path: Path, ignore_patterns: Set[str]) -> bool:
    """
    Return True if file name matches any ignored glob pattern.
    """
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(path.name, pattern):
            return True
    return False


def should_include_file(
    path: Path,
    include_extensions: Set[str],
    include_filenames: Set[str],
    ignore_patterns: Set[str],
    max_file_size_kb: int
) -> Tuple[bool, str]:
    """
    Decide whether to include a file in the output.

    Returns:
        (include: bool, reason: str)
    """
    if not path.is_file():
        return False, "Not a file"

    if should_ignore_file(path, ignore_patterns):
        return False, "Ignored by file pattern"

    try:
        size_kb = path.stat().st_size / 1024
        if max_file_size_kb > 0 and size_kb > max_file_size_kb:
            return False, f"Skipped (>{max_file_size_kb} KB)"
    except Exception:
        return False, "Could not read file size"

    if is_binary_file(path):
        return False, "Binary file"

    # Include by explicit filename
    if path.name in include_filenames:
        return True, "Included by filename"

    # Include by extension
    suffixes = path.suffixes
    if suffixes:
        combined_suffix = "".join(suffixes).lower()
        if combined_suffix in include_extensions:
            return True, "Included by combined suffix"

        if path.suffix.lower() in include_extensions:
            return True, "Included by suffix"

    # Special-case extensionless files that are often useful
    if not path.suffix and path.name in include_filenames:
        return True, "Included by extensionless filename"

    return False, "Not a selected code/text file"


def get_markdown_language(path: Path) -> str:
    """
    Map file extension/name to Markdown code fence language.
    """
    name = path.name.lower()
    suffix = path.suffix.lower()

    filename_map = {
        "dockerfile": "dockerfile",
        "makefile": "makefile",
    }
    if name in filename_map:
        return filename_map[name]

    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".java": "java",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".scala": "scala",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
        ".hh": "cpp",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".php": "php",
        ".rb": "ruby",
        ".swift": "swift",
        ".dart": "dart",
        ".lua": "lua",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        ".ps1": "powershell",
        ".bat": "bat",
        ".sql": "sql",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".scss": "scss",
        ".sass": "sass",
        ".less": "less",
        ".xml": "xml",
        ".json": "json",
        ".jsonc": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".ini": "ini",
        ".cfg": "ini",
        ".conf": "conf",
        ".env": "dotenv",
        ".md": "markdown",
        ".txt": "text",
        ".rst": "rst",
        ".graphql": "graphql",
        ".gql": "graphql",
        ".proto": "proto",
    }
    return ext_map.get(suffix, "")


def safe_read_text(path: Path) -> str:
    """
    Read text file safely using UTF-8 first, then fallback.
    """
    encodings = ["utf-8", "utf-8-sig", "latin-1"]
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return f"[ERROR READING FILE: {e}]"
    return "[ERROR: Unable to decode file as text]"


# -------------------------------
# Tree generation
# -------------------------------

def build_tree(root: Path, ignore_dirs: Set[str], ignore_file_patterns: Set[str], prefix: str = "") -> List[str]:
    """
    Build a simple ASCII tree for a directory.
    """
    lines = []

    try:
        entries = sorted(
            list(root.iterdir()),
            key=lambda p: (not p.is_dir(), p.name.lower())
        )
    except PermissionError:
        return [f"{prefix}[Permission Denied]"]
    except Exception as e:
        return [f"{prefix}[Error: {e}]"]

    # Filter ignored directories and ignored files
    filtered_entries = []
    for entry in entries:
        if entry.is_dir() and entry.name in ignore_dirs:
            continue
        if entry.is_file() and should_ignore_file(entry, ignore_file_patterns):
            continue
        filtered_entries.append(entry)

    for index, entry in enumerate(filtered_entries):
        is_last = index == len(filtered_entries) - 1
        branch = "└── " if is_last else "├── "
        lines.append(f"{prefix}{branch}{entry.name}")

        if entry.is_dir():
            extension = "    " if is_last else "│   "
            lines.extend(build_tree(entry, ignore_dirs, ignore_file_patterns, prefix + extension))

    return lines


# -------------------------------
# File collection
# -------------------------------

def collect_files(
    root: Path,
    ignore_dirs: Set[str],
    ignore_file_patterns: Set[str],
    include_extensions: Set[str],
    include_filenames: Set[str],
    max_file_size_kb: int
) -> List[Path]:
    """
    Recursively collect files that should be included.
    """
    collected: List[Path] = []

    for current_root, dirs, files in os.walk(root):
        current_root_path = Path(current_root)

        # Modify dirs in-place so os.walk skips ignored dirs
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for file_name in sorted(files):
            file_path = current_root_path / file_name
            include, _reason = should_include_file(
                file_path,
                include_extensions=include_extensions,
                include_filenames=include_filenames,
                ignore_patterns=ignore_file_patterns,
                max_file_size_kb=max_file_size_kb,
            )
            if include:
                collected.append(file_path)

    collected.sort(key=lambda p: str(p).lower())
    return collected


# -------------------------------
# Markdown generation
# -------------------------------

def generate_markdown(
    roots: List[Path],
    ignore_dirs: Set[str],
    ignore_file_patterns: Set[str],
    include_extensions: Set[str],
    include_filenames: Set[str],
    max_file_size_kb: int,
) -> str:
    """
    Build the final markdown content.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    parts: List[str] = []
    parts.append("# Project Context Export")
    parts.append("")
    parts.append(f"Generated on: `{now}`")
    parts.append("")
    parts.append("## Included Roots")
    parts.append("")
    for root in roots:
        parts.append(f"- `{root.resolve()}`")
    parts.append("")

    # Folder structures
    parts.append("## Folder Structure")
    parts.append("")
    for root in roots:
        parts.append(f"### Root: `{root.name}`")
        parts.append("")
        parts.append("```text")
        parts.append(root.name)
        parts.extend(build_tree(root, ignore_dirs, ignore_file_patterns))
        parts.append("```")
        parts.append("")

    # File contents
    parts.append("## File Contents")
    parts.append("")
    for root in roots:
        files = collect_files(
            root=root,
            ignore_dirs=ignore_dirs,
            ignore_file_patterns=ignore_file_patterns,
            include_extensions=include_extensions,
            include_filenames=include_filenames,
            max_file_size_kb=max_file_size_kb,
        )

        parts.append(f"### Files from `{root.name}`")
        parts.append("")

        if not files:
            parts.append("_No matching code/text files found._")
            parts.append("")
            continue

        for file_path in files:
            relative_path = file_path.relative_to(root)
            language = get_markdown_language(file_path)
            content = safe_read_text(file_path)

            parts.append(f"#### `{root.name}/{relative_path.as_posix()}`")
            parts.append("")
            parts.append(f"**Language hint:** `{language or 'text'}`")
            parts.append("")
            parts.append(f"```{language}")
            parts.append(content.rstrip())
            parts.append("```")
            parts.append("")

    return "\n".join(parts)


# -------------------------------
# CLI
# -------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge multiple project directories into a single LLM-friendly Markdown file."
    )

    parser.add_argument(
        "dirs",
        nargs="+",
        help="One or more directories to scan"
    )

    parser.add_argument(
        "-o",
        "--output",
        default="project_context.md",
        help="Output Markdown file path (default: project_context.md)"
    )

    parser.add_argument(
        "--max-file-size-kb",
        type=int,
        default=512,
        help="Skip files larger than this size in KB (default: 512). Use 0 for no limit."
    )

    parser.add_argument(
        "--ignore-dir",
        action="append",
        default=[],
        help="Additional directory name to ignore. Can be used multiple times."
    )

    parser.add_argument(
        "--ignore-file",
        action="append",
        default=[],
        help="Additional file glob pattern to ignore (example: '*.log'). Can be used multiple times."
    )

    parser.add_argument(
        "--ext",
        action="append",
        default=[],
        help="Additional file extension to include (example: --ext py --ext tsx). Can be used multiple times."
    )

    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden directories/files if they otherwise match filters."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    roots = [Path(d).resolve() for d in args.dirs]

    for root in roots:
        if not root.exists():
            raise FileNotFoundError(f"Directory does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root}")

    ignore_dirs = set(DEFAULT_IGNORE_DIRS)
    ignore_dirs.update(args.ignore_dir)

    ignore_file_patterns = set(DEFAULT_IGNORE_FILES)
    ignore_file_patterns.update(args.ignore_file)

    include_extensions = set(DEFAULT_INCLUDE_EXTENSIONS)
    include_extensions.update(normalize_extensions(args.ext))

    include_filenames = set(DEFAULT_INCLUDE_FILENAMES)

    # If hidden files/dirs are not included, ignore dot-directories except specific useful files.
    if not args.include_hidden:
        # We avoid globally ignoring dot-files here because some are useful,
        # but hidden directories are already mostly covered.
        pass

    markdown = generate_markdown(
        roots=roots,
        ignore_dirs=ignore_dirs,
        ignore_file_patterns=ignore_file_patterns,
        include_extensions=include_extensions,
        include_filenames=include_filenames,
        max_file_size_kb=args.max_file_size_kb,
    )

    output_path = Path(args.output).resolve()
    output_path.write_text(markdown, encoding="utf-8")

    print(f"Markdown context file created successfully: {output_path}")


if __name__ == "__main__":
    main()