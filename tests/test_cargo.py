"""Проверки чтения Cargo.toml без Cargo CLI."""

from pathlib import Path
import tempfile
import unittest

from dependency_graph.cargo import CargoPackage, load_package


def _load_workspace_packages(root: Path) -> tuple[CargoPackage, CargoPackage]:
    """Создаёт workspace и загружает основной и локальный пакеты."""
    app = root / "app"
    app.mkdir()
    workspace = (
        "[workspace]\nmembers = ['app']\n\n"
        "[workspace.package]\nversion = '1.0.0'\n\n"
        "[workspace.dependencies]\nserde = '^1.0'\n"
    )
    (root / "Cargo.toml").write_text(workspace, encoding="utf-8")
    manifest = (
        "[package]\nname = 'demo'\nversion.workspace = true\n\n"
        "[dependencies]\nserde.workspace = true\n"
        "renamed = { package = 'actual', version = '2' }\n\n"
        "git-dep = { git = 'https://example.test/repo', "
        "rev = 'abc123' }\n\n"
        "[build-dependencies]\ncc = '1'\n\n"
        "[dev-dependencies]\npretty_assertions = '1'\n\n"
        "[target.'cfg(unix)'.dependencies]\nlibc = '0.2'\n"
    )
    (app / "Cargo.toml").write_text(manifest, encoding="utf-8")
    local = app / "local"
    local.mkdir()
    local_manifest = (
        "[package]\nname = 'local'\nversion.workspace = true\n\n"
        "[dependencies]\nserde.workspace = true\n"
    )
    (local / "Cargo.toml").write_text(local_manifest, encoding="utf-8")
    return load_package(root, "demo"), load_package(local, "local")


class CargoManifestTests(unittest.TestCase):
    """Проверяет обычные, build- и workspace-зависимости."""

    def test_reads_workspace_dependencies_and_target_tables(self) -> None:
        """Собирает зависимости workspace из TOML-манифестов."""
        with tempfile.TemporaryDirectory() as temporary:
            package, local_package = _load_workspace_packages(
                Path(temporary)
            )
        self.assertEqual(package.version, "1.0.0")
        found = {item.name: item.requirement for item in package.dependencies}
        self.assertEqual(
            found,
            {
                "actual": "2",
                "cc": "1",
                "git-dep": "*",
                "libc": "0.2",
                "serde": "^1.0",
            },
        )
        git_dependency = next(
            item for item in package.dependencies if item.name == "git-dep"
        )
        self.assertEqual(git_dependency.git_ref, "abc123")
        self.assertEqual(local_package.version, "1.0.0")
        self.assertEqual(local_package.dependencies[0].requirement, "^1.0")


if __name__ == "__main__":
    unittest.main()
