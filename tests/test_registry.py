"""Проверки semver-выбора без сетевых запросов."""

import unittest

from dependency_graph.registry import _index_path, version_matches


class RegistryTests(unittest.TestCase):
    """Проверяет пути индекса и распространённые диапазоны Cargo."""

    def test_sparse_index_paths(self) -> None:
        self.assertEqual(_index_path("a"), "1/a")
        self.assertEqual(_index_path("ab"), "2/ab")
        self.assertEqual(_index_path("log"), "3/l/log")
        self.assertEqual(_index_path("serde"), "se/rd/serde")

    def test_caret_requirements(self) -> None:
        self.assertTrue(version_matches("1.9.0", "^1.2"))
        self.assertFalse(version_matches("2.0.0", "^1.2"))
        self.assertTrue(version_matches("0.2.8", "^0.2.3"))
        self.assertFalse(version_matches("0.3.0", "^0.2.3"))

    def test_comparison_and_wildcard_requirements(self) -> None:
        self.assertTrue(version_matches("1.4.2", ">= 1.2, < 2.0"))
        self.assertFalse(version_matches("2.0.0", ">= 1.2, < 2.0"))
        self.assertTrue(version_matches("1.2.9", "1.2.*"))
        self.assertFalse(version_matches("1.3.0", "1.2.*"))

    def test_prerelease_needs_explicit_requirement(self) -> None:
        self.assertFalse(version_matches("1.0.0-alpha", "^1.0"))
        self.assertTrue(version_matches("1.0.0-alpha", "=1.0.0-alpha"))


if __name__ == "__main__":
    unittest.main()
