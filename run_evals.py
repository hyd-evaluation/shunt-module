#!/usr/bin/env python3
"""
Run all evaluations
"""

import os
import sys
import unittest
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import hook_evals, code_write_eval, benchmark_evals, quality_evals


def run_all_evals():
    """Run all evaluations"""
    print("=" * 70)
    print("RUNNING ALL EVALUATIONS")
    print("=" * 70)
    
    results = {}
    
    # 1. Run hook evals
    print("\n--- HOOK EVALS ---")
    try:
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(hook_evals)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        results["hook_evals"] = {
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "success": len(result.failures) == 0 and len(result.errors) == 0
        }
    except Exception as e:
        print(f"Hook evals failed: {e}")
        results["hook_evals"] = {"error": str(e), "success": False}
    
    # 2. Run code write evals
    print("\n--- CODE WRITE EVALS ---")
    try:
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(code_write_eval)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        results["code_write_evals"] = {
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "success": len(result.failures) == 0 and len(result.errors) == 0
        }
    except Exception as e:
        print(f"Code write evals failed: {e}")
        results["code_write_evals"] = {"error": str(e), "success": False}
    
    # 3. Run benchmark evals
    print("\n--- BENCHMARK EVALS ---")
    try:
        benchmark_result = benchmark_evals.run_benchmark()
        results["benchmark_evals"] = {
            "total_savings_percentage": benchmark_result["total_savings_percentage"],
            "success": True
        }
    except Exception as e:
        print(f"Benchmark evals failed: {e}")
        results["benchmark_evals"] = {"error": str(e), "success": False}
    
    # 4. Run quality evals
    print("\n--- QUALITY EVALS ---")
    try:
        quality_result = quality_evals.run_quality_evals()
        results["quality_evals"] = {
            "average_keyword_coverage": quality_result["average_keyword_coverage"],
            "success": True
        }
    except Exception as e:
        print(f"Quality evals failed: {e}")
        results["quality_evals"] = {"error": str(e), "success": False}
    
    # Summary
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    
    all_success = all(r.get("success", False) for r in results.values())
    
    for name, result in results.items():
        status = "✓ PASS" if result.get("success") else "✗ FAIL"
        print(f"{name}: {status}")
        if "tests_run" in result:
            print(f"  Tests: {result['tests_run']}, Failures: {result['failures']}, Errors: {result['errors']}")
        if "total_savings_percentage" in result:
            print(f"  Savings: {result['total_savings_percentage']:.1f}%")
        if "average_keyword_coverage" in result:
            print(f"  Keyword coverage: {result['average_keyword_coverage']:.1f}%")
    
    print("\n" + "=" * 70)
    print(f"OVERALL: {'✓ ALL PASSED' if all_success else '✗ SOME FAILED'}")
    print("=" * 70)
    
    # Save results
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_results.json")
    with open(output_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "overall_success": all_success
        }, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")
    
    return all_success


if __name__ == "__main__":
    success = run_all_evals()
    sys.exit(0 if success else 1)
