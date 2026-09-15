#!/usr/bin/env bash
# ============================================
# Shunt Module - Automated Setup Script
# Version: 1.0
# ============================================

set -euo pipefail

# ============================================
# Configuration
# ============================================
INSTALL_DIR="${HOME}/shunt-module"
HARNESS_DIR="${HOME}/pb-harness-v2"
DEFAULT_API_KEY="sk-55100efb9fb4a726-62bfab-89db8b81"
SCRIPT_VERSION="1.0"
TOTAL_STEPS=8

# ============================================
# Logging Functions
# ============================================
log_info() { echo "[INFO] $1"; }
log_verbose() { if $VERBOSE; then echo "[VERBOSE] $1"; fi; }
log_error() { echo "[ERROR] $1" >&2; }
log_step() { echo "Step $1/$TOTAL_STEPS: $2"; }

# ============================================
# Utility Functions
# ============================================
check_python() {
    log_step 1 "Checking Python"
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 not found. Install Python 3.11+ first."
        exit 1
    fi
    
    PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    log_verbose "Python version: ${PYTHON_VER}"
    
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
        log_verbose "Python version OK"
    else
        log_error "Python 3.11+ required. Found: ${PYTHON_VER}"
        exit 1
    fi
    
    echo "✅ Python ${PYTHON_VER} found"
}

check_internet() {
    log_verbose "Checking internet connection..."
    
    if ! ping -c 1 8.8.8.8 &> /dev/null; then
        log_error "No internet connection. Required for installing dependencies."
        exit 1
    fi
    
    log_verbose "Internet connection OK"
}

check_existing() {
    if [ -d "${INSTALL_DIR}" ]; then
        if $FORCE; then
            log_verbose "Force mode: Cleaning existing directory"
            # Remove everything except the setup script itself
            find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 ! -name "setup.sh" -exec rm -rf {} + 2>/dev/null || true
            return
        fi
        
        echo ""
        echo "Existing directory found: ${INSTALL_DIR}"
        echo ""
        echo "Options:"
        echo "  1. Skip (keep existing)"
        echo "  2. Reinstall (overwrite)"
        echo "  3. Uninstall (remove everything)"
        echo ""
        read -p "Enter choice (1/2/3): " CHOICE
        
        case $CHOICE in
            1) log_verbose "Skipping existing directory"; exit 0 ;;
            2) log_verbose "Reinstalling..."; rm -rf "${INSTALL_DIR}" ;;
            3) uninstall; exit 0 ;;
            *) log_error "Invalid choice"; exit 1 ;;
        esac
    fi
}

ask_confirmation() {
    if $FORCE; then
        log_verbose "Force mode enabled, skipping confirmation"
        return
    fi
    
    echo ""
    echo "This will create the following directories:"
    echo "  1. ${INSTALL_DIR}/"
    echo "  2. ${HARNESS_DIR}/"
    echo ""
    echo "And install:"
    echo "  - Python files (4)"
    echo "  - Config files (1)"
    echo "  - README.md"
    echo "  - Dependencies"
    echo ""
    read -p "Do you want to proceed? (1=Yes, 2=No): " CONFIRM
    
    if [ "$CONFIRM" != "1" ]; then
        log_info "Setup cancelled by user"
        exit 0
    fi
}

# ============================================
# Setup Functions
# ============================================
create_directories() {
    log_step 2 "Creating directories"
    
    mkdir -p "${INSTALL_DIR}"/{configs,scripts,tests,results}
    mkdir -p "${HARNESS_DIR}"
    
    log_verbose "Created ${INSTALL_DIR}/"
    log_verbose "Created ${INSTALL_DIR}/configs/"
    log_verbose "Created ${INSTALL_DIR}/results/"
    log_verbose "Created ${HARNESS_DIR}/"
    
    echo "✅ Directories created"
}

create_venv() {
    log_step 3 "Creating virtual environment"
    
    cd "${HARNESS_DIR}"
    python3 -m venv venv
    
    log_verbose "Virtual environment created at ${HARNESS_DIR}/venv"
    echo "✅ Virtual environment created"
}

install_deps() {
    log_step 4 "Installing dependencies"
    
    source "${HARNESS_DIR}/venv/bin/activate"
    pip install --quiet mini-swe-agent pyyaml jinja2 requests
    
    log_verbose "Installed: mini-swe-agent, pyyaml, jinja2, requests"
    echo "✅ Dependencies installed"
}

copy_files() {
    log_step 5 "Copying shunt module files"
    
    # Create __init__.py
    cat > "${INSTALL_DIR}/__init__.py" << 'EOF'
"""Shunt Module - Cost savings through model routing"""
from .worker import ShuntWorker, ShuntWorkerFactory
from .interceptor import ShuntInterceptor
from .shunt_model import ShuntModel, ShuntModelFactory

__all__ = [
    "ShuntWorker",
    "ShuntWorkerFactory", 
    "ShuntInterceptor",
    "ShuntModel",
    "ShuntModelFactory"
]
EOF
    log_verbose "Copied __init__.py"
    
    # Create worker.py
    cat > "${INSTALL_DIR}/worker.py" << 'WORKEREOF'
"""
Shunt Worker Client
Calls cheap worker models (Luna, Gemini, Nemotron, etc.) for file summarization
"""

import json
import logging
import os
import time
from typing import Any, Optional

import requests

logger = logging.getLogger("shunt_worker")


class ShuntWorker:
    """Client for calling worker models via Neusis Router"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "codex/gpt-5.6-luna",
        api_base: str = "https://pbtest.neusis.ai/router/v1",
        timeout: int = 120
    ):
        self.api_key = api_key
        self.model = model
        self.api_url = api_base
        self.timeout = timeout
        self._total_tokens = 0
        self._total_cost = 0.0
        self._call_count = 0
    
    def summarize(
        self,
        file_path: str,
        content: str,
        question: str = "Summarize this file for code analysis"
    ) -> dict:
        """
        Send file to worker model for summarization
        
        Args:
            file_path: Path to the file
            content: File content
            question: What to ask about the file
            
        Returns:
            dict with summary, tokens, and model info
        """
        prompt = self._build_prompt(file_path, content, question)
        
        try:
            start_time = time.time()
            response = self._call_api(prompt)
            latency = time.time() - start_time
            
            # Extract results
            summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = response.get("usage", {})
            
            tokens = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }
            
            # Update stats
            self._total_tokens += tokens["total_tokens"]
            self._call_count += 1
            
            return {
                "summary": summary,
                "tokens": tokens,
                "model": self.model,
                "latency": latency,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Worker call failed: {e}")
            return {
                "summary": "",
                "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "model": self.model,
                "latency": 0,
                "success": False,
                "error": str(e)
            }
    
    def _build_prompt(self, file_path: str, content: str, question: str) -> str:
        """Build the prompt for the worker model"""
        return f"""<file path="{file_path}">
{content}
</file>

Task: {question}

Provide a structured summary with:
1. Key functions/classes and their purposes
2. Important logic and algorithms
3. Potential issues or TODOs
4. Dependencies and imports
5. How this file interacts with other parts of the codebase

Be concise but comprehensive. Focus on what's important for understanding and modifying this code."""
    
    def _call_api(self, prompt: str) -> dict:
        """Call the Neusis Router API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0.2,
            "max_tokens": 4096
        }
        
        response = requests.post(
            f"{self.api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout
        )
        
        response.raise_for_status()
        
        # Handle streaming response (SSE)
        if response.text.startswith("data:"):
            return self._parse_sse_response(response.text)
        
        return response.json()
    
    def _parse_sse_response(self, text: str) -> dict:
        """Parse SSE streaming response"""
        content = ""
        for line in text.split("\n"):
            if line.startswith("data:"):
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            content += delta["content"]
                except json.JSONDecodeError:
                    continue
        
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {"total_tokens": len(content) // 4}  # Estimate
        }
    
    def get_metrics(self) -> dict:
        """Return accumulated metrics"""
        return {
            "total_tokens": self._total_tokens,
            "call_count": self._call_count,
            "model": self.model
        }


class ShuntWorkerFactory:
    """Factory for creating worker instances"""
    
    WORKER_CONFIGS = {
        "codex/gpt-5.6-luna": {
            "api_base": "https://pbtest.neusis.ai/router/v1",
            "description": "Fast, good at code"
        },
        "openrouter/google/gemini-3.6-flash": {
            "api_base": "https://pbtest.neusis.ai/router/v1",
            "description": "Fast, good at text"
        },
        "openrouter/nvidia/nemotron-3.5-lightning:free": {
            "api_base": "https://pbtest.neusis.ai/router/v1",
            "description": "Free, good enough"
        },
        "openrouter/qwen/qwen3-coder": {
            "api_base": "https://pbtest.neusis.ai/router/v1",
            "description": "Good at code"
        }
    }
    
    @classmethod
    def create_worker(
        cls,
        model: str,
        api_key: str,
        api_base: Optional[str] = None
    ) -> ShuntWorker:
        """Create a worker instance for the specified model"""
        if api_base is None:
            config = cls.WORKER_CONFIGS.get(model, {})
            api_base = config.get("api_base", "https://pbtest.neusis.ai/router/v1")
        
        return ShuntWorker(
            api_key=api_key,
            model=model,
            api_base=api_base
        )
    
    @classmethod
    def list_available_workers(cls) -> list:
        """List all available worker models"""
        return [
            {
                "model": model,
                **config
            }
            for model, config in cls.WORKER_CONFIGS.items()
        ]
WORKEREOF
    log_verbose "Copied worker.py"
    
    # Create interceptor.py
    cat > "${INSTALL_DIR}/interceptor.py" << 'INTERCEPTEOF'
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
INTERCEPTEOF
    log_verbose "Copied interceptor.py"
    
    # Create shunt_model.py
    cat > "${INSTALL_DIR}/shunt_model.py" << 'MODELEOF'
"""
Shunt Model
Wraps NeusisRouterModel with shunt interception for large file reads
"""

import json
import logging
import os
import re
import time
from typing import Any, Optional

from .interceptor import ShuntInterceptor
from .worker import ShuntWorker, ShuntWorkerFactory

logger = logging.getLogger("shunt_model")


class ShuntModel:
    """
    Wraps any model class with shunt interception
    
    Usage:
        model = ShuntModel(
            base_model=NeusisRouterModel(...),
            worker_model="codex/gpt-5.6-luna",
            api_key="...",
            threshold=350
        )
    """
    
    def __init__(
        self,
        base_model: Any,
        worker_model: str = "codex/gpt-5.6-luna",
        api_key: str = "",
        api_base: str = "https://pbtest.neusis.ai/router/v1",
        threshold: int = 350,
        base_dir: str = "/testbed",
        delegate_question: str = "Summarize this file for code analysis and bug fixing"
    ):
        self.base_model = base_model
        self.worker_model = worker_model
        self.threshold = threshold
        self.delegate_question = delegate_question
        
        # Create worker
        self.worker = ShuntWorkerFactory.create_worker(
            model=worker_model,
            api_key=api_key,
            api_base=api_base
        )
        
        # Create interceptor
        self.interceptor = ShuntInterceptor(threshold=threshold, base_dir=base_dir)
        
        # Stats
        self._stats = {
            "total_queries": 0,
            "intercepted_queries": 0,
            "delegated_queries": 0,
            "tokens_expensive": 0,
            "tokens_worker": 0,
            "savings": 0
        }
    
    def query(self, messages: list, **kwargs) -> Any:
        """
        Query with shunt interception
        
        Checks each message for file read commands. If found and file is large,
        intercepts and delegates to worker model.
        """
        self._stats["total_queries"] += 1
        
        # Process messages for interception
        processed_messages = []
        intercepted_count = 0
        
        for msg in messages:
            if msg.get("role") == "user" or msg.get("role") == "assistant":
                content = msg.get("content", "")
                
                # Check for file read commands
                intercepted, file_path, cmd_type = self.interceptor.check_command(content)
                
                if intercepted:
                    intercepted_count += 1
                    summary_result = self._delegate_file(file_path)
                    
                    if summary_result.get("success"):
                        # Replace file content with summary
                        summary = summary_result["summary"]
                        new_content = self._replace_with_summary(content, file_path, summary)
                        processed_messages.append({**msg, "content": new_content})
                        
                        # Track tokens
                        self._stats["tokens_worker"] += summary_result["tokens"]["total_tokens"]
                    else:
                        # Worker failed, pass through
                        processed_messages.append(msg)
                else:
                    processed_messages.append(msg)
            else:
                processed_messages.append(msg)
        
        if intercepted_count > 0:
            self._stats["intercepted_queries"] += 1
            self._stats["delegated_queries"] += intercepted_count
        
        # Call base model
        result = self.base_model.query(processed_messages, **kwargs)
        
        # Track expensive model tokens (estimate)
        self._stats["tokens_expensive"] += self._estimate_tokens(processed_messages)
        
        return result
    
    def _delegate_file(self, file_path: str) -> dict:
        """Delegate file reading to worker model"""
        # Get file content
        content = self.interceptor.get_file_content(file_path)
        if content is None:
            return {"success": False, "error": "Could not read file"}
        
        # Call worker
        result = self.worker.summarize(
            file_path=file_path,
            content=content,
            question=self.delegate_question
        )
        
        return result
    
    def _replace_with_summary(self, original: str, file_path: str, summary: str) -> str:
        """Replace file content in message with summary"""
        # Try to find and replace cat/head/tail commands
        patterns = [
            (rf'cat\s+{re.escape(file_path)}', f'[SUMMARY of {file_path}]\n{summary}\n[END SUMMARY]'),
            (rf'head\s+.*\s+{re.escape(file_path)}', f'[SUMMARY of {file_path}]\n{summary}\n[END SUMMARY]'),
            (rf'tail\s+.*\s+{re.escape(file_path)}', f'[SUMMARY of {file_path}]\n{summary}\n[END SUMMARY]'),
        ]
        
        result = original
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result)
        
        return result
    
    def _estimate_tokens(self, messages: list) -> int:
        """Estimate token count for messages"""
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        return total_chars // 4
    
    def get_stats(self) -> dict:
        """Return statistics"""
        stats = self._stats.copy()
        stats["worker_metrics"] = self.worker.get_metrics()
        stats["interceptor_stats"] = self.interceptor.get_stats()
        
        # Calculate savings
        if stats["tokens_expensive"] > 0:
            savings_percent = (stats["tokens_worker"] / stats["tokens_expensive"]) * 100
            stats["savings_percent"] = round(savings_percent, 2)
        else:
            stats["savings_percent"] = 0
        
        return stats


class ShuntModelFactory:
    """Factory for creating shunt model instances"""
    
    @classmethod
    def create(
        cls,
        base_model: Any,
        worker_model: str = "codex/gpt-5.6-luna",
        api_key: str = "",
        **kwargs
    ) -> ShuntModel:
        """Create a shunt model instance"""
        return ShuntModel(
            base_model=base_model,
            worker_model=worker_model,
            api_key=api_key,
            **kwargs
        )
MODELEOF
    log_verbose "Copied shunt_model.py"
    
    echo "✅ Shunt module files copied"
}

create_configs() {
    log_step 6 "Creating config files"
    
    cat > "${INSTALL_DIR}/configs/shunt_neusiscode.yaml" << EOF
# Shunt NeusisCode Configuration
# Uses NeusisRouterModel as base with shunt interception
# Worker model: Luna (configurable)

model:
  model_class: configs.neusis_router_model:NeusisRouterModel
  model_name: codex/gpt-5.6-luna
  model_kwargs:
    api_base: https://pbtest.neusis.ai/router/v1
    api_key: ${API_KEY}

# Shunt configuration
shunt:
  enabled: true
  worker_model: codex/gpt-5.6-luna  # Configurable - change this per task
  threshold: 350  # Lines - files larger than this get intercepted
  api_base: https://pbtest.neusis.ai/router/v1
  api_key: ${API_KEY}

# Agent configuration
agent:
  name: neusiscode
  description: NeusisCode with shunt interception
  tools:
    - name: bash
      description: Execute bash commands
    - name: read
      description: Read file contents
    - name: write
      description: Write file contents
    - name: edit
      description: Edit file contents

# Environment
environment:
  base_dir: /testbed
  python_version: "3.10"
  node_version: "18"

# Execution
execution:
  max_steps: 50
  timeout: 600
  retry_attempts: 3

# Logging
logging:
  level: INFO
  log_shunt_interceptions: true
  log_token_usage: true
EOF
    
    log_verbose "Created shunt_neusiscode.yaml"
    echo "✅ Config files created"
}

create_readme() {
    log_step 7 "Creating README.md"
    
    cat > "${INSTALL_DIR}/README.md" << 'EOF'
# Shunt Module

A lightweight implementation of Spotify's "shunt" pattern for cost savings.

## Quick Start

```bash
# Test setup
PYTHONPATH=~ python3 -c "from shunt_module import ShuntInterceptor; print('OK')"

# Run setup check
bash setup.sh --check
```

## Components

- `worker.py` - Worker client for cheap models
- `interceptor.py` - File read interception
- `shunt_model.py` - Shunt model wrapper

## Configuration

Edit `configs/shunt_neusiscode.yaml` to change:
- `worker_model` - Which cheap model to use
- `threshold` - File size threshold (lines)
- `api_key` - Your API key

## Available Worker Models

| Model | Cost | Speed |
|-------|------|-------|
| codex/gpt-5.6-luna | $1.00/$6.00 | Fast |
| openrouter/google/gemini-3.6-flash | $0.00 | Fast |
| openrouter/nvidia/nemotron-3.5-lightning:free | $0.00 | Fast |
| openrouter/qwen/qwen3-coder | $0.50/$2.00 | Medium |

## Usage

```python
from shunt_module import ShuntModel, ShuntWorkerFactory

# Create base model
base_model = NeusisRouterModel(...)

# Create shunt model
shunt_model = ShuntModel(
    base_model=base_model,
    worker_model="codex/gpt-5.6-luna",
    api_key="sk-...",
    threshold=350
)

# Use it
result = shunt_model.query(messages)
```
EOF
    
    log_verbose "Created README.md"
    echo "✅ README.md created"
}

test_setup() {
    log_step 8 "Testing setup"
    
    cd "${INSTALL_DIR}"
    PYTHONPATH="${HOME}:${PYTHONPATH:-}" python3 -c "
    from shunt_module import ShuntInterceptor
    interceptor = ShuntInterceptor(threshold=350)
    print('✅ Shunt module import successful')
    "
    
    echo "✅ Setup test passed"
}

uninstall() {
    echo "Uninstalling shunt module..."
    rm -rf "${INSTALL_DIR}"
    rm -rf "${HARNESS_DIR}"
    echo "✅ Uninstalled successfully"
}

check_setup() {
    echo "Checking setup..."
    echo ""
    
    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        echo "  [✓] Python: ${PYTHON_VER}"
    else
        echo "  [✗] Python: not found"
    fi
    
    # Check virtual environment
    if [ -d "${HARNESS_DIR}/venv" ]; then
        echo "  [✓] Virtual environment: exists"
    else
        echo "  [✗] Virtual environment: not found"
    fi
    
    # Check dependencies
    if "${HARNESS_DIR}/venv/bin/python" -c "import minisweagent" 2>/dev/null; then
        echo "  [✓] Dependencies: installed"
    else
        echo "  [✗] Dependencies: not installed"
    fi
    
    # Check shunt module
    if PYTHONPATH="${HOME}:${PYTHONPATH:-}" python3 -c "from shunt_module import ShuntInterceptor" 2>/dev/null; then
        echo "  [✓] Shunt module: importable"
    else
        echo "  [✗] Shunt module: not importable"
    fi
    
    # Check config files
    if [ -f "${INSTALL_DIR}/configs/shunt_neusiscode.yaml" ]; then
        echo "  [✓] Config files: present"
    else
        echo "  [✗] Config files: not found"
    fi
    
    echo ""
    echo "Setup check complete!"
}

show_help() {
    echo "Shunt Module Setup Script v${SCRIPT_VERSION}"
    echo ""
    echo "Usage: bash setup.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dry-run       Preview without making changes"
    echo "  --verbose       Show detailed output"
    echo "  --force         Skip confirmation prompts"
    echo "  --check         Verify existing setup"
    echo "  --uninstall     Remove all installed files"
    echo "  --api-key KEY   Use custom API key"
    echo "  --version       Show script version"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  bash setup.sh                    # Interactive setup"
    echo "  bash setup.sh --dry-run          # Preview only"
    echo "  bash setup.sh --force            # Skip confirmation"
    echo "  bash setup.sh --check            # Verify setup"
    echo "  bash setup.sh --uninstall        # Remove everything"
    echo "  bash setup.sh --api-key YOUR_KEY # Custom API key"
}

show_version() {
    echo "Shunt Module Setup Script v${SCRIPT_VERSION}"
}

print_summary() {
    echo ""
    echo "=========================================="
    echo "Setup Complete!"
    echo "=========================================="
    echo ""
    echo "Files created:"
    echo "  ${INSTALL_DIR}/"
    echo "  ├── __init__.py"
    echo "  ├── worker.py"
    echo "  ├── interceptor.py"
    echo "  ├── shunt_model.py"
    echo "  ├── README.md"
    echo "  └── configs/"
    echo "      └── shunt_neusiscode.yaml"
    echo ""
    echo "Next steps:"
    echo "  1. Test with: PYTHONPATH=~ python3 -c \"from shunt_module import ShuntInterceptor; print('OK')\""
    echo "  2. Run: bash setup.sh --check"
}

# ============================================
# Argument Parsing
# ============================================
DRY_RUN=false
VERBOSE=false
FORCE=false
UNINSTALL=false
CHECK=false
API_KEY="${DEFAULT_API_KEY}"

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run) DRY_RUN=true; shift ;;
            --verbose) VERBOSE=true; shift ;;
            --force) FORCE=true; shift ;;
            --uninstall) UNINSTALL=true; shift ;;
            --check) CHECK=true; shift ;;
            --api-key) API_KEY="$2"; shift 2 ;;
            --version) show_version; exit 0 ;;
            --help) show_help; exit 0 ;;
            *) log_error "Unknown option: $1"; show_help; exit 1 ;;
        esac
    done
}

# ============================================
# Main
# ============================================
main() {
    parse_args "$@"
    
    echo "=========================================="
    echo "Shunt Module - Automated Setup"
    echo "=========================================="
    echo "Username: $(whoami)"
    echo "Home: ${HOME}"
    echo "Dry run: ${DRY_RUN}"
    echo "Verbose: ${VERBOSE}"
    echo ""
    
    if $CHECK; then
        check_setup
        exit 0
    fi
    
    if $UNINSTALL; then
        uninstall
        exit 0
    fi
    
    check_python
    check_internet
    check_existing
    ask_confirmation
    
    if $DRY_RUN; then
        echo ""
        echo "Dry run complete. No changes made."
        exit 0
    fi
    
    create_directories
    create_venv
    install_deps
    copy_files
    create_configs
    create_readme
    test_setup
    print_summary
}

main "$@"