"""
Shunt Interceptor
Detects and blocks large file reads, delegating to worker models
"""

import logging
import os
import re
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger("shunt_interceptor")


class ShuntInterceptor:
    """Intercepts file read commands and delegates large files to worker models"""
    
    # Patterns that read files
    FILE_READ_PATTERNS = [
        (r'\bcat\s+([^\s|&;]+)', 'cat'),
        (r'\bhead\s+(?:-\d+\s+|\d+\s+)([^\s|&;]+)', 'head'),
        (r'\btail\s+(?:-\d+\s+|\d+\s+)([^\s|&;]+)', 'tail'),
        (r'\bless\s+([^\s|&;]+)', 'less'),
        (r'\bmore\s+([^\s|&;]+)', 'more'),
        (r'\bsed\s+.*<\s*([^\s|&;]+)', 'sed'),
        (r'\bawk\s+.*<\s*([^\s|&;]+)', 'awk'),
        (r'\bview\s+([^\s|&;]+)', 'view'),
        (r'\bnvim\s+([^\s|&;]+)', 'nvim'),
        (r'\bvi\s+([^\s|&;]+)', 'vi'),
    ]
    
    def __init__(self, threshold: int = 350, base_dir: str = "/testbed"):
        """
        Args:
            threshold: Maximum file size (lines) to allow direct read
            base_dir: Base directory for relative file paths
        """
        self.threshold = threshold
        self.base_dir = base_dir
        self._stats = {
            "files_checked": 0,
            "files_intercepted": 0,
            "files_delegated": 0,
            "files_read_direct": 0
        }
    
    def check_command(self, command: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a command reads a large file
        
        Args:
            command: The bash command to check
            
        Returns:
            Tuple of (should_intercept, file_path, command_type)
        """
        self._stats["files_checked"] += 1
        
        for pattern, cmd_type in self.FILE_READ_PATTERNS:
            match = re.search(pattern, command)
            if match:
                file_path = match.group(1)
                
                # Resolve relative paths
                if not os.path.isabs(file_path):
                    file_path = os.path.join(self.base_dir, file_path)
                
                # Check file size
                lines = self._get_file_lines(file_path)
                if lines is not None and lines > self.threshold:
                    self._stats["files_intercepted"] += 1
                    logger.info(f"Intercepted {cmd_type} on {file_path} ({lines} lines > {self.threshold})")
                    return True, file_path, cmd_type
        
        return False, None, None
    
    def _get_file_lines(self, file_path: str) -> Optional[int]:
        """Get the number of lines in a file"""
        try:
            # First try wc -l
            result = subprocess.run(
                ["wc", "-l", file_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return int(result.stdout.split()[0])
            
            # Fallback: read file and count lines
            with open(file_path, 'r', errors='ignore') as f:
                return sum(1 for _ in f)
                
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            return None
    
    def get_file_content(self, file_path: str) -> Optional[str]:
        """Read file content for delegation"""
        try:
            with open(file_path, 'r', errors='ignore') as f:
                return f.read()
        except (FileNotFoundError, PermissionError):
            return None
    
    def get_stats(self) -> dict:
        """Return interception statistics"""
        return self._stats.copy()
    
    def reset_stats(self):
        """Reset statistics"""
        self._stats = {
            "files_checked": 0,
            "files_intercepted": 0,
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
        error: Optional[str] = None
    ):
        self.intercepted = intercepted
        self.file_path = file_path
        self.command_type = command_type
        self.summary = summary
        self.tokens = tokens or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.error = error
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "intercepted": self.intercepted,
            "file_path": self.file_path,
            "command_type": self.command_type,
            "summary": self.summary,
            "tokens": self.tokens,
            "error": self.error
        }
    
    def __repr__(self) -> str:
        if self.intercepted:
            return f"ShuntResult(intercepted=True, file={self.file_path}, type={self.command_type})"
        return "ShuntResult(intercepted=False)"
