"""Построение графа по Cargo.lock без запуска Cargo."""

from pathlib import Path
import re
import tomllib

from dependency_graph.errors import DependencyGraphError
from dependency_graph.graph import DependencyGraph, breadth_first

_LOCK_REFERENCE = re.compile(
    r"^(?P<name>[^ ]+)(?:\s+(?P<version>\d[^ ]*))?(?:\s+"
    r"\((?P<source>[^)]+)\))?$"
)


def _load_lock(path: Path) -> dict:
    try:
        with path.open("rb") as lock_file:
            return tomllib.load(lock_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DependencyGraphError(
            f"Не удалось прочитать Cargo.lock {path}: {error}"
        ) from error


def _package_id(package: dict) -> str:
    return f"{package['name']}@{package['version']}"


def _reference_parts(value: str) -> tuple[str, str, str]:
    match = _LOCK_REFERENCE.fullmatch(value.strip())
    if not match:
        raise DependencyGraphError(
            f"Некорректная ссылка на пакет в Cargo.lock: {value}"
        )
    return (
        match.group("name"),
        match.group("version") or "",
        match.group("source") or "",
    )


def _find_referenced_package(value: str, packages: list[dict]) -> str:
    name, version, source = _reference_parts(value)
    candidates = [item for item in packages if item.get("name") == name]
    if version:
        candidates = [
            item for item in candidates if item.get("version") == version
        ]
    if source:
        candidates = [
            item for item in candidates if item.get("source", "") == source
        ]
    if not candidates:
        return ""
    return _package_id(sorted(candidates, key=_package_id)[0])


def graph_from_lock(
    path: Path,
    root_name: str,
    root_version: str,
) -> DependencyGraph | None:
    """Возвращает граф из lock-файла или None, если корня в нём нет."""
    data = _load_lock(path)
    packages = data.get("package", [])
    roots = [
        item
        for item in packages
        if item.get("name") == root_name
        and item.get("version") == root_version
    ]
    if not roots:
        return None
    root = _package_id(roots[0])
    by_id = {_package_id(item): item for item in packages}

    def children(node: str) -> tuple[str, ...]:
        package = by_id[node]
        values = package.get("dependencies", [])
        resolved = (_find_referenced_package(value, packages) for value in values)
        return tuple(item for item in resolved if item)

    return breadth_first(root, children)

