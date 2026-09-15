#!/usr/bin/env python3
"""
Full Code-Writer Evaluation
Tests code generation on 20+ files from ShardingSphere
"""

import asyncio
import aiohttp
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Any

# Configuration
API_KEY = "sk-55100efb9fb4a726-62bfab-89db8b81"
API_BASE = "https://pbtest.neusis.ai/router/v1"

WORKER_MODEL = "codex/gpt-5.6-luna"
EXPENSIVE_MODEL = "codex/gpt-5.6-sol"

# Pricing per 1M tokens
PRICING = {
    "codex/gpt-5.6-luna": {"input": 1.00, "output": 6.00},
    "codex/gpt-5.6-sol": {"input": 2.50, "output": 15.00},
}

REPO_PATH = "/home/varun/shardingsphere"
RESULTS_DIR = "/home/varun/shunt-module/results"
MAX_CONCURRENT = 5
TIMEOUT = 180


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost in dollars"""
    pricing = PRICING.get(model, PRICING["codex/gpt-5.6-luna"])
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def find_test_files(repo_path: str, min_lines: int = 100, max_lines: int = 800) -> List[Dict]:
    """Find test files that can be used as references for code generation"""
    test_files = []
    
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith('Test.java') or file.endswith('Tests.java'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', errors='ignore') as f:
                        lines = sum(1 for _ in f)
                    
                    if min_lines <= lines <= max_lines:
                        # Read content
                        with open(file_path, 'r', errors='ignore') as f:
                            content = f.read()
                        
                        # Extract class name
                        class_name = file.replace('.java', '')
                        
                        test_files.append({
                            "path": file_path,
                            "name": file,
                            "class_name": class_name,
                            "lines": lines,
                            "content": content
                        })
                        
                        if len(test_files) >= 25:  # Get 25 files
                            return test_files
                except Exception:
                    continue
    
    return test_files


async def call_api(session: aiohttp.ClientSession, model: str, messages: List[Dict], max_tokens: int = 1024) -> Dict:
    """Call the API"""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0.2
    }
    
    async with session.post(
        f"{API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=aiohttp.ClientTimeout(total=TIMEOUT)
    ) as response:
        result = await response.json()
        
        if 'error' in result:
            return {'error': result['error'].get('message', 'Unknown error'), 'success': False}
        
        return {
            'content': result.get('choices', [{}])[0].get('message', {}).get('content', ''),
            'usage': result.get('usage', {}),
            'success': True
        }


async def test_code_generation(session: aiohttp.ClientSession, file_info: Dict, semaphore: asyncio.Semaphore) -> Dict:
    """Test code generation for a single file"""
    async with semaphore:
        file_name = file_info["name"]
        class_name = file_info["class_name"]
        content = file_info["content"]
        lines = file_info["lines"]
        
        # Spec: Generate tests for the class
        spec = f"Write comprehensive unit tests for {class_name}"
        
        # Build prompt
        prompt = f"""Spec: {spec}

Reference file ({file_name}):
{content}

Generate code that matches the patterns, conventions, naming, and style of the reference file. Output only the code - no explanations, no markdown fences unless asked."""
        
        # Test with worker (Luna)
        worker_start = time.time()
        worker_result = await call_api(session, WORKER_MODEL, [
            {"role": "user", "content": prompt}
        ])
        worker_latency = time.time() - worker_start
        
        if not worker_result.get('success'):
            return {
                "file": file_name,
                "lines": lines,
                "success": False,
                "error": worker_result.get('error')
            }
        
        worker_usage = worker_result.get('usage', {})
        worker_input = worker_usage.get('prompt_tokens', 0)
        worker_output = worker_usage.get('completion_tokens', 0)
        worker_cost = calculate_cost(worker_input, worker_output, WORKER_MODEL)
        
        # Test with expensive model (Sol) for comparison
        expensive_start = time.time()
        expensive_result = await call_api(session, EXPENSIVE_MODEL, [
            {"role": "user", "content": prompt}
        ])
        expensive_latency = time.time() - expensive_start
        
        if not expensive_result.get('success'):
            return {
                "file": file_name,
                "lines": lines,
                "success": False,
                "error": expensive_result.get('error')
            }
        
        expensive_usage = expensive_result.get('usage', {})
        expensive_input = expensive_usage.get('prompt_tokens', 0)
        expensive_output = expensive_usage.get('completion_tokens', 0)
        expensive_cost = calculate_cost(expensive_input, expensive_output, EXPENSIVE_MODEL)
        
        # Calculate savings
        savings = expensive_cost - worker_cost
        savings_pct = (savings / expensive_cost * 100) if expensive_cost > 0 else 0
        
        # Get generated code length
        worker_code = worker_result.get('content', '')
        expensive_code = expensive_result.get('content', '')
        
        return {
            "file": file_name,
            "class_name": class_name,
            "lines": lines,
            "worker": {
                "model": WORKER_MODEL,
                "input_tokens": worker_input,
                "output_tokens": worker_output,
                "total_tokens": worker_input + worker_output,
                "cost": worker_cost,
                "latency": worker_latency,
                "code_lines": len(worker_code.split('\n')),
                "code_length": len(worker_code)
            },
            "expensive": {
                "model": EXPENSIVE_MODEL,
                "input_tokens": expensive_input,
                "output_tokens": expensive_output,
                "total_tokens": expensive_input + expensive_output,
                "cost": expensive_cost,
                "latency": expensive_latency,
                "code_lines": len(expensive_code.split('\n')),
                "code_length": len(expensive_code)
            },
            "savings": {
                "cost": savings,
                "percentage": savings_pct
            },
            "success": True
        }


async def run_evaluation():
    """Run full code-writer evaluation"""
    print("=" * 70)
    print("FULL CODE-WRITER EVALUATION")
    print("=" * 70)
    
    # Find test files
    print(f"\nScanning {REPO_PATH} for test files...")
    test_files = find_test_files(REPO_PATH)
    print(f"Found {len(test_files)} test files")
    
    if not test_files:
        print("No test files found. Exiting.")
        return
    
    # Show file distribution
    lines_range = [f["lines"] for f in test_files]
    print(f"Lines range: {min(lines_range)} - {max(lines_range)}")
    print(f"Average lines: {sum(lines_range) // len(lines_range)}")
    
    # Run tests
    print(f"\nRunning code generation tests ({MAX_CONCURRENT} concurrent)...")
    start_time = time.time()
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)
    
    results = []
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_code_generation(session, f, semaphore) for f in test_files]
        
        completed = 0
        total = len(tasks)
        
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            completed += 1
            
            if completed % 5 == 0 or completed == total:
                successful = len([r for r in results if r.get('success')])
                print(f"  Progress: {completed}/{total} ({completed*100//total}%) - {successful} successful")
    
    total_time = time.time() - start_time
    print(f"\nTotal evaluation time: {total_time:.1f}s ({total_time/60:.1f} min)")
    
    # Analyze results
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    if not successful:
        print("No successful tests. Exiting.")
        return
    
    # Calculate statistics
    worker_costs = [r['worker']['cost'] for r in successful]
    expensive_costs = [r['expensive']['cost'] for r in successful]
    savings_pct = [r['savings']['percentage'] for r in successful]
    worker_latencies = [r['worker']['latency'] for r in successful]
    expensive_latencies = [r['expensive']['latency'] for r in successful]
    
    total_worker_cost = sum(worker_costs)
    total_expensive_cost = sum(expensive_costs)
    total_savings = total_expensive_cost - total_worker_cost
    avg_savings_pct = sum(savings_pct) / len(savings_pct)
    avg_worker_latency = sum(worker_latencies) / len(worker_latencies)
    avg_expensive_latency = sum(expensive_latencies) / len(expensive_latencies)
    
    # Find best and worst
    best = max(successful, key=lambda x: x['savings']['percentage'])
    worst = min(successful, key=lambda x: x['savings']['percentage'])
    
    # Print results
    print("\n" + "=" * 70)
    print("CODE-WRITER EVALUATION RESULTS")
    print("=" * 70)
    
    print(f"\nFiles tested: {len(successful)} successful, {len(failed)} failed")
    print(f"Total evaluation time: {total_time:.1f}s")
    
    print("\n--- COST ANALYSIS ---")
    print(f"Total worker (Luna) cost:  ${total_worker_cost:.6f}")
    print(f"Total expensive (Sol) cost: ${total_expensive_cost:.6f}")
    print(f"Total savings:              ${total_savings:.6f}")
    print(f"Overall savings %:          {((total_savings / total_expensive_cost * 100) if total_expensive_cost > 0 else 0):.1f}%")
    print(f"Avg savings per file:       {avg_savings_pct:.1f}%")
    
    print("\n--- LATENCY ANALYSIS ---")
    print(f"Avg worker latency:    {avg_worker_latency:.1f}s")
    print(f"Avg expensive latency: {avg_expensive_latency:.1f}s")
    print(f"Latency increase:      {((avg_worker_latency - avg_expensive_latency) / avg_expensive_latency * 100):+.1f}%")
    
    print("\n--- BEST CASE ---")
    print(f"File: {best['file']} ({best['lines']} lines)")
    print(f"Savings: {best['savings']['percentage']:.1f}%")
    print(f"Worker: ${best['worker']['cost']:.6f} | Expensive: ${best['expensive']['cost']:.6f}")
    print(f"Generated: {best['worker']['code_lines']} lines ({best['worker']['code_length']} chars)")
    
    print("\n--- WORST CASE ---")
    print(f"File: {worst['file']} ({worst['lines']} lines)")
    print(f"Savings: {worst['savings']['percentage']:.1f}%")
    print(f"Worker: ${worst['worker']['cost']:.6f} | Expensive: ${worst['expensive']['cost']:.6f}")
    print(f"Generated: {worst['worker']['code_lines']} lines ({worst['worker']['code_length']} chars)")
    
    # Distribution
    print("\n--- SAVINGS DISTRIBUTION ---")
    dist = {
        "70%+": len([s for s in savings_pct if s >= 70]),
        "60-70%": len([s for s in savings_pct if 60 <= s < 70]),
        "50-60%": len([s for s in savings_pct if 50 <= s < 60]),
        "40-50%": len([s for s in savings_pct if 40 <= s < 50]),
        "<40%": len([s for s in savings_pct if s < 40]),
    }
    for label, count in dist.items():
        print(f"  {label}: {count} files ({count*100//len(successful)}%)")
    
    print("=" * 70)
    
    # Save results
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    output = {
        "test_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "repo": "Apache ShardingSphere",
        "files_tested": len(successful),
        "files_failed": len(failed),
        "config": {
            "worker_model": WORKER_MODEL,
            "expensive_model": EXPENSIVE_MODEL,
            "max_concurrent": MAX_CONCURRENT,
            "timeout": TIMEOUT
        },
        "summary": {
            "worker_cost": total_worker_cost,
            "expensive_cost": total_expensive_cost,
            "total_savings": total_savings,
            "overall_savings_pct": (total_savings / total_expensive_cost * 100) if total_expensive_cost > 0 else 0,
            "avg_savings_pct": avg_savings_pct,
            "avg_worker_latency": avg_worker_latency,
            "avg_expensive_latency": avg_expensive_latency
        },
        "best_case": {
            "file": best['file'],
            "lines": best['lines'],
            "savings_pct": best['savings']['percentage']
        },
        "worst_case": {
            "file": worst['file'],
            "lines": worst['lines'],
            "savings_pct": worst['savings']['percentage']
        },
        "results": results
    }
    
    output_path = os.path.join(RESULTS_DIR, "codewriter_eval_results.json")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
