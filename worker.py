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
