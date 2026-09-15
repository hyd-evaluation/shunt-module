#!/usr/bin/env python3
"""
Parallel Shunt Test Runner
Tests shunt module on 195+ Java files using concurrent API calls
"""

import asyncio
import aiohttp
import json
import os
import time
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# Try importing tqdm for progress bar
try:
    from tqdm.asyncio import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("tqdm not available, using simple progress tracking")

# ============================================================
# Configuration
# ============================================================

API_KEY = "sk-55100efb9fb4a726-62bfab-89db8b81"
API_BASE = "https://pbtest.neusis.ai/router/v1"

EXPENSIVE_MODEL = "codex/gpt-5.6-sol"
CHEAP_MODEL = "codex/gpt-5.6-luna"

# Pricing (per 1M tokens)
EXPENSIVE_INPUT_PRICE = 2.50
EXPENSIVE_OUTPUT_PRICE = 15.00
CHEAP_INPUT_PRICE = 1.00
CHEAP_OUTPUT_PRICE = 6.00

REPO_PATH = "/home/varun/shardingsphere"
MIN_LINES = 350
MAX_CONCURRENT = 10
MAX_RETRIES = 3
TIMEOUT = 180
RESULTS_DIR = "/home/varun/shunt-module/results"

# ============================================================
# Utility Functions
# ============================================================

def calculate_cost(input_tokens: int, output_tokens: int, input_price: float, output_price: float) -> float:
    """Calculate cost in dollars"""
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000

def count_lines(file_path: str) -> int:
    """Count lines in a file"""
    try:
        with open(file_path, 'r', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def read_file(file_path: str) -> str:
    """Read file content"""
    try:
        with open(file_path, 'r', errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return ""

def find_large_files(repo_path: str, min_lines: int = 350) -> List[str]:
    """Find all Java files with more than min_lines"""
    large_files = []
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith('.java'):
                file_path = os.path.join(root, file)
                lines = count_lines(file_path)
                if lines > min_lines:
                    large_files.append(file_path)
    return large_files

# ============================================================
# API Functions
# ============================================================

async def call_api(
    session: aiohttp.ClientSession,
    model: str,
    messages: List[Dict],
    max_tokens: int = 2048,
    retries: int = MAX_RETRIES
) -> Dict[str, Any]:
    """Call the Neusis Router API with retries"""
    for attempt in range(retries):
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "max_tokens": max_tokens,
                "temperature": 0.2
            }
            
            async with session.post(
                f"{API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as response:
                result = await response.json()
                
                if 'error' in result:
                    error_msg = result['error'].get('message', 'Unknown error')
                    if attempt < retries - 1:
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    return {'error': error_msg, 'success': False}
                
                return {
                    'content': result.get('choices', [{}])[0].get('message', {}).get('content', ''),
                    'usage': result.get('usage', {}),
                    'success': True
                }
                
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(3 * (attempt + 1))
                continue
            return {'error': str(e), 'success': False}
    
    return {'error': 'Max retries exceeded', 'success': False}

# ============================================================
# Test Functions
# ============================================================

async def test_baseline(
    session: aiohttp.ClientSession,
    file_path: str,
    semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    """Test baseline (expensive model reads file directly)"""
    async with semaphore:
        file_name = os.path.basename(file_path)
        content = read_file(file_path)
        lines = content.count('\n')
        
        if not content:
            return {
                'file': file_path,
                'file_name': file_name,
                'lines': lines,
                'success': False,
                'error': 'Failed to read file'
            }
        
        start_time = time.time()
        
        messages = [{"role": "user", "content": f"File:\n{content}\n\nProvide a structured summary covering key classes, methods, and responsibilities."}]
        
        result = await call_api(session, EXPENSIVE_MODEL, messages)
        
        latency = time.time() - start_time
        
        if result.get('success'):
            usage = result.get('usage', {})
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)
            cost = calculate_cost(input_tokens, output_tokens, EXPENSIVE_INPUT_PRICE, EXPENSIVE_OUTPUT_PRICE)
            
            return {
                'file': file_path,
                'file_name': file_name,
                'lines': lines,
                'baseline': {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': input_tokens + output_tokens,
                    'cost': cost,
                    'latency_sec': latency,
                    'model': EXPENSIVE_MODEL
                },
                'success': True
            }
        else:
            return {
                'file': file_path,
                'file_name': file_name,
                'lines': lines,
                'success': False,
                'error': result.get('error', 'Unknown error')
            }

async def test_shunt(
    session: aiohttp.ClientSession,
    file_path: str,
    semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    """Test shunt (cheap summarizes, then expensive answers)"""
    async with semaphore:
        file_name = os.path.basename(file_path)
        content = read_file(file_path)
        lines = content.count('\n')
        
        if not content:
            return {
                'file': file_path,
                'file_name': file_name,
                'lines': lines,
                'success': False,
                'error': 'Failed to read file'
            }
        
        # Step 1: Cheap model summarizes
        luna_start = time.time()
        
        luna_messages = [{"role": "user", "content": f"File:\n{content}\n\nProvide a structured summary covering key classes, methods, and responsibilities."}]
        
        luna_result = await call_api(session, CHEAP_MODEL, luna_messages)
        
        luna_latency = time.time() - luna_start
        
        if not luna_result.get('success'):
            return {
                'file': file_path,
                'file_name': file_name,
                'lines': lines,
                'success': False,
                'error': f"Luna failed: {luna_result.get('error', 'Unknown error')}"
            }
        
        luna_usage = luna_result.get('usage', {})
        luna_input = luna_usage.get('prompt_tokens', 0)
        luna_output = luna_usage.get('completion_tokens', 0)
        luna_cost = calculate_cost(luna_input, luna_output, CHEAP_INPUT_PRICE, CHEAP_OUTPUT_PRICE)
        summary = luna_result.get('content', '')
        
        # Step 2: Expensive model answers from summary
        sol_start = time.time()
        
        sol_messages = [{"role": "user", "content": f"Summary:\n{summary}\n\nWhat are the key classes and their responsibilities in this code?"}]
        
        sol_result = await call_api(session, EXPENSIVE_MODEL, sol_messages)
        
        sol_latency = time.time() - sol_start
        
        if not sol_result.get('success'):
            return {
                'file': file_path,
                'file_name': file_name,
                'lines': lines,
                'success': False,
                'error': f"Sol failed: {sol_result.get('error', 'Unknown error')}"
            }
        
        sol_usage = sol_result.get('usage', {})
        sol_input = sol_usage.get('prompt_tokens', 0)
        sol_output = sol_usage.get('completion_tokens', 0)
        sol_cost = calculate_cost(sol_input, sol_output, EXPENSIVE_INPUT_PRICE, EXPENSIVE_OUTPUT_PRICE)
        
        total_cost = luna_cost + sol_cost
        total_latency = luna_latency + sol_latency
        total_tokens = luna_input + luna_output + sol_input + sol_output
        
        return {
            'file': file_path,
            'file_name': file_name,
            'lines': lines,
            'shunt': {
                'luna_input_tokens': luna_input,
                'luna_output_tokens': luna_output,
                'luna_cost': luna_cost,
                'luna_latency_sec': luna_latency,
                'sol_input_tokens': sol_input,
                'sol_output_tokens': sol_output,
                'sol_cost': sol_cost,
                'sol_latency_sec': sol_latency,
                'total_tokens': total_tokens,
                'total_cost': total_cost,
                'total_latency_sec': total_latency,
                'luna_model': CHEAP_MODEL,
                'sol_model': EXPENSIVE_MODEL
            },
            'success': True
        }

async def test_file(
    session: aiohttp.ClientSession,
    file_path: str,
    semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    """Run both baseline and shunt tests on a file"""
    # Run baseline
    baseline_result = await test_baseline(session, file_path, semaphore)
    
    # Run shunt
    shunt_result = await test_shunt(session, file_path, semaphore)
    
    # Combine results
    if baseline_result.get('success') and shunt_result.get('success'):
        baseline_cost = baseline_result['baseline']['cost']
        shunt_cost = shunt_result['shunt']['total_cost']
        cost_savings = ((baseline_cost - shunt_cost) / baseline_cost * 100) if baseline_cost > 0 else 0
        
        baseline_latency = baseline_result['baseline']['latency_sec']
        shunt_latency = shunt_result['shunt']['total_latency_sec']
        latency_change = ((shunt_latency - baseline_latency) / baseline_latency * 100) if baseline_latency > 0 else 0
        
        return {
            'file': file_path,
            'file_name': baseline_result['file_name'],
            'lines': baseline_result['lines'],
            'baseline': baseline_result['baseline'],
            'shunt': shunt_result['shunt'],
            'cost_savings_pct': cost_savings,
            'latency_change_pct': latency_change,
            'success': True
        }
    else:
        error = baseline_result.get('error') or shunt_result.get('error')
        return {
            'file': file_path,
            'file_name': baseline_result.get('file_name', os.path.basename(file_path)),
            'lines': baseline_result.get('lines', 0),
            'success': False,
            'error': error
        }

# ============================================================
# Main Runner
# ============================================================

async def run_parallel_test(
    files: List[str],
    max_concurrent: int = MAX_CONCURRENT
) -> List[Dict[str, Any]]:
    """Run parallel tests on all files"""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    connector = aiohttp.TCPConnector(limit=max_concurrent, limit_per_host=max_concurrent)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_file(session, f, semaphore) for f in files]
        
        results = []
        completed = 0
        total = len(tasks)
        
        if HAS_TQDM:
            for coro in tqdm.as_completed(tasks, total=total, desc="Testing files"):
                result = await coro
                results.append(result)
                completed += 1
                
                # Save intermediate results every 10 files
                if completed % 10 == 0:
                    save_results(results)
        else:
            for i, coro in enumerate(tasks):
                result = await coro
                results.append(result)
                completed += 1
                
                # Progress update
                if completed % 10 == 0 or completed == total:
                    print(f"  Progress: {completed}/{total} files ({completed*100//total}%)")
                
                # Save intermediate results every 10 files
                if completed % 10 == 0:
                    save_results(results)
        
        return results

def save_results(results: List[Dict], filename: str = "parallel_test_results.json"):
    """Save results to file"""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    filepath = os.path.join(RESULTS_DIR, filename)
    
    # Calculate summary statistics
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    if successful:
        total_baseline_cost = sum(r['baseline']['cost'] for r in successful)
        total_shunt_cost = sum(r['shunt']['total_cost'] for r in successful)
        avg_baseline_latency = sum(r['baseline']['latency_sec'] for r in successful) / len(successful)
        avg_shunt_latency = sum(r['shunt']['total_latency_sec'] for r in successful) / len(successful)
        avg_cost_savings = sum(r['cost_savings_pct'] for r in successful) / len(successful)
        avg_latency_change = sum(r['latency_change_pct'] for r in successful) / len(successful)
        
        summary = {
            'total_files': len(results),
            'successful_files': len(successful),
            'failed_files': len(failed),
            'baseline': {
                'total_cost': total_baseline_cost,
                'avg_latency_sec': avg_baseline_latency
            },
            'shunt': {
                'total_cost': total_shunt_cost,
                'avg_latency_sec': avg_shunt_latency
            },
            'savings': {
                'total_cost_savings': total_baseline_cost - total_shunt_cost,
                'cost_savings_pct': ((total_baseline_cost - total_shunt_cost) / total_baseline_cost * 100) if total_baseline_cost > 0 else 0,
                'avg_cost_savings_pct': avg_cost_savings,
                'avg_latency_change_pct': avg_latency_change
            }
        }
    else:
        summary = {'error': 'No successful tests'}
    
    output = {
        'test_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'repo': 'Apache ShardingSphere',
        'models': {
            'expensive': EXPENSIVE_MODEL,
            'cheap': CHEAP_MODEL
        },
        'config': {
            'max_concurrent': MAX_CONCURRENT,
            'min_lines': MIN_LINES,
            'timeout': TIMEOUT
        },
        'summary': summary,
        'results': results
    }
    
    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: {filepath}")

def generate_final_report(results: List[Dict]):
    """Generate comprehensive final report"""
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    if not successful:
        print("No successful tests to report")
        return
    
    # Calculate statistics
    baseline_costs = [r['baseline']['cost'] for r in successful]
    shunt_costs = [r['shunt']['total_cost'] for r in successful]
    baseline_latencies = [r['baseline']['latency_sec'] for r in successful]
    shunt_latencies = [r['shunt']['total_latency_sec'] for r in successful]
    cost_savings = [r['cost_savings_pct'] for r in successful]
    latency_changes = [r['latency_change_pct'] for r in successful]
    
    total_baseline_cost = sum(baseline_costs)
    total_shunt_cost = sum(shunt_costs)
    avg_baseline_latency = sum(baseline_latencies) / len(baseline_latencies)
    avg_shunt_latency = sum(shunt_latencies) / len(shunt_latencies)
    
    # Find best and worst cases
    best_cost_savings = max(cost_savings)
    worst_cost_savings = min(cost_savings)
    best_file = next(r for r in successful if r['cost_savings_pct'] == best_cost_savings)
    worst_file = next(r for r in successful if r['cost_savings_pct'] == worst_cost_savings)
    
    print(f"\n{'='*70}")
    print(f"PARALLEL SHUNT TEST - FINAL REPORT")
    print(f"{'='*70}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Repo: Apache ShardingSphere")
    print(f"Files tested: {len(successful)} successful, {len(failed)} failed")
    print(f"Concurrency: {MAX_CONCURRENT} parallel API calls")
    print(f"{'='*70}")
    
    print(f"\n--- COST ANALYSIS ---")
    print(f"Total baseline cost:  ${total_baseline_cost:.6f}")
    print(f"Total shunt cost:     ${total_shunt_cost:.6f}")
    print(f"Total savings:        ${total_baseline_cost - total_shunt_cost:.6f}")
    print(f"Overall savings %:    {((total_baseline_cost - total_shunt_cost) / total_baseline_cost * 100):.1f}%")
    print(f"Avg savings per file: {sum(cost_savings) / len(cost_savings):.1f}%")
    
    print(f"\n--- LATENCY ANALYSIS ---")
    print(f"Avg baseline latency: {avg_baseline_latency:.1f}s")
    print(f"Avg shunt latency:    {avg_shunt_latency:.1f}s")
    print(f"Avg latency change:   {sum(latency_changes) / len(latency_changes):+.1f}%")
    
    print(f"\n--- BEST CASE ---")
    print(f"File: {best_file['file_name']} ({best_file['lines']} lines)")
    print(f"Cost savings: {best_cost_savings:.1f}%")
    print(f"Baseline: ${best_file['baseline']['cost']:.6f} | Shunt: ${best_file['shunt']['total_cost']:.6f}")
    
    print(f"\n--- WORST CASE ---")
    print(f"File: {worst_file['file_name']} ({worst_file['lines']} lines)")
    print(f"Cost savings: {worst_cost_savings:.1f}%")
    print(f"Baseline: ${worst_file['baseline']['cost']:.6f} | Shunt: ${worst_file['shunt']['total_cost']:.6f}")
    
    print(f"\n--- DISTRIBUTION ---")
    savings_ranges = [
        ("30%+ savings", len([s for s in cost_savings if s >= 30])),
        ("20-30% savings", len([s for s in cost_savings if 20 <= s < 30])),
        ("10-20% savings", len([s for s in cost_savings if 10 <= s < 20])),
        ("0-10% savings", len([s for s in cost_savings if 0 <= s < 10])),
        ("Negative (cost increase)", len([s for s in cost_savings if s < 0])),
    ]
    for label, count in savings_ranges:
        print(f"  {label}: {count} files ({count*100//len(successful)}%)")
    
    print(f"\n{'='*70}")
    
    # Save final report
    final_report = {
        'test_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'repo': 'Apache ShardingSphere',
        'files_tested': len(successful),
        'concurrency': MAX_CONCURRENT,
        'models': {
            'expensive': EXPENSIVE_MODEL,
            'cheap': CHEAP_MODEL
        },
        'summary': {
            'baseline': {
                'total_cost': total_baseline_cost,
                'avg_latency_sec': avg_baseline_latency
            },
            'shunt': {
                'total_cost': total_shunt_cost,
                'avg_latency_sec': avg_shunt_latency
            },
            'savings': {
                'total_cost_savings': total_baseline_cost - total_shunt_cost,
                'cost_savings_pct': ((total_baseline_cost - total_shunt_cost) / total_baseline_cost * 100) if total_baseline_cost > 0 else 0,
                'avg_cost_savings_pct': sum(cost_savings) / len(cost_savings),
                'avg_latency_change_pct': sum(latency_changes) / len(latency_changes)
            },
            'best_case': {
                'file': best_file['file_name'],
                'lines': best_file['lines'],
                'savings_pct': best_cost_savings
            },
            'worst_case': {
                'file': worst_file['file_name'],
                'lines': worst_file['lines'],
                'savings_pct': worst_cost_savings
            }
        }
    }
    
    report_path = os.path.join(RESULTS_DIR, "FINAL_REPORT.json")
    with open(report_path, 'w') as f:
        json.dump(final_report, f, indent=2)
    
    print(f"Final report saved to: {report_path}")

# ============================================================
# Entry Point
# ============================================================

def main():
    print("="*70)
    print("PARALLEL SHUNT TEST RUNNER")
    print("="*70)
    print(f"Repo: {REPO_PATH}")
    print(f"Min lines: {MIN_LINES}")
    print(f"Max concurrent: {MAX_CONCURRENT}")
    print(f"Models: {EXPENSIVE_MODEL} (expensive), {CHEAP_MODEL} (cheap)")
    print("="*70)
    
    # Find large files
    print(f"\nScanning for Java files > {MIN_LINES} lines...")
    files = find_large_files(REPO_PATH, MIN_LINES)
    print(f"Found {len(files)} files to test")
    
    if not files:
        print("No files found. Exiting.")
        return
    
    # Show file size distribution
    lines_count = [count_lines(f) for f in files]
    print(f"File size range: {min(lines_count)} - {max(lines_count)} lines")
    print(f"Average file size: {sum(lines_count) // len(lines_count)} lines")
    
    # Run parallel test
    print(f"\nStarting parallel test ({MAX_CONCURRENT} concurrent)...")
    start_time = time.time()
    
    results = asyncio.run(run_parallel_test(files, MAX_CONCURRENT))
    
    total_time = time.time() - start_time
    print(f"\nTotal test time: {total_time:.1f}s ({total_time/60:.1f} min)")
    
    # Save results
    save_results(results)
    
    # Generate report
    generate_final_report(results)

if __name__ == "__main__":
    main()
