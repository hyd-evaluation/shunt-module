"""
Hook Evals
Tests file read blocking and smart routing
"""

import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interceptor import ShuntInterceptor


class TestHookEvals(unittest.TestCase):
    """Test file read hook evaluation"""
    
    def setUp(self):
        self.interceptor = ShuntInterceptor(
            threshold=350,
            min_lines_for_shunt=500,
            base_dir="/tmp/shunt_test"
        )
        # Create test files
        self._create_test_files()
    
    def tearDown(self):
        # Clean up test files
        self._remove_test_files()
    
    def _create_test_files(self):
        """Create test files for evaluation"""
        os.makedirs("/tmp/shunt_test", exist_ok=True)
        
        # Large file (>350 lines)
        with open("/tmp/shunt_test/large_file.java", "w") as f:
            f.write("// Large file\n" * 500)
        
        # Small file (<350 lines)
        with open("/tmp/shunt_test/small_file.java", "w") as f:
            f.write("// Small file\n" * 100)
        
        # Visitor file (should be skipped)
        with open("/tmp/shunt_test/TestVisitor.java", "w") as f:
            f.write("// Visitor\n" * 600)
        
        # Parser file (should be skipped)
        with open("/tmp/shunt_test/TestParser.java", "w") as f:
            f.write("// Parser\n" * 600)
    
    def _remove_test_files(self):
        """Remove test files"""
        import shutil
        if os.path.exists("/tmp/shunt_test"):
            shutil.rmtree("/tmp/shunt_test")
    
    def test_cat_large_file(self):
        """Test: cat on large file should be intercepted"""
        command = "cat /tmp/shunt_test/large_file.java"
        should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
        
        self.assertTrue(should_intercept)
        self.assertEqual(file_path, "/tmp/shunt_test/large_file.java")
        self.assertEqual(cmd_type, "cat")
    
    def test_cat_small_file(self):
        """Test: cat on small file should NOT be intercepted"""
        command = "cat /tmp/shunt_test/small_file.java"
        should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
        
        self.assertFalse(should_intercept)
    
    def test_head_large_file(self):
        """Test: head on large file should be intercepted"""
        command = "head -100 /tmp/shunt_test/large_file.java"
        should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
        
        self.assertTrue(should_intercept)
        self.assertEqual(cmd_type, "head")
    
    def test_tail_large_file(self):
        """Test: tail on large file should be intercepted"""
        command = "tail -50 /tmp/shunt_test/large_file.java"
        should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
        
        self.assertTrue(should_intercept)
        self.assertEqual(cmd_type, "tail")
    
    def test_visitor_skipped(self):
        """Test: Visitor files should be skipped"""
        command = "cat /tmp/shunt_test/TestVisitor.java"
        should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
        
        self.assertFalse(should_intercept)
        self.assertEqual(self.interceptor._stats["files_skipped_pattern"], 1)
    
    def test_parser_skipped(self):
        """Test: Parser files should be skipped"""
        command = "cat /tmp/shunt_test/TestParser.java"
        should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
        
        self.assertFalse(should_intercept)
        self.assertEqual(self.interceptor._stats["files_skipped_pattern"], 1)
    
    def test_piped_command_not_intercepted(self):
        """Test: Piped commands should NOT be intercepted"""
        command = "cat /tmp/shunt_test/large_file.java | grep -i 'class'"
        should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
        
        # Piped commands should not be intercepted
        self.assertFalse(should_intercept)
    
    def test_non_read_command_not_intercepted(self):
        """Test: Non-read commands should NOT be intercepted"""
        commands = [
            "ls -la /tmp/shunt_test",
            "grep -r 'pattern' /tmp/shunt_test",
            "find /tmp/shunt_test -name '*.java'",
            "git status",
        ]
        
        for command in commands:
            should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
            self.assertFalse(should_intercept, f"Should not intercept: {command}")
    
    def test_relative_path_resolved(self):
        """Test: Relative paths should be resolved"""
        command = "cat large_file.java"
        should_intercept, file_path, cmd_type = self.interceptor.check_command(command)
        
        self.assertTrue(should_intercept)
        self.assertTrue(os.path.isabs(file_path))
    
    def test_statistics_tracking(self):
        """Test: Statistics should be tracked correctly"""
        # Reset stats
        self.interceptor.reset_stats()
        
        # Check some files
        self.interceptor.check_command("cat /tmp/shunt_test/large_file.java")
        self.interceptor.check_command("cat /tmp/shunt_test/small_file.java")
        self.interceptor.check_command("cat /tmp/shunt_test/TestVisitor.java")
        
        stats = self.interceptor.get_stats()
        
        self.assertEqual(stats["files_checked"], 3)
        self.assertEqual(stats["files_intercepted"], 1)
        self.assertEqual(stats["files_skipped_small"], 1)
        self.assertEqual(stats["files_skipped_pattern"], 1)


if __name__ == "__main__":
    unittest.main()
