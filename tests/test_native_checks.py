"""Regression tests for native CMake/CTest check discovery."""
from pathlib import Path
import tempfile
import unittest

from sparkle_coder.checks import discover_checks
from sparkle_coder.workspace import Workspace


class NativeCheckDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Workspace(Path(self.tmp.name))

    def put(self, path, body):
        target = self.workspace.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def get(self):
        return discover_checks(self.workspace)["checks"]

    def native(self):
        return [check for check in self.get()
                if check["command"].startswith(("cmake ", "ctest "))]

    def test_root_project_discovers_configure_build_and_ctest(self):
        self.put("CMakeLists.txt", """cmake_minimum_required(VERSION 3.21)
project(example LANGUAGES CXX)
include(CTest)
add_executable(example main.cpp)
if(BUILD_TESTING)
    add_test(NAME example COMMAND example)
endif()
""")
        checks = self.native()
        self.assertEqual([check["command"] for check in checks], [
            "cmake -S . -B build/sparkle-coder -DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            "cmake --build build/sparkle-coder --parallel 2",
            "ctest --test-dir build/sparkle-coder --output-on-failure --no-tests=error",
        ])
        self.assertTrue(all(check["cwd"] == "." for check in checks))

    def test_no_ctest_suggestion_without_test_declaration(self):
        self.put("CMakeLists.txt", "cmake_minimum_required(VERSION 3.21)\nproject(example CXX)\n")
        self.assertEqual(len(self.native()), 2)

    def test_nested_add_subdirectory_is_not_independent_project(self):
        self.put("CMakeLists.txt", "project(parent CXX)\nadd_subdirectory(src)\n")
        self.put("src/CMakeLists.txt", "add_library(core core.cpp)\n")
        checks = self.native()
        self.assertEqual(len(checks), 2)
        self.assertEqual({item["cwd"] for item in checks}, {"."})

    def test_nested_standalone_project_is_discovered(self):
        self.put("native/client/CMakeLists.txt", "project(client LANGUAGES CXX)\nenable_testing()\n")
        checks = self.native()
        self.assertEqual(len(checks), 3)
        self.assertEqual({item["cwd"] for item in checks}, {"native/client"})

    def test_nested_project_with_explicit_project_directive_is_independent(self):
        self.put("CMakeLists.txt", "project(parent)\nadd_subdirectory(lib)\n")
        self.put("lib/CMakeLists.txt", "project(child)\n")
        checks = self.native()
        self.assertEqual(len(checks), 4)
        self.assertEqual({item["cwd"] for item in checks}, {".", "lib"})

    def test_tests_declared_in_subdirectory_use_root_ctest(self):
        self.put("CMakeLists.txt", "project(example CXX)\nadd_subdirectory(tests)\n")
        self.put("tests/CMakeLists.txt", "enable_testing()\nadd_test(NAME smoke COMMAND example)\n")
        checks = self.native()
        self.assertEqual(len(checks), 3)
        self.assertEqual(checks[-1]["cwd"], ".")

    def test_commented_test_declaration_is_ignored(self):
        self.put("CMakeLists.txt", "# include(CTest)\nproject(example CXX)\n")
        self.assertEqual(len(self.native()), 2)

    def test_existing_languages_not_regressed(self):
        self.put("package.json", '{"scripts":{"test":"node test.js"}}')
        self.assertIn("npm run test", [item["command"] for item in self.get()])
        self.assertEqual(self.native(), [])

    def test_discovery_does_not_execute_build(self):
        self.put("CMakeLists.txt", "project(example)\n")
        self.native()
        self.assertFalse((self.workspace.root / "build").exists())


if __name__ == "__main__":
    unittest.main()
