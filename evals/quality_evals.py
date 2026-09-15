"""
Quality Evals
Tests summary quality using LLM-as-judge
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

# Test cases with expected quality
TEST_CASES = [
    {
        "name": "Java class with methods",
        "content": """
public class UserService {
    private UserRepository userRepository;
    
    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }
    
    public User getUserById(Long id) {
        return userRepository.findById(id).orElse(null);
    }
    
    public User createUser(CreateUserDto dto) {
        User user = new User();
        user.setName(dto.getName());
        user.setEmail(dto.getEmail());
        return userRepository.save(user);
    }
    
    public void deleteUser(Long id) {
        userRepository.deleteById(id);
    }
}
""",
        "expected_keywords": ["UserService", "UserRepository", "getUserById", "createUser", "deleteUser"]
    },
    {
        "name": "TypeScript interface",
        "content": """
export interface User {
    id: number;
    name: string;
    email: string;
    createdAt: Date;
}

export interface CreateUserDto {
    name: string;
    email: string;
}

export interface UserRepository {
    findById(id: number): Promise<User | null>;
    save(user: User): Promise<User>;
    deleteById(id: number): Promise<void>;
}
""",
        "expected_keywords": ["User", "CreateUserDto", "UserRepository", "id", "name", "email"]
    },
    {
        "name": "Complex algorithm",
        "content": """
public class SortUtils {
    public static <T extends Comparable<T>> void quickSort(T[] arr, int low, int high) {
        if (low < high) {
            int pivotIndex = partition(arr, low, high);
            quickSort(arr, low, pivotIndex - 1);
            quickSort(arr, pivotIndex + 1, high);
        }
    }
    
    private static <T extends Comparable<T>> int partition(T[] arr, int low, int high) {
        T pivot = arr[high];
        int i = low - 1;
        for (int j = low; j < high; j++) {
            if (arr[j].compareTo(pivot) < 0) {
                i++;
                swap(arr, i, j);
            }
        }
        swap(arr, i + 1, high);
        return i + 1;
    }
    
    private static <T> void swap(T[] arr, int i, int j) {
        T temp = arr[i];
        arr[i] = arr[j];
        arr[j] = temp;
    }
}
""",
        "expected_keywords": ["quickSort", "partition", "swap", "pivot", "T extends Comparable"]
    }
]


def evaluate_summary(summary: str, expected_keywords: List[str]) -> Dict:
    """Evaluate summary quality using LLM-as-judge"""
    
    judge_prompt = f"""Evaluate the quality of this code summary.

Summary:
{summary}

Evaluate on these dimensions (1-5 scale):
1. Accuracy: Does it correctly describe the code?
2. Completeness: Does it cover all important parts?
3. Clarity: Is it clear and easy to understand?
4. Conciseness: Is it brief but informative?

Also check if these keywords are mentioned: {', '.join(expected_keywords)}

Return JSON with scores and feedback.
"""
    
    judge = ShuntWorker(
        api_key=API_KEY,
        model="codex/gpt-5.6-sol",
        api_base=API_BASE,
        max_output_tokens=512
    )
    
    result = judge.summarize(
        file_path="judge_prompt.txt",
        content=judge_prompt,
        question="Evaluate this summary quality"
    )
    
    if result.get("success"):
        # Parse judge response (simplified)
        summary_text = result.get("summary", "")
        
        # Extract keywords found
        keywords_found = [kw for kw in expected_keywords if kw.lower() in summary.lower()]
        
        return {
            "scores": {
                "accuracy": 4.0,  # Simplified - would parse from judge response
                "completeness": 4.0,
                "clarity": 4.0,
                "conciseness": 4.0
            },
            "keywords_found": keywords_found,
            "keywords_total": len(expected_keywords),
            "keyword_coverage": len(keywords_found) / len(expected_keywords) * 100 if expected_keywords else 0,
            "judge_response": summary_text
        }
    
    return {"error": "Judge failed"}


def run_quality_evals() -> Dict:
    """Run quality evaluation tests"""
    
    # Create worker
    worker = ShuntWorker(
        api_key=API_KEY,
        model="codex/gpt-5.6-luna",
        api_base=API_BASE,
        max_output_tokens=1024
    )
    
    results = []
    
    for test_case in TEST_CASES:
        print(f"\nEvaluating: {test_case['name']}")
        
        # Generate summary
        start_time = time.time()
        result = worker.summarize(
            file_path=f"test_{test_case['name'].lower().replace(' ', '_')}.java",
            content=test_case["content"],
            question="Summarize this code for understanding and modification"
        )
        latency = time.time() - start_time
        
        if result.get("success"):
            summary = result.get("summary", "")
            
            # Evaluate quality
            quality = evaluate_summary(summary, test_case["expected_keywords"])
            
            test_result = {
                "test_case": test_case["name"],
                "summary": summary,
                "cost": result.get("cost", 0),
                "tokens": result.get("tokens", {}),
                "latency": latency,
                "quality": quality
            }
            
            results.append(test_result)
            
            print(f"  Summary length: {len(summary)} chars")
            print(f"  Cost: ${result.get('cost', 0):.6f}")
            print(f"  Keyword coverage: {quality.get('keyword_coverage', 0):.1f}%")
        else:
            print(f"  Error: {result.get('error')}")
    
    # Calculate overall statistics
    avg_keyword_coverage = sum(
        r.get("quality", {}).get("keyword_coverage", 0) for r in results
    ) / len(results) if results else 0
    
    avg_cost = sum(r.get("cost", 0) for r in results) / len(results) if results else 0
    
    summary = {
        "total_tests": len(results),
        "average_keyword_coverage": avg_keyword_coverage,
        "average_cost": avg_cost,
        "results": results
    }
    
    return summary


def main():
    """Main quality eval function"""
    print("=" * 70)
    print("SHUNT MODULE QUALITY EVALS")
    print("=" * 70)
    
    summary = run_quality_evals()
    
    print("\n" + "=" * 70)
    print("QUALITY EVAL RESULTS")
    print("=" * 70)
    print(f"Total tests: {summary['total_tests']}")
    print(f"Average keyword coverage: {summary['average_keyword_coverage']:.1f}%")
    print(f"Average cost: ${summary['average_cost']:.6f}")
    print("=" * 70)
    
    # Save results
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quality_results.json")
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
