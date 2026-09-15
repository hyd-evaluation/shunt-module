"""
Code Write Evals
Tests boilerplate code generation
"""

import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from code_writer import ShuntCodeWriter


class TestCodeWriteEvals(unittest.TestCase):
    """Test code generation evaluation"""
    
    def setUp(self):
        self.api_key = os.environ.get("NEUSIS_API_KEY", "sk-55100efb9fb4a726-62bfab-89db8b81")
        self.writer = ShuntCodeWriter(
            api_key=self.api_key,
            worker_model="codex/gpt-5.6-luna",
            expensive_model="codex/gpt-5.6-sol"
        )
        
        # Create test reference files
        self._create_test_files()
    
    def tearDown(self):
        # Clean up test files
        self._remove_test_files()
    
    def _create_test_files(self):
        """Create test reference files"""
        os.makedirs("/tmp/shunt_eval", exist_ok=True)
        
        # Java test reference
        with open("/tmp/shunt_eval/OrderTest.java", "w") as f:
            f.write("""
package com.example;

import org.junit.Test;
import static org.junit.Assert.*;

public class OrderTest {
    @Test
    public void testOrderCreation() {
        Order order = new Order();
        order.setId(1);
        assertEquals(1, order.getId());
    }
    
    @Test
    public void testOrderTotal() {
        Order order = new Order();
        order.addItem(new Item("A", 10.0));
        order.addItem(new Item("B", 20.0));
        assertEquals(30.0, order.getTotal(), 0.001);
    }
}
""")
        
        # TypeScript reference
        with open("/tmp/shunt_eval/UserService.ts", "w") as f:
            f.write("""
export class UserService {
    private users: Map<number, User> = new Map();
    
    async getUser(id: number): Promise<User | null> {
        return this.users.get(id) || null;
    }
    
    async createUser(data: CreateUserDto): Promise<User> {
        const user = new User(data);
        this.users.set(user.id, user);
        return user;
    }
}
""")
    
    def _remove_test_files(self):
        """Remove test files"""
        import shutil
        if os.path.exists("/tmp/shunt_eval"):
            shutil.rmtree("/tmp/shunt_eval")
    
    def test_java_test_generation(self):
        """Test: Generate Java tests from reference"""
        result = self.writer.generate(
            spec="Write tests for UserService",
            reference_path="/tmp/shunt_eval/OrderTest.java"
        )
        
        self.assertTrue(result["success"])
        self.assertGreater(len(result["code"]), 0)
        self.assertGreater(result["cost"], 0)
        self.assertGreater(result["latency"], 0)
        
        # Check that code contains test patterns
        code = result["code"]
        self.assertTrue(
            "@Test" in code or "test" in code.lower(),
            "Generated code should contain test patterns"
        )
    
    def test_typescript_generation(self):
        """Test: Generate TypeScript from reference"""
        result = self.writer.generate(
            spec="Write tests for UserService",
            reference_path="/tmp/shunt_eval/UserService.ts"
        )
        
        self.assertTrue(result["success"])
        self.assertGreater(len(result["code"]), 0)
    
    def test_estimated_savings(self):
        """Test: Estimate cost savings"""
        estimate = self.writer.estimate_savings(
            spec="Write tests for UserService",
            reference_path="/tmp/shunt_eval/OrderTest.java"
        )
        
        self.assertIn("worker_cost", estimate)
        self.assertIn("expensive_cost", estimate)
        self.assertIn("estimated_savings_pct", estimate)
        self.assertGreater(estimate["estimated_savings_pct"], 0)
    
    def test_markdown_fence_stripping(self):
        """Test: Markdown fences should be stripped from output"""
        result = self.writer.generate(
            spec="Write a simple function",
            reference_path="/tmp/shunt_eval/OrderTest.java"
        )
        
        self.assertTrue(result["success"])
        # Code should not contain markdown fences
        self.assertNotIn("```java", result["code"])
        self.assertNotIn("```typescript", result["code"])
    
    def test_file_write(self):
        """Test: Code should be written to target file"""
        target_path = "/tmp/shunt_eval/GeneratedTest.java"
        
        result = self.writer.generate(
            spec="Write tests for UserService",
            reference_path="/tmp/shunt_eval/OrderTest.java",
            target_path=target_path
        )
        
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(target_path))
        
        # Check file content
        with open(target_path) as f:
            content = f.read()
        self.assertGreater(len(content), 0)
    
    def test_statistics_tracking(self):
        """Test: Statistics should be tracked"""
        # Generate some code
        self.writer.generate(
            spec="Write tests",
            reference_path="/tmp/shunt_eval/OrderTest.java"
        )
        
        stats = self.writer.get_stats()
        
        self.assertEqual(stats["total_calls"], 1)
        self.assertEqual(stats["worker_calls"], 1)
        self.assertGreater(stats["worker_cost"], 0)
        self.assertGreater(stats["total_lines_generated"], 0)


if __name__ == "__main__":
    unittest.main()
