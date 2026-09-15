#!/usr/bin/env python3
"""
Continue testing remaining files from parallel test
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
EXPENSIVE_MODEL = "codex/gpt-5.6-sol"
CHEAP_MODEL = "codex/gpt-5.6-luna"

# Pricing
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

def calculate_cost(input_tokens, output_tokens, input_price, output_price):
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000

def count_lines(file_path):
    try:
        with open(file_path, 'r', errors='ignore') as f:
            return sum(1 for _ in f)
    except:
        return 0

def read_file(file_path):
    try:
        with open(file_path, 'r', errors='ignore') as f:
            return f.read()
    except:
        return ""

def find_large_files(repo_path, min_lines=350):
    large_files = []
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith('.java'):
                file_path = os.path.join(root, file)
                lines = count_lines(file_path)
                if lines > min_lines:
                    large_files.append(file_path)
    return large_files

async def call_api(session, model, messages, max_tokens=2048, retries=MAX_RETRIES):
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
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as response:
                result = await response.json()
                if 'error' in result:
                    if attempt < retries - 1:
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    return {'error': result['error'].get('message', 'Unknown error'), 'success': False}
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

async def test_baseline(session, file_path, semaphore):
    async with semaphore:
        content = read_file(file_path)
        if not content:
            return {'file': file_path, 'success': False, 'error': 'Failed to read'}
        
        start = time.time()
        result = await call_api(session, EXPENSIVE_MODEL, [
            {"role": "user", "content": f"File:\n{content}\n\nSummarize this file."}
        ])
        latency = time.time() - start
        
        if result.get('success'):
            usage = result.get('usage', {})
            cost = calculate_cost(usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0), EXPENSIVE_INPUT_PRICE, EXPENSIVE_OUTPUT_PRICE)
            return {
                'file': file_path,
                'file_name': os.path.basename(file_path),
                'lines': content.count('\n'),
                'baseline': {'input_tokens': usage.get('prompt_tokens', 0), 'output_tokens': usage.get('completion_tokens', 0), 'cost': cost, 'latency_sec': latency, 'model': EXPENSIVE_MODEL},
                'success': True
            }
        return {'file': file_path, 'file_name': os.path.basename(file_path), 'lines': content.count('\n'), 'success': False, 'error': result.get('error')}

async def test_shunt(session, file_path, semaphore):
    async with semaphore:
        content = read_file(file_path)
        if not content:
            return {'file': file_path, 'success': False, 'error': 'Failed to read'}
        
        # Luna
        start = time.time()
        luna_result = await call_api(session, CHEAP_MODEL, [
            {"role": "user", "content": f"File:\n{content}\n\nSummarize this file."}
        ])
        luna_latency = time.time() - start
        
        if not luna_result.get('success'):
            return {'file': file_path, 'success': False, 'error': f"Luna failed: {luna_result.get('error')}"}
        
        luna_usage = luna_result.get('usage', {})
        luna_cost = calculate_cost(luna_usage.get('prompt_tokens', 0), luna_usage.get('completion_tokens', 0), CHEAP_INPUT_PRICE, CHEAP_OUTPUT_PRICE)
        summary = luna_result.get('content', '')
        
        # Sol
        start = time.time()
        sol_result = await call_api(session, EXPENSIVE_MODEL, [
            {"role": "user", "content": f"Summary:\n{summary}\n\nWhat does this file do?"}
        ])
        sol_latency = time.time() - start
        
        if not sol_result.get('success'):
            return {'file': file_path, 'success': False, 'error': f"Sol failed: {sol_result.get('error')}"}
        
        sol_usage = sol_result.get('usage', {})
        sol_cost = calculate_cost(sol_usage.get('prompt_tokens', 0), sol_usage.get('completion_tokens', 0), EXPENSIVE_INPUT_PRICE, EXPENSIVE_OUTPUT_PRICE)
        
        return {
            'file': file_path,
            'file_name': os.path.basename(file_path),
            'lines': content.count('\n'),
            'shunt': {
                'luna_input_tokens': luna_usage.get('prompt_tokens', 0),
                'luna_output_tokens': luna_usage.get('completion_tokens', 0),
                'luna_cost': luna_cost,
                'luna_latency_sec': luna_latency,
                'sol_input_tokens': sol_usage.get('prompt_tokens', 0),
                'sol_output_tokens': sol_usage.get('completion_tokens', 0),
                'sol_cost': sol_cost,
                'sol_latency_sec': sol_latency,
                'total_tokens': luna_usage.get('prompt_tokens', 0) + luna_usage.get('completion_tokens', 0) + sol_usage.get('prompt_tokens', 0) + sol_usage.get('completion_tokens', 0),
                'total_cost': luna_cost + sol_cost,
                'total_latency_sec': luna_latency + sol_latency,
                'luna_model': CHEAP_MODEL,
                'sol_model': EXPENSIVE_MODEL
            },
            'success': True
        }

async def test_file(session, file_path, semaphore):
    baseline = await test_baseline(session, file_path, semaphore)
    shunt = await test_shunt(session, file_path, semaphore)
    
    if baseline.get('success') and shunt.get('success'):
        baseline_cost = baseline['baseline']['cost']
        shunt_cost = shunt['shunt']['total_cost']
        savings = ((baseline_cost - shunt_cost) / baseline_cost * 100) if baseline_cost > 0 else 0
        baseline_latency = baseline['baseline']['latency_sec']
        shunt_latency = shunt['shunt']['total_latency_sec']
        latency_change = ((shunt_latency - baseline_latency) / baseline_latency * 100) if baseline_latency > 0 else 0
        
        return {
            'file': file_path,
            'file_name': baseline['file_name'],
            'lines': baseline['lines'],
            'baseline': baseline['baseline'],
            'shunt': shunt['shunt'],
            'cost_savings_pct': savings,
            'latency_change_pct': latency_change,
            'success': True
        }
    else:
        return {
            'file': file_path,
            'file_name': baseline.get('file_name', os.path.basename(file_path)),
            'lines': baseline.get('lines', 0),
            'success': False,
            'error': baseline.get('error') or shunt.get('error')
        }

async def main():
    print("="*70)
    print("CONTINUING TEST - REMAINING FILES")
    print("="*70)
    
    # Load already tested files
    with open(f'{RESULTS_DIR}/parallel_test_results.json') as f:
        data = json.load(f)
    
    tested_files = set(r['file'] for r in data['results'])
    print(f"Already tested: {len(tested_files)} files")
    
    # Find all large files
    all_files = find_large_files(REPO_PATH, MIN_LINES)
    remaining = [f for f in all_files if f not in tested_files]
    print(f"Remaining files: {len(remaining)}")
    
    if not remaining:
        print("No remaining files. Done.")
        return
    
    # Sort by size
    remaining.sort(key=lambda f: count_lines(f))
    print(f"File size range: {min(count_lines(f) for f in remaining)} - {max(count_lines(f) for f in remaining)} lines")
    
    # Run tests
    print(f"\nStarting parallel test ({MAX_CONCURRENT} concurrent)...")
    start_time = time.time()
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)
    
    new_results = []
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_file(session, f, semaphore) for f in remaining]
        
        completed = 0
        total = len(tasks)
        
        for coro in asyncio.as_completed(tasks):
            result = await coro
            new_results.append(result)
            completed += 1
            
            if completed % 10 == 0 or completed == total:
                successful = len([r for r in new_results if r.get('success')])
                print(f"  Progress: {completed}/{total} ({completed*100//total}%) - {successful} successful")
                
                # Save intermediate
                all_results = data['results'] + new_results
                with open(f'{RESULTS_DIR}/parallel_test_results.json', 'w') as f:
                    json.dump({
                        'test_date': data['test_date'],
                        'repo': data['repo'],
                        'models': data['models'],
                        'config': data['config'],
                        'summary': {'total_files': len(all_results), 'successful_files': len([r for r in all_results if r.get('success')])},
                        'results': all_results
                    }, f, indent=2)
    
    total_time = time.time() - start_time
    print(f"\nTotal test time: {total_time:.1f}s ({total_time/60:.1f} min)")
    
    # Combine all results
    all_results = data['results'] + new_results
    
    # Save final results
    successful = [r for r in all_results if r.get('success')]
    failed = [r for r in all_results if not r.get('success')]
    
    total_baseline = sum(r['baseline']['cost'] for r in successful)
    total_shunt = sum(r['shunt']['total_cost'] for r in successful)
    avg_baseline_latency = sum(r['baseline']['latency_sec'] for r in successful) / len(successful)
    avg_shunt_latency = sum(r['shunt']['total_latency_sec'] for r in successful) / len(successful)
    avg_savings = sum(r['cost_savings_pct'] for r in successful) / len(successful)
    avg_latency_change = sum(r['latency_change_pct'] for r in successful) / len(successful)
    
    final_data = {
        'test_date': data['test_date'],
        'repo': data['repo'],
        'models': data['models'],
        'config': data['config'],
        'summary': {
            'total_files': len(all_results),
            'successful_files': len(successful),
            'failed_files': len(failed),
            'baseline': {'total_cost': total_baseline, 'avg_latency_sec': avg_baseline_latency},
            'shunt': {'total_cost': total_shunt, 'avg_latency_sec': avg_shunt_latency},
            'savings': {
                'total_cost_savings': total_baseline - total_shunt,
                'cost_savings_pct': ((total_baseline - total_shunt) / total_baseline * 100) if total_baseline > 0 else 0,
                'avg_cost_savings_pct': avg_savings,
                'avg_latency_change_pct': avg_latency_change
            }
        },
        'results': all_results
    }
    
    with open(f'{RESULTS_DIR}/parallel_test_results.json', 'w') as f:
        json.dump(final_data, f, indent=2)
    
    print(f"\nResults saved to {RESULTS_DIR}/parallel_test_results.json")
    print(f"\n{'='*70}")
    print(f"FINAL RESULTS ({len(all_results)} files)")
    print(f"{'='*70}")
    print(f"Total baseline cost: ${total_baseline:.4f}")
    print(f"Total shunt cost:    ${total_shunt:.4f}")
    print(f"Total savings:       ${total_baseline - total_shunt:.4f}")
    print(f"Overall savings %:   {((total_baseline - total_shunt) / total_baseline * 100):.1f}%")
    print(f"Avg savings/file:    {avg_savings:.1f}%")
    print(f"Avg latency change:  {avg_latency_change:+.1f}%")
    print(f"{'='*70}")

if __name__ == "__main__":
    asyncio.run(main())
