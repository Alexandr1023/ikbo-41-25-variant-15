"""Обход Cargo-графа из lock-файла или реестра crates.io."""

from hashlib import sha256
from pathlib import Path

from dependency_graph.cargo import (
    CargoPackage,
    Dependency,
    clone_repository,
    load_package,
)
from dependency_graph.errors import DependencyGraphError
from dependency_graph.graph import DependencyGraph, breadth_first
from dependency_graph.lockfile import graph_from_lock
from dependency_graph.registry import CrateIndex


class CargoGraphSource:
    """Разрешает зависимости Cargo без обращения к Cargo CLI."""

    def __init__(
        self,
        repository: Path,
        package: CargoPackage,
        temporary_root: Path,
    ) -> None:
        self.repository = repository
        self.temporary_root = temporary_root
        self.index = CrateIndex()
        self.root = f"{package.name}@{package.version}"
        self.packages: dict[str, CargoPackage] = {self.root: package}
        self.records: dict[str, dict] = {}
        self.clones: dict[str, Path] = {}

    def _local_package(self, parent: CargoPackage, dep: Dependency) -> str:
        directory = parent.manifest_path.parent / dep.path
        package = load_package(directory.resolve(), dep.name)
        identifier = f"{package.name}@{package.version}"
        self.packages[identifier] = package
        return identifier

    def _git_package(self, dep: Dependency) -> str:
        key = sha256(dep.git_url.encode("utf-8")).hexdigest()[:12]
        repository = self.clones.get(dep.git_url)
        if repository is None:
            repository = self.temporary_root / f"git-{key}"
            clone_repository(dep.git_url, repository)
            self.clones[dep.git_url] = repository
        package = load_package(repository, dep.name)
        identifier = f"{package.name}@{package.version}"
        self.packages[identifier] = package
        return identifier

    def _registry_package(self, dep: Dependency) -> str:
        record = self.index.resolve(dep.name, dep.requirement)
        identifier = self.index.package_id(record)
        self.records[identifier] = record
        return identifier

    def _resolve(self, parent: CargoPackage, dep: Dependency) -> str:
        if dep.path:
            return self._local_package(parent, dep)
        if dep.git_url:
            return self._git_package(dep)
        return self._registry_package(dep)

    def _package_dependencies(self, node: str) -> tuple[Dependency, ...]:
        if node in self.packages:
            return self.packages[node].dependencies
        return self.index.dependencies(self.records[node])

    def get_dependencies(self, node: str) -> tuple[str, ...]:
        """Возвращает соседей пакета и регистрирует новые узлы."""
        parent = self.packages.get(node)
        dependencies = self._package_dependencies(node)
        resolved = []
        for dependency in dependencies:
            if dependency.optional:
                continue
            if parent is None and (dependency.path or dependency.git_url):
                raise DependencyGraphError(
                    "Реестр crates.io содержит неподдерживаемый источник."
                )
            if parent is None:
                child = self._registry_package(dependency)
            else:
                child = self._resolve(parent, dependency)
            resolved.append(child)
        return tuple(sorted(set(resolved)))


def _find_lockfile(repository: Path, package: CargoPackage) -> Path:
    candidates = (repository / "Cargo.lock", package.manifest_path.parent / "Cargo.lock")
    return next((path for path in candidates if path.is_file()), candidates[0])


def build_cargo_graph(
    repository: Path,
    package: CargoPackage,
    temporary_root: Path,
) -> DependencyGraph:
    """Строит граф из Cargo.lock или из sparse index crates.io."""
    lock_path = _find_lockfile(repository, package)
    if lock_path.is_file():
        locked = graph_from_lock(lock_path, package.name, package.version)
        if locked is not None:
            return locked
    source = CargoGraphSource(repository, package, temporary_root)
    return breadth_first(source.root, source.get_dependencies)

