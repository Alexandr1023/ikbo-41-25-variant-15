"""Чтение Cargo-манифестов без вызова менеджера пакетов."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tomllib

from dependency_graph.errors import DependencyGraphError


@dataclass(frozen=True)
class Dependency:
    """Прямая зависимость из Cargo.toml."""

    name: str
    requirement: str


@dataclass(frozen=True)
class CargoPackage:
    """Пакет Cargo и путь к его манифесту."""

    name: str
    version: str
    manifest_path: Path
    dependencies: tuple[Dependency, ...]


def clone_repository(url: str, destination: Path) -> None:
    """Клонирует исходный репозиторий для чтения манифеста."""
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(destination)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DependencyGraphError(
            f"Не удалось загрузить репозиторий: {error}"
        ) from error
    if result.returncode:
        detail = result.stderr.strip() or "git clone завершился с ошибкой"
        raise DependencyGraphError(f"Не удалось загрузить репозиторий: {detail}")


def _read_manifest(path: Path) -> dict:
    try:
        with path.open("rb") as manifest_file:
            return tomllib.load(manifest_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DependencyGraphError(
            f"Не удалось прочитать Cargo-манифест {path}: {error}"
        ) from error


def _manifest_paths(repository: Path) -> list[Path]:
    paths = []
    for path in repository.rglob("Cargo.toml"):
        if ".git" in path.parts or "target" in path.parts:
            continue
        paths.append(path)
    return sorted(paths)


def _find_package(repository: Path, name: str) -> tuple[Path, dict]:
    for path in _manifest_paths(repository):
        manifest = _read_manifest(path)
        package = manifest.get("package", {})
        if package.get("name") == name:
            return path, manifest
    raise DependencyGraphError(
        f"Пакет {name!r} не найден в Cargo.toml репозитория."
    )


def _workspace_dependencies(repository: Path) -> dict:
    path = repository / "Cargo.toml"
    if not path.is_file():
        return {}
    manifest = _read_manifest(path)
    return manifest.get("workspace", {}).get("dependencies", {})


def _dependency_tables(manifest: dict) -> list[dict]:
    tables = []
    for key in ("dependencies", "build-dependencies"):
        value = manifest.get(key, {})
        if isinstance(value, dict):
            tables.append(value)
    targets = manifest.get("target", {})
    if isinstance(targets, dict):
        for target in targets.values():
            if not isinstance(target, dict):
                continue
            for key in ("dependencies", "build-dependencies"):
                value = target.get(key, {})
                if isinstance(value, dict):
                    tables.append(value)
    return tables


def _dependency_value(value: object, workspace: dict) -> tuple[str, str]:
    if isinstance(value, str):
        return "", value
    if not isinstance(value, dict):
        return "", "*"
    if value.get("workspace") is True:
        inherited = workspace.get(value.get("package", ""))
        if isinstance(inherited, str):
            return "", inherited
        if isinstance(inherited, dict):
            value = {**inherited, **value}
    return str(value.get("package", "")), str(value.get("version", "*"))


def _collect_dependencies(manifest: dict, workspace: dict) -> tuple:
    dependencies = {}
    for table in _dependency_tables(manifest):
        for alias, value in table.items():
            package_name, version = _dependency_value(value, workspace)
            name = package_name or alias
            dependencies[name] = Dependency(name, version)
    return tuple(sorted(dependencies.values(), key=lambda item: item.name))


def load_package(repository: Path, name: str) -> CargoPackage:
    """Ищет пакет и читает его обычные и build-зависимости."""
    path, manifest = _find_package(repository, name)
    package = manifest["package"]
    dependencies = _collect_dependencies(
        manifest,
        _workspace_dependencies(repository),
    )
    return CargoPackage(
        name=package["name"],
        version=str(package.get("version", "не указана")),
        manifest_path=path,
        dependencies=dependencies,
    )


def dependency_lines(package: CargoPackage) -> list[str]:
    """Форматирует список прямых зависимостей."""
    if not package.dependencies:
        return ["Прямых зависимостей нет."]
    return [
        f"{dependency.name} ({dependency.requirement})"
        for dependency in package.dependencies
    ]

