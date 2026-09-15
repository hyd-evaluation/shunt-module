"""
Shunt Code Writer
Delegates boilerplate code generation to cheap worker models
"""

import json
import logging
import os
import time
from typing import Any, Optional

from worker import ShuntWorker, ShuntWorkerFactory, calculate_cost

logger = logging.getLogger("shunt_code_writer")


class ShuntCodeWriter:
    """
    Delegates boilerplate code generation to cheap worker models
    
    Usage:
        writer = ShuntCodeWriter(api_key="...", worker_model="codex/gpt-5.6-luna")
        result = writer.generate(
            spec="Write tests for UserService",
            reference_path="tests/OrderTest.java",
            target_path="tests/UserTest.java"
        )
    """
    
    def __init__(
        self,
        api_key: str,
        worker_model: str = "codex/gpt-5.6-luna",
        api_base: str = "https://pbtest.neusis.ai/router/v1",
        expensive_model: str = "codex/gpt-5.6-sol",
        max_output_tokens: int = 1024
    ):
        self.api_key = api_key
        self.worker_model = worker_model
        self.expensive_model = expensive_model
        
        # Create worker
        self.worker = ShuntWorkerFactory.create_worker(
            model=worker_model,
            api_key=api_key,
            api_base=api_base,
            max_output_tokens=max_output_tokens
        )
        
        # Stats
        self._stats = {
            "total_calls": 0,
            "worker_calls": 0,
            "worker_cost": 0.0,
            "expensive_cost": 0.0,
            "total_lines_generated": 0
        }
    
    def generate(
        self,
        spec: str,
        reference_path: str,
        target_path: Optional[str] = None
    ) -> dict:
        """
        Generate boilerplate code based on spec and reference file
        
        Args:
            spec: Description of what to generate
            reference_path: Path to reference file (for patterns/style)
            target_path: Optional path to write output file
            
        Returns:
            dict with code, tokens, cost, and latency
        """
        # Read reference file
        try:
            with open(reference_path, 'r', errors='ignore') as f:
                reference_content = f.read()
        except Exception as e:
            return {
                "code": "",
                "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "cost": 0.0,
                "latency": 0,
                "success": False,
                "error": f"Could not read reference file: {e}"
            }
        
        # Delegate to worker
        start_time = time.time()
        
        result = self.worker.generate_code(
            spec=spec,
            reference=reference_path,
            reference_content=reference_content
        )
        
        latency = time.time() - start_time
        
        if not result.get("success"):
            return {
                "code": "",
                "tokens": result.get("tokens", {}),
                "cost": 0.0,
                "latency": latency,
                "success": False,
                "error": result.get("error", "Unknown error")
            }
        
        code = result["code"]
        tokens = result["tokens"]
        cost = result["cost"]
        
        # Write to target if specified
        if target_path:
            try:
                os.makedirs(os.path.dirname(target_path) if os.path.dirname(target_path) else '.', exist_ok=True)
                with open(target_path, 'w') as f:
                    f.write(code)
                logger.info(f"Wrote {len(code.split(chr(10)))} lines to {target_path}")
            except Exception as e:
                logger.error(f"Failed to write to {target_path}: {e}")
        
        # Update stats
        self._stats["total_calls"] += 1
        self._stats["worker_calls"] += 1
        self._stats["worker_cost"] += cost
        self._stats["total_lines_generated"] += len(code.split('\n'))
        
        return {
            "code": code,
            "tokens": tokens,
            "cost": cost,
            "model": self.worker_model,
            "latency": latency,
            "lines_generated": len(code.split('\n')),
            "success": True
        }
    
    def estimate_savings(
        self,
        spec: str,
        reference_path: str
    ) -> dict:
        """
        Estimate cost savings for code generation
        Compares: worker (cheap) vs direct (expensive)
        """
        # Read reference file
        try:
            with open(reference_path, 'r', errors='ignore') as f:
                reference_content = f.read()
        except Exception as e:
            return {"error": f"Could not read reference file: {e}"}
        
        # Estimate tokens (rough: 4 chars per token)
        prompt_estimate = len(spec) + len(reference_content) + 200  # overhead
        input_tokens = prompt_estimate // 4
        output_tokens = 512  # typical code generation output
        
        # Calculate costs
        worker_cost = calculate_cost(input_tokens, output_tokens, self.worker_model)
        expensive_cost = calculate_cost(input_tokens, output_tokens, self.expensive_model)
        
        savings = expensive_cost - worker_cost
        savings_pct = (savings / expensive_cost * 100) if expensive_cost > 0 else 0
        
        return {
            "worker_model": self.worker_model,
            "expensive_model": self.expensive_model,
            "estimated_tokens": {
                "input": input_tokens,
                "output": output_tokens
            },
            "worker_cost": worker_cost,
            "expensive_cost": expensive_cost,
            "estimated_savings": savings,
            "estimated_savings_pct": savings_pct
        }
    
    def get_stats(self) -> dict:
        """Return accumulated statistics"""
        stats = self._stats.copy()
        stats["worker_metrics"] = self.worker.get_metrics()
        return stats


class ShuntCodeWriterFactory:
    """Factory for creating code writer instances"""
    
    @classmethod
    def create(
        cls,
        api_key: str,
        worker_model: str = "codex/gpt-5.6-luna",
        expensive_model: str = "codex/gpt-5.6-sol",
        **kwargs
    ) -> ShuntCodeWriter:
        """Create a code writer instance"""
        return ShuntCodeWriter(
            api_key=api_key,
            worker_model=worker_model,
            expensive_model=expensive_model,
            **kwargs
        )
