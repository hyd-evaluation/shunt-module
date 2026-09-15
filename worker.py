"""
Shunt Worker Client
Calls cheap worker models (Luna, Gemini, Nemotron, etc.) for file summarization
Focus on TOKEN COST savings, not just token count
"""

import json
import logging
import os
import time
from typing import Any, Optional

import requests

logger = logging.getLogger("shunt_worker")

# Pricing per 1M tokens (input/output)
PRICING = {
    "codex/gpt-5.6-luna": {"input": 1.00, "output": 6.00},
    "codex/gpt-5.6-sol": {"input": 2.50, "output": 15.00},
    "codex/gpt-5.6-terra": {"input": 2.50, "output": 15.00},
    "openrouter/google/gemini-3.6-flash": {"input": 0.15, "output": 0.60},
    "openrouter/nvidia/nemotron-3.5-lightning:free": {"input": 0.0, "output": 0.0},
    "openrouter/qwen/qwen3-coder": {"input": 0.50, "output": 2.00},
}

# Default pricing for unknown models
DEFAULT_PRICING = {"input": 1.00, "output": 6.00}


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost in dollars for given token counts"""
    pricing = PRICING.get(model, DEFAULT_PRICING)
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


class ShuntWorker:
    """Client for calling worker models via Neusis Router"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "codex/gpt-5.6-luna",
        api_base: str = "https://pbtest.neusis.ai/router/v1",
        timeout: int = 120,
        max_output_tokens: int = 1024
    ):
        self.api_key = api_key
        self.model = model
        self.api_url = api_base
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self._total_input_tokens = 0
        self._total_output_tokens = 0
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
        Focus on minimizing COST, not just tokens
        """
        prompt = self._build_summarize_prompt(file_path, content, question)
        
        try:
            start_time = time.time()
            response = self._call_api(prompt)
            latency = time.time() - start_time
            
            # Extract results
            summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = response.get("usage", {})
            
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            cost = calculate_cost(input_tokens, output_tokens, self.model)
            
            # Update stats
            self._total_input_tokens += input_tokens
            self._total_output_tokens += output_tokens
            self._total_cost += cost
            self._call_count += 1
            
            return {
                "summary": summary,
                "tokens": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens
                },
                "cost": cost,
                "model": self.model,
                "latency": latency,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Worker call failed: {e}")
            return {
                "summary": "",
                "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "cost": 0.0,
                "model": self.model,
                "latency": 0,
                "success": False,
                "error": str(e)
            }
    
    def generate_code(
        self,
        spec: str,
        reference: str,
        reference_content: str
    ) -> dict:
        """
        Generate boilerplate code based on spec and reference file
        """
        prompt = self._build_codegen_prompt(spec, reference, reference_content)
        
        try:
            start_time = time.time()
            response = self._call_api(prompt)
            latency = time.time() - start_time
            
            # Extract results
            code = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = response.get("usage", {})
            
            # Strip markdown fences
            code = self._strip_markdown_fences(code)
            
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            cost = calculate_cost(input_tokens, output_tokens, self.model)
            
            # Update stats
            self._total_input_tokens += input_tokens
            self._total_output_tokens += output_tokens
            self._total_cost += cost
            self._call_count += 1
            
            return {
                "code": code,
                "tokens": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens
                },
                "cost": cost,
                "model": self.model,
                "latency": latency,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            return {
                "code": "",
                "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "cost": 0.0,
                "model": self.model,
                "latency": 0,
                "success": False,
                "error": str(e)
            }
    
    def _build_summarize_prompt(self, file_path: str, content: str, question: str) -> str:
        """Build the prompt for summarization"""
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
    
    def _build_codegen_prompt(self, spec: str, reference: str, reference_content: str) -> str:
        """Build the prompt for code generation"""
        return f"""Spec: {spec}

Reference file ({reference}):
{reference_content}

Generate code that matches the patterns, conventions, naming, and style of the reference file. Output only the code - no explanations, no markdown fences unless asked. If the spec is ambiguous, make reasonable choices that match the patterns in the reference code."""
    
    def _strip_markdown_fences(self, code: str) -> str:
        """Strip markdown code fences from output"""
        lines = code.split('\n')
        result = []
        in_fence = False
        
        for line in lines:
            if line.strip().startswith('```'):
                in_fence = not in_fence
                continue
            if not in_fence:
                result.append(line)
        
        return '\n'.join(result)
    
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
            "max_tokens": self.max_output_tokens
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
        
        # Estimate tokens for SSE response
        input_tokens = len(content) // 4
        output_tokens = len(content) // 4
        
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens
            }
        }
    
    def get_metrics(self) -> dict:
        """Return accumulated metrics with COST focus"""
        return {
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "total_cost": self._total_cost,
            "call_count": self._call_count,
            "model": self.model,
            "avg_cost_per_call": self._total_cost / self._call_count if self._call_count > 0 else 0.0
        }


class ShuntWorkerFactory:
    """Factory for creating worker instances"""
    
    WORKER_CONFIGS = {
        "codex/gpt-5.6-luna": {
            "api_base": "https://pbtest.neusis.ai/router/v1",
            "description": "Fast, good at code",
            "max_output_tokens": 1024
        },
        "openrouter/google/gemini-3.6-flash": {
            "api_base": "https://pbtest.neusis.ai/router/v1",
            "description": "Fast, good at text",
            "max_output_tokens": 1024
        },
        "openrouter/nvidia/nemotron-3.5-lightning:free": {
            "api_base": "https://pbtest.neusis.ai/router/v1",
            "description": "Free, good enough",
            "max_output_tokens": 1024
        },
        "openrouter/qwen/qwen3-coder": {
            "api_base": "https://pbtest.neusis.ai/router/v1",
            "description": "Good at code",
            "max_output_tokens": 1024
        }
    }
    
    @classmethod
    def create_worker(
        cls,
        model: str,
        api_key: str,
        api_base: Optional[str] = None,
        max_output_tokens: Optional[int] = None
    ) -> ShuntWorker:
        """Create a worker instance for the specified model"""
        config = cls.WORKER_CONFIGS.get(model, {})
        
        if api_base is None:
            api_base = config.get("api_base", "https://pbtest.neusis.ai/router/v1")
        
        if max_output_tokens is None:
            max_output_tokens = config.get("max_output_tokens", 1024)
        
        return ShuntWorker(
            api_key=api_key,
            model=model,
            api_base=api_base,
            max_output_tokens=max_output_tokens
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
