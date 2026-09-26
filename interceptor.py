"""
Shunt Interceptor
Detects and blocks large file reads, delegating to worker models
Smart routing: skips shunt for small files or files that don't benefit
"""

import logging
import os
import re
import subprocess
from typing import Optional, Tuple, List

logger = logging.getLogger("shunt_interceptor")


class ShuntInterceptor:
    """Intercepts file read commands and delegates large files to worker models"""

    FILE_READ_PATTERNS = [
        (r'\bcat\s+([^\s|&;]+)', 'cat', False),
        (r'\bhead\s+(?:-(\d+)|(\d+))\s+([^\s|&;]+)', 'head', True),
        (r'\btail\s+(?:-(\d+)|(\d+))\s+([^\s|&;]+)', 'tail', True),
        (r'\bhead\s+([^\s|&;]+)', 'head', False),
        (r'\btail\s+([^\s|&;]+)', 'tail', False),
        (r'\bless\s+([^\s|&;]+)', 'less', False),
        (r'\bmore\s+([^\s|&;]+)', 'more', False),
        (r'\bsed\s+.*<\s*([^\s|&;]+)', 'sed', False),
        (r'\bawk\s+.*<\s*([^\s|&;]+)', 'awk', False),
        (r'\bview\s+([^\s|&;]+)', 'view', False),
        (r'\bnvim\s+([^\s|&;]+)', 'nvim', False),
        (r'\bvi\s+([^\s|&;]+)', 'vi', False),
    ]

    DEFAULT_HEAD_TAIL_LINES = 10

    SKIP_PATTERNS = [
        r'.*Visitor\.java$',
        r'.*Parser\.java$',
        r'.*Lexer\.java$',
        r'.*Token\.java$',
        r'.*Test\.java$',
        r'.*Test\.ts$',
        r'.*Test\.js$',
        r'.*\.min\.js$',
        r'.*\.min\.css$',
        r'.*\.map$',
        r'.*\.json$',
        r'.*\.yaml$',
        r'.*\.yml$',
        r'.*\.xml$',
    ]

    def __init__(
        self,
        threshold: int = 350,
        base_dir: str = "/testbed",
        skip_patterns: Optional[List[str]] = None
    ):
        self.threshold = threshold
        self.base_dir = base_dir
        self.skip_patterns = self.SKIP_PATTERNS + (skip_patterns or [])
        self._stats = {
            "files_checked": 0,
            "files_intercepted": 0,
            "files_skipped_small": 0,
            "files_skipped_pattern": 0,
            "files_skipped_targeted_read": 0,
            "files_delegated": 0,
            "files_read_direct": 0
        }

    def check_command(self, command: str) -> Tuple[bool, Optional[str], Optional[str]]:
        self._stats["files_checked"] += 1

        if '|' in command:
            return False, None, None
        if '>' in command or '>>' in command:
            return False, None, None

        for pattern, cmd_type, has_numeric_arg in self.FILE_READ_PATTERNS:
            match = re.search(pattern, command)
            if not match:
                continue

            if has_numeric_arg:
                num_str = match.group(1) or match.group(2)
                file_path = match.group(3)
                requested_lines = int(num_str) if num_str else self.DEFAULT_HEAD_TAIL_LINES
            else:
                file_path = match.group(1)
                requested_lines = None
                if cmd_type in ("head", "tail"):
                    requested_lines = self.DEFAULT_HEAD_TAIL_LINES

            if not os.path.isabs(file_path):
                file_path = os.path.join(self.base_dir, file_path)

            if not os.path.exists(file_path):
                return False, None, None

            if requested_lines is not None and requested_lines <= self.threshold:
                self._stats["files_skipped_targeted_read"] += 1
                logger.debug(f"Skipping {file_path}: targeted read of {requested_lines} lines")
                return False, None, None

            should_skip, reason = self._should_skip(file_path)
            if should_skip:
                logger.debug(f"Skipping {file_path}: {reason}")
                return False, None, None

            lines = self._get_file_lines(file_path)
            if lines is not None and lines > self.threshold:
                self._stats["files_intercepted"] += 1
                logger.info(f"Intercepted {cmd_type} on {file_path} ({lines} lines > {self.threshold})")
                return True, file_path, cmd_type
            elif lines is not None:
                self._stats["files_skipped_small"] += 1

        return False, None, None

    def _should_skip(self, file_path: str) -> Tuple[bool, str]:
        for pattern in self.skip_patterns:
            if re.match(pattern, file_path, re.IGNORECASE):
                self._stats["files_skipped_pattern"] += 1
                return True, f"Matches skip pattern: {pattern}"
        return False, ""

    def _get_file_lines(self, file_path: str) -> Optional[int]:
        try:
            result = subprocess.run(
                ["wc", "-l", file_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return int(result.stdout.split()[0])
            with open(file_path, 'r', errors='ignore') as f:
                return sum(1 for _ in f)
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            return None

    def get_file_content(self, file_path: str) -> Optional[str]:
        try:
            with open(file_path, 'r', errors='ignore') as f:
                return f.read()
        except (FileNotFoundError, PermissionError):
            return None

    def get_stats(self) -> dict:
        stats = self._stats.copy()
        total = stats["files_checked"]
        if total > 0:
            stats["interception_rate"] = stats["files_intercepted"] / total * 100
            stats["skip_rate"] = (
                stats["files_skipped_small"]
                + stats["files_skipped_pattern"]
                + stats["files_skipped_targeted_read"]
            ) / total * 100
        return stats

    def reset_stats(self):
        self._stats = {
            "files_checked": 0,
            "files_intercepted": 0,
            "files_skipped_small": 0,
            "files_skipped_pattern": 0,
            "files_skipped_targeted_read": 0,
            "files_delegated": 0,
            "files_read_direct": 0
        }


class ShuntResult:
    """Represents the result of a shunt interception"""
    
    def __init__(
        self,
        intercepted: bool,
        file_path: Optional[str] = None,
        command_type: Optional[str] = None,
        summary: Optional[str] = None,
        tokens: Optional[dict] = None,
        cost: float = 0.0,
        error: Optional[str] = None
    ):
        self.intercepted = intercepted
        self.file_path = file_path
        self.command_type = command_type
        self.summary = summary
        self.tokens = tokens or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.cost = cost
        self.error = error
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "intercepted": self.intercepted,
            "file_path": self.file_path,
            "command_type": self.command_type,
            "summary": self.summary,
            "tokens": self.tokens,
            "cost": self.cost,
            "error": self.error
        }
    
    def __repr__(self) -> str:
        if self.intercepted:
            return f"ShuntResult(intercepted=True, file={self.file_path}, type={self.command_type})"
        return "ShuntResult(intercepted=False)"
