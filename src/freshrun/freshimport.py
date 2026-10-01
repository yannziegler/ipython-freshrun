"""
Implementation of the %freshimport IPython magic.

%freshimport
%freshimport --all
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import importlib
from importlib.util import spec_from_file_location
import inspect
import os
import sys
import sysconfig
import types
from pathlib import Path
from typing import Iterable

from IPython.core.magic import Magics, line_magic, magics_class

# Used to avoid reloading itself!
FRESHIMPORT_MODULE = __name__

@dataclass
class ObjectInfo:
    name: str
    kind: str


@dataclass
class ModuleInfo:
    name: str
    functions: int = 0
    classes: int = 0
    others: int = 0
    objects: list[ObjectInfo] = field(default_factory=list)


@dataclass
class FreshImportResult:
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    functions: int = 0
    classes: int = 0
    others: int = 0


def _module_from_object(obj: object) -> types.ModuleType | None:
    if isinstance(obj, types.ModuleType):
        return obj

    module_name = getattr(obj, "__module__", None)
    if not module_name:
        return None

    module = sys.modules.get(module_name)
    return module if isinstance(module, types.ModuleType) else None


def _qualname_getattr(obj: object, qualname: str) -> object:
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


def _module_source_path(module: types.ModuleType) -> Path | None:
    filename = getattr(module, "__file__", None)
    if not filename:
        return None

    path = Path(filename).resolve()
    return path if path.suffix in {".py", ".pyw"} else None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_project_path(path: Path, project_root: Path) -> bool:
    path = path.resolve()
    project_root = project_root.resolve()
    return _is_within(path, project_root)


def _project_root() -> Path | None:
    value = os.environ.get("FRESHRUN_PROJECT_ROOT")

    if not value:
        return None

    root = Path(value).expanduser().resolve()
    return root if root.is_dir() else None


def _environment_paths() -> tuple[Path, ...]:
    paths = sysconfig.get_paths()
    return tuple(
        Path(path).resolve()
        for key in ("stdlib", "platstdlib", "purelib", "platlib")
        if (path := paths.get(key))
    )


def _is_environment_module(module: types.ModuleType) -> bool:
    path = _module_source_path(module)
    if path is None:
        return True

    return any(_is_within(path, root) for root in _environment_paths())


def _modules_from_root(
    root: Path,
) -> dict[str, types.ModuleType]:
    """
    Return currently loaded Python modules whose source files are inside root.

    The filesystem location is the only criterion. This deliberately avoids
    trying to classify modules as "user", "system", "third-party", etc.
    """
    modules: dict[str, types.ModuleType] = {}
    root = root.resolve()

    for module in list(sys.modules.values()):
        if not isinstance(module, types.ModuleType):
            continue

        name = module.__name__

        if name in {"__main__", "__mp_main__", FRESHIMPORT_MODULE}:
            continue

        if name.startswith('freshrun'):
            continue

        path = _module_source_path(module)
        if path is None:
            continue

        if not _is_within(path, root):
            continue

        modules[name] = module

    return modules


def _module_name_from_path(
    path: Path,
    root: Path,
) -> str | None:
    if not _is_within(path, root):
        return None

    relative = path.relative_to(root)

    if relative.name in {"__init__.py", "__init__.pyw"}:
        parts = relative.parts[:-1]
    else:
        parts = relative.with_suffix("").parts

    return ".".join(parts) or None


def _discover_project_modules(root: Path) -> set[str]:
    """
    Recursively discover Python modules below the project root.

    Generated/environment directories are ignored because --all is an
    explicit request to import discovered project files, not environments.
    """
    modules: set[str] = set()

    ignored_directories = {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
    }

    for path in root.rglob("*.py"):
        if any(part in ignored_directories for part in path.parts):
            continue

        module_name = _module_name_from_path(
            path.resolve(),
            root,
        )

        if module_name:
            modules.add(module_name)

    return modules


def _module_depth(module_name: str) -> int:
    return module_name.count(".")


def _reload_module(module: types.ModuleType) -> types.ModuleType:
    """
    Re-execute a source module in its existing module object.

    This intentionally avoids importlib.reload(), whose requirement for a
    valid module __spec__ caused problems in IPython sessions.
    """
    module_name = module.__name__
    path = _module_source_path(module)

    if path is None:
        raise ImportError(
            f"Cannot fresh-import {module_name!r}: "
            "module has no Python source file"
        )

    is_package = path.name in {"__init__.py", "__init__.pyw"}

    if is_package:
        spec = spec_from_file_location(
            module_name,
            str(path),
            submodule_search_locations=[str(path.parent)],
        )
    else:
        spec = spec_from_file_location(module_name, str(path))

    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not create import spec for {module_name!r} "
            f"from {str(path)!r}"
        )

    module.__spec__ = spec
    module.__loader__ = spec.loader

    if is_package:
        module.__package__ = module_name
        module.__path__ = [str(path.parent)]
    else:
        module.__package__ = module_name.rpartition(".")[0]

    spec.loader.exec_module(module)
    return module


def _reload_modules(
    modules: Iterable[types.ModuleType],
) -> dict[str, types.ModuleType]:
    unique = {
        module.__name__: module
        for module in modules
        if isinstance(module, types.ModuleType)
    }

    ordered = sorted(
        unique.values(),
        key=lambda module: (
            _module_depth(module.__name__),
            module.__name__,
        ),
    )

    reloaded: dict[str, types.ModuleType] = {}

    for module in ordered:
        reloaded[module.__name__] = _reload_module(module)

    return reloaded


def _import_modules(
    module_names: Iterable[str],
) -> dict[str, types.ModuleType]:
    """
    Import discovered modules which aren't already loaded.

    The modules are imported into sys.modules but are not injected into
    user_ns. Existing namespace bindings are handled separately.
    """
    modules: dict[str, types.ModuleType] = {}

    for module_name in sorted(
        set(module_names),
        key=lambda name: (_module_depth(name), name),
    ):
        module = sys.modules.get(module_name)

        if module is None:
            module = importlib.import_module(module_name)

        if isinstance(module, types.ModuleType):
            modules[module_name] = module

    return modules


# def _capture_bindings(
#     namespace: dict[str, object],
#     module_names: set[str],
# ) -> dict[str, tuple[str, str]]:
#     bindings: dict[str, tuple[str, str]] = {}

#     for name, value in namespace.items():
#         module = _module_from_object(value)
#         if module is None or module.__name__ not in module_names:
#             continue

#         qualname = getattr(value, "__qualname__", None)
#         if not qualname or "<locals>" in qualname:
#             continue

#         bindings[name] = (module.__name__, qualname)

#     return bindings


# def _capture_bindings(
#     namespace: dict[str, object],
#     module_names: set[str],
# ) -> dict[str, tuple[str, str]]:
#     bindings: dict[str, tuple[str, str]] = {}

#     modules = {
#         name: sys.modules[name]
#         for name in module_names
#         if isinstance(sys.modules.get(name), types.ModuleType)
#     }

#     for name, value in namespace.items():
#         module = _module_from_object(value)

#         if module is not None and module.__name__ in module_names:
#             qualname = getattr(value, "__qualname__", None)

#             if qualname and "<locals>" not in qualname:
#                 bindings[name] = (module.__name__, qualname)
#                 continue

#         # Objects such as instances, constants, dicts, lists, etc. may not
#         # expose __module__. Find the object directly in a project module.
#         for module_name, candidate in modules.items():
#             for attr_name, attr_value in candidate.__dict__.items():
#                 if attr_value is value:
#                     bindings[name] = (module_name, attr_name)
#                     break
#             if name in bindings:
#                 break

#     return bindings


def _capture_bindings(
    namespace: dict[str, object],
    module_names: set[str],
) -> dict[str, tuple[str, str | None]]:
    bindings: dict[str, tuple[str, str | None]] = {}

    modules = {
        name: sys.modules[name]
        for name in module_names
        if isinstance(sys.modules.get(name), types.ModuleType)
    }

    for name, value in namespace.items():
        if isinstance(value, types.ModuleType):
            continue

        # The binding may be a function/class/object imported with
        # `from module import X`, or a plain module global such as X = 42.
        for module_name, module in modules.items():
            if module.__dict__.get(name, object()) is value:
                qualname = getattr(value, "__qualname__", None)

                if (
                    qualname
                    and "<locals>" not in qualname
                    and getattr(value, "__module__", None) == module_name
                ):
                    bindings[name] = (module_name, qualname)
                else:
                    bindings[name] = (module_name, None)

                break

    return bindings


def _refresh_namespace_bindings(
    namespace: dict[str, object],
    bindings: dict[str, tuple[str, str]],
    reloaded: dict[str, types.ModuleType],
    module_info: dict[str, ModuleInfo],
) -> None:
    for name, (module_name, qualname) in bindings.items():
        module = reloaded.get(module_name)
        if module is None:
            continue

        if qualname is None:
            if name not in module.__dict__:
                namespace.pop(name, None)
                continue
            new_value = module.__dict__[name]
        else:
            try:
                new_value = _qualname_getattr(module, qualname)
            except AttributeError:
                namespace.pop(name, None)
                continue

        # try:
        #     new_value = _qualname_getattr(module, qualname)
        # except AttributeError:
        #     namespace.pop(name, None)
        #     continue

        if isinstance(new_value, types.ModuleType):
            continue

        namespace[name] = new_value
        info = module_info[module_name]

        if inspect.isfunction(new_value):
            kind = "function"
            info.functions += 1
        elif inspect.isclass(new_value):
            kind = "class"
            info.classes += 1
        else:
            kind = "other"
            info.others += 1

        info.objects.append(ObjectInfo(name=name, kind=kind))


def _refresh_module_bindings(
    namespace: dict[str, object],
    reloaded: dict[str, types.ModuleType],
) -> None:
    for name, value in list(namespace.items()):
        if not isinstance(value, types.ModuleType):
            continue

        module_name = value.__name__
        if module_name in reloaded:
            namespace[name] = reloaded[module_name]


def fresh_import(
    namespace: dict[str, object],
    *,
    import_all: bool = False,
) -> FreshImportResult:
    """
    Reload currently loaded modules inside the current project root.

    Without an explicit freshrun project root, the current working directory
    is the boundary.

    With a freshrun project root, that directory is the boundary.

    --all additionally discovers and imports Python files below that root.
    """
    project_root = _project_root()
    root = project_root if project_root is not None else Path.cwd().resolve()

    if project_root is None and root == Path.home().resolve():
        print(
            "%freshimport: cannot be used from the user home directory; "
            "change to a project directory or use "
            "'%freshrun --project ~/my_project'."
        )
        return FreshImportResult()

    # In every mode, the reload boundary is purely filesystem-based.
    modules = _modules_from_root(root)

    discovered = (
        _discover_project_modules(root)
        if import_all
        else set()
    )

    module_names = set(modules)

    bindings = _capture_bindings(
        namespace,
        module_names,
    )

    imported = _import_modules(
        discovered - module_names,
    ) if import_all else {}

    # Include newly imported modules in the result. They weren't reloaded,
    # but they are part of the fresh-import operation.
    all_modules = dict(modules)
    all_modules.update(imported)

    reloaded = _reload_modules(modules.values())

    module_info = {
        module_name: ModuleInfo(name=module_name)
        for module_name in all_modules
    }

    _refresh_namespace_bindings(
        namespace,
        bindings,
        reloaded,
        module_info,
    )

    _refresh_module_bindings(
        namespace,
        reloaded,
    )

    return FreshImportResult(
        modules=module_info,
        functions=sum(info.functions for info in module_info.values()),
        classes=sum(info.classes for info in module_info.values()),
        others=sum(info.others for info in module_info.values()),
    )


def _format_count(
    count: int,
    singular: str,
    plural: str | None = None,
) -> str:
    plural = plural or singular + "s"
    return f"{count} {singular if count == 1 else plural}"


def _print_result(
    result: FreshImportResult,
    *,
    verbosity: int,
) -> None:
    summary = [
        _format_count(len(result.modules), "module"),
        _format_count(result.functions, "function"),
        _format_count(result.classes, "class", "classes"),
    ]

    if result.others:
        summary.append(_format_count(result.others, "other"))

    print("%freshimport: " + ", ".join(summary))

    if verbosity == 0:
        return

    # if verbosity == 1:
    #     for module_name in sorted(result.modules):
    #         print(f"  {module_name}")
    #     return

    for module_name in sorted(result.modules):
        info = result.modules[module_name]
        module_summary = [
            _format_count(info.functions, "function"),
            _format_count(info.classes, "class", "classes"),
        ]

        if info.others:
            module_summary.append(_format_count(info.others, "other"))

        if verbosity >= 1:
            print(f"  {module_name}: " + ", ".join(module_summary))

        if verbosity >= 2:
            objects = [
                obj for obj in info.objects
                if verbosity >= 3 or obj.kind != "other"
            ]

            sorted_obj = sorted(
                objects,
                key=lambda obj: (obj.kind, obj.name),
            )
            for obj in sorted_obj:
                print(f"    {obj.kind}: {obj.name}")


@magics_class
class FreshImportMagics(Magics):
    """IPython magic providing in-place fresh imports."""

    @line_magic
    def freshimport(self, line: str = "") -> None:
        """
        Reload currently imported modules.

        In a freshrun child with a known project root, only project modules
        are reloaded.

        Use --all in that context to additionally discover and import all
        Python modules below the project root.
        """
        parser = argparse.ArgumentParser(
            prog="%freshimport",
            description="Reload currently imported modules in place.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="in a project child, also discover and import project modules",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            action="count",
            default=0,
            help="increase output verbosity " \
                 "(-vv for functions/classes, -vvv for all objects)",
        )

        try:
            args = parser.parse_args(line.split())
        except SystemExit:
            return

        result = fresh_import(
            self.shell.user_ns,
            import_all=args.all,
        )

        if not result.modules:
            print("%freshimport: no reloadable modules found.")
            return

        _print_result(
            result,
            verbosity=min(args.verbose, 3),
        )
