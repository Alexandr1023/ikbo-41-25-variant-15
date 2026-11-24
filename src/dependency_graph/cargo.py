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
    git_url: str = ""
    git_ref: str = ""
    path: str = ""
    optional: bool = False


@dataclass(frozen=True)
class CargoPackage:
    """Пакет Cargo и путь к его манифесту."""

    name: str
    version: str
    manifest_path: Path
    dependencies: tuple[Dependency, ...]


def clone_repository(url: str, destination: Path, ref: str = "") -> None:
    """Клонирует исходный репозиторий для чтения манифеста."""
    try:
        command = ["git", "clone", "--depth", "1"]
        if ref:
            command.append("--no-checkout")
        command.extend((url, str(destination)))
        result = subprocess.run(
            command,
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
        message = f"Не удалось загрузить репозиторий: {detail}"
        raise DependencyGraphError(message)
    if ref:
        _checkout_ref(destination, ref)


def _checkout_ref(repository: Path, ref: str) -> None:
    """Загружает и переключает репозиторий на branch, tag или rev."""
    if ref.startswith("-") or any(char.isspace() for char in ref):
        raise DependencyGraphError("Некорректный git ref зависимости.")
    commands = (
        ["git", "-C", str(repository), "fetch", "--depth", "1", "origin", ref],
        ["git", "-C", str(repository), "checkout", "--detach", "FETCH_HEAD"],
    )
    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DependencyGraphError(
                f"Не удалось выбрать git ref {ref}: {error}"
            ) from error
        if result.returncode:
            detail = result.stderr.strip()
            if not detail:
                detail = "git checkout завершился с ошибкой"
            raise DependencyGraphError(
                f"Не удалось выбрать git ref {ref}: {detail}"
            )


def _read_manifest(path: Path) -> dict:
    """Загружает TOML-манифест пакета."""
    try:
        with path.open("rb") as manifest_file:
            return tomllib.load(manifest_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DependencyGraphError(
            f"Не удалось прочитать Cargo-манифест {path}: {error}"
        ) from error


def _manifest_paths(repository: Path) -> list[Path]:
    """Находит Cargo.toml, исключая git-объекты и сборку."""
    paths = []
    for path in repository.rglob("Cargo.toml"):
        if ".git" in path.parts or "target" in path.parts:
            continue
        paths.append(path)
    return sorted(paths)


def _find_package(repository: Path, name: str) -> tuple[Path, dict]:
    """Находит пакет с указанным именем в репозитории."""
    for path in _manifest_paths(repository):
        manifest = _read_manifest(path)
        package = manifest.get("package", {})
        if package.get("name") == name:
            return path, manifest
    raise DependencyGraphError(
        f"Пакет {name!r} не найден в Cargo.toml репозитория."
    )


def _workspace_manifest(repository: Path) -> dict:
    """Находит ближайший workspace-манифест среди родителей."""
    fallback = {}
    for directory in (repository, *repository.parents):
        path = directory / "Cargo.toml"
        if not path.is_file():
            continue
        manifest = _read_manifest(path)
        if not fallback:
            fallback = manifest
        if "workspace" in manifest:
            return manifest
    return fallback


def _workspace_dependencies(repository: Path) -> dict:
    """Читает общие зависимости workspace."""
    return _workspace_manifest(repository).get(
        "workspace", {}
    ).get("dependencies", {})


def _dependency_tables(manifest: dict) -> list[dict]:
    """Собирает обычные и build-таблицы зависимостей."""
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


def _dependency_value(value: object, workspace: dict, alias: str) -> tuple:
    """Разбирает алиас, версию и источник одного объявления."""
    if isinstance(value, str):
        return "", value, "", "", "", False
    if not isinstance(value, dict):
        return "", "*", "", "", "", False
    if value.get("workspace") is True:
        workspace_key = alias
        if workspace_key not in workspace:
            workspace_key = value.get("package", "")
        inherited = workspace.get(workspace_key)
        if isinstance(inherited, str):
            return "", inherited, "", "", "", False
        if isinstance(inherited, dict):
            value = {**inherited, **value}
    return (
        str(value.get("package", "")),
        str(value.get("version", "*")),
        str(value.get("git", "")),
        str(
            value.get("branch")
            or value.get("tag")
            or value.get("rev")
            or ""
        ),
        str(value.get("path", "")),
        bool(value.get("optional", False)),
    )


def _collect_dependencies(manifest: dict, workspace: dict) -> tuple:
    """Объединяет зависимости с одинаковым именем пакета."""
    dependencies = {}
    for table in _dependency_tables(manifest):
        for alias, value in table.items():
            details = _dependency_value(value, workspace, alias)
            package_name, version, git_url, git_ref, path, optional = details
            name = package_name or alias
            dependencies[name] = Dependency(
                name,
                version,
                git_url,
                git_ref,
                path,
                optional,
            )
    return tuple(sorted(dependencies.values(), key=lambda item: item.name))


def load_package(repository: Path, name: str) -> CargoPackage:
    """Ищет пакет и читает его обычные и build-зависимости."""
    path, manifest = _find_package(repository, name)
    package = manifest["package"]
    version = package.get("version", "не указана")
    if isinstance(version, dict) and version.get("workspace") is True:
        workspace = _workspace_manifest(repository)
        version = workspace.get("workspace", {}).get("package", {}).get(
            "version", "не указана"
        )
    dependencies = _collect_dependencies(
        manifest,
        _workspace_dependencies(repository),
    )
    return CargoPackage(
        name=package["name"],
        version=str(version),
        manifest_path=path,
        dependencies=dependencies,
    )


def dependency_lines(package: CargoPackage) -> list[str]:
    """Форматирует список прямых зависимостей."""
    if not package.dependencies:
        return ["Прямых зависимостей нет."]
    return [
        _format_dependency(dependency)
        for dependency in package.dependencies
    ]


def _format_dependency(dependency: Dependency) -> str:
    """Форматирует зависимость вместе с её источником."""
    suffix = f" ({dependency.requirement})"
    if dependency.git_url:
        suffix += f" git={dependency.git_url}"
        if dependency.git_ref:
            suffix += f"#{dependency.git_ref}"
    if dependency.path:
        suffix += f" path={dependency.path}"
    return f"{dependency.name}{suffix}"

