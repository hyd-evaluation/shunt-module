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
