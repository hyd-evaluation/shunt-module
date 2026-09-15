"""
Benchmark Evals
Measures token cost savings across different scenarios
"""

import json
import os
import sys
import time
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker import ShuntWorker, calculate_cost

API_KEY = os.environ.get("NEUSIS_API_KEY", "sk-55100efb9fb4a726-62bfab-89db8b81")
API_BASE = "https://pbtest.neusis.ai/router/v1"

# Test scenarios
SCENARIOS = [
    {
        "name": "Single large file",
        "lines": 500,
        "description": "Read and summarize a single large Java file"
    },
    {
        "name": "Multiple files",
        "lines": 1000,
        "description": "Read and summarize multiple Java files"
    },
    {
        "name": "Code generation",
        "lines": 200,
        "description": "Generate boilerplate code from reference"
    },
    {
        "name": "Cross-service analysis",
        "lines": 1500,
        "description": "Analyze code across multiple services"
    }
]


def run_benchmark() -> Dict:
    """Run benchmark tests and return results"""
    
    # Create workers
    luna_worker = ShuntWorker(
        api_key=API_KEY,
        model="codex/gpt-5.6-luna",
        api_base=API_BASE,
        max_output_tokens=1024
    )
    
    sol_worker = ShuntWorker(
        api_key=API_KEY,
        model="codex/gpt-5.6-sol",
        api_base=API_BASE,
        max_output_tokens=1024
    )
    
    results = []
    
    for scenario in SCENARIOS:
        print(f"\nRunning scenario: {scenario['name']}")
        
        # Generate test content
        content = f"// Test file with {scenario['lines']} lines\n"
        content += "// " + "x" * 100 + "\n" * scenario["lines"]
        
        # Test with Luna (cheap)
        luna_start = time.time()
        luna_result = luna_worker.summarize(
            file_path=f"test_{scenario['name'].lower().replace(' ', '_')}.java",
            content=content,
            question="Summarize this file for code analysis"
        )
        luna_time = time.time() - luna_start
        
        # Test with Sol (expensive)
        sol_start = time.time()
        sol_result = sol_worker.summarize(
            file_path=f"test_{scenario['name'].lower().replace(' ', '_')}.java",
            content=content,
            question="Summarize this file for code analysis"
        )
        sol_time = time.time() - sol_start
        
        # Calculate savings
        luna_cost = luna_result.get("cost", 0)
        sol_cost = sol_result.get("cost", 0)
        savings = sol_cost - luna_cost
        savings_pct = (savings / sol_cost * 100) if sol_cost > 0 else 0
        
        scenario_result = {
            "scenario": scenario["name"],
            "description": scenario["description"],
            "lines": scenario["lines"],
            "luna": {
                "cost": luna_cost,
                "tokens": luna_result.get("tokens", {}),
                "latency": luna_time
            },
            "sol": {
                "cost": sol_cost,
                "tokens": sol_result.get("tokens", {}),
                "latency": sol_time
            },
            "savings": {
                "cost": savings,
                "percentage": savings_pct
            }
        }
        
        results.append(scenario_result)
        
        print(f"  Luna cost: ${luna_cost:.6f}")
        print(f"  Sol cost: ${sol_cost:.6f}")
        print(f"  Savings: ${savings:.6f} ({savings_pct:.1f}%)")
    
    # Calculate overall statistics
    total_luna_cost = sum(r["luna"]["cost"] for r in results)
    total_sol_cost = sum(r["sol"]["cost"] for r in results)
    total_savings = total_sol_cost - total_luna_cost
    total_savings_pct = (total_savings / total_sol_cost * 100) if total_sol_cost > 0 else 0
    
    summary = {
        "total_scenarios": len(results),
        "total_luna_cost": total_luna_cost,
        "total_sol_cost": total_sol_cost,
        "total_savings": total_savings,
        "total_savings_percentage": total_savings_pct,
        "avg_savings_per_scenario": total_savings / len(results) if results else 0,
        "scenarios": results
    }
    
    return summary


def main():
    """Main benchmark function"""
    print("=" * 70)
    print("SHUNT MODULE BENCHMARK")
    print("=" * 70)
    
    summary = run_benchmark()
    
    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Total scenarios: {summary['total_scenarios']}")
    print(f"Total Luna cost: ${summary['total_luna_cost']:.6f}")
    print(f"Total Sol cost: ${summary['total_sol_cost']:.6f}")
    print(f"Total savings: ${summary['total_savings']:.6f}")
    print(f"Overall savings: {summary['total_savings_percentage']:.1f}%")
    print("=" * 70)
    
    # Save results
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_results.json")
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
