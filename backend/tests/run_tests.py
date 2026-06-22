#!/usr/bin/env python3
"""
Simple test runner to execute plain python test classes (Test*) with assert statements,
without requiring pytest to be installed.
"""
import os
import sys
import inspect
import importlib

def main():
    sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
    tests_dir = os.path.abspath(os.path.dirname(__file__))
    
    # Find all test_*.py files
    test_files = [f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")]
    
    passed_count = 0
    failed_count = 0
    failures = []
    
    for filename in sorted(test_files):
        module_name = f"tests.{filename[:-3]}"
        print(f"Running tests in {filename}...")
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            print(f"  ❌ Failed to import {module_name}: {e}")
            failed_count += 1
            failures.append((module_name, "Import", e))
            continue
            
        # Find all test classes or TestCase classes
        for name, obj in inspect.getmembers(module):
            if not inspect.isclass(obj) or not name.startswith("Test"):
                continue
                
            print(f"  Class {name}:")
            # Instantiate class (unless it's a unittest.TestCase subclass, which we handle differently)
            import unittest
            is_unittest = issubclass(obj, unittest.TestCase)
            
            if is_unittest:
                # Run via unittest runner
                suite = unittest.defaultTestLoader.loadTestsFromTestCase(obj)
                runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=1)
                result = runner.run(suite)
                passed_count += result.testsRun - len(result.failures) - len(result.errors)
                failed_count += len(result.failures) + len(result.errors)
                for test, err in result.failures + result.errors:
                    failures.append((f"{module_name}.{name}", test.id(), err))
            else:
                instance = obj()
                # Find all methods starting with test_
                for method_name, method in inspect.getmembers(instance):
                    if not inspect.ismethod(method) or not method_name.startswith("test_"):
                        continue
                        
                    try:
                        # If the method expects a 'self' argument, call it
                        method()
                        print(f"    ✅ {method_name} - PASSED")
                        passed_count += 1
                    except Exception as e:
                        print(f"    ❌ {method_name} - FAILED: {e}")
                        failed_count += 1
                        failures.append((f"{module_name}.{name}", method_name, e))
                        
    print("\n" + "="*40)
    print(f"Test Run Summary:")
    print(f"  Passed: {passed_count}")
    print(f"  Failed: {failed_count}")
    print("="*40)
    
    if failed_count > 0:
        print("\nFailures:")
        for scope, test, err in failures:
            print(f"  [{scope}] {test}: {err}")
        sys.exit(1)
    else:
        print("\nAll tests passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
