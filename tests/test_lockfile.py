"""Проверки построения графа по Cargo.lock."""

from pathlib import Path
import tempfile
import unittest

from dependency_graph.lockfile import graph_from_lock


class LockfileTests(unittest.TestCase):
    """Проверяет разрешение имён и версий пакетов lock-файла."""

    def test_builds_transitive_graph_from_lockfile(self) -> None:
        """Обходит прямые и транзитивные ссылки без Cargo."""
        content = (
            'version = 3\n\n'
            '[[package]]\nname = "app"\nversion = "1.0.0"\n'
            'dependencies = ["alpha 1.2.0 (registry+crates)"]\n\n'
            '[[package]]\nname = "alpha"\nversion = "1.2.0"\n'
            'source = "registry+crates"\n'
            'dependencies = ["beta 2.0.0 (registry+crates)"]\n\n'
            '[[package]]\nname = "beta"\nversion = "2.0.0"\n'
            'source = "registry+crates"\n'
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Cargo.lock"
            path.write_text(content, encoding="utf-8")
            graph = graph_from_lock(path, "app", "1.0.0")
        self.assertIsNotNone(graph)
        self.assertEqual(
            graph.breadth_first_order,
            ("app@1.0.0", "alpha@1.2.0", "beta@2.0.0"),
        )


if __name__ == "__main__":
    unittest.main()
