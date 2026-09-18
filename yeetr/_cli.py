"""CLI entry point for running callables from Python files."""

from __future__ import annotations

import importlib.util
import inspect
import stat
import sys
import types
import typing
from contextlib import suppress
from pathlib import Path
from typing import get_args, get_origin

from rich.console import Console
from rich.text import Text

from ._runner import run


def _logo_text(style: str) -> Text:
    text = Text(style=style)
    text.append("                  _        \n")
    text.append("  _   _  ___  ___| |_ _ __ \n")
    text.append(" | | | |/ _ \\/ _ \\ __| '__|\n")
    text.append(" | |_| |  __/  __/ |_| |   \n")
    text.append("  \\__, |\\___|\\___|\\__|_|   \n")
    text.append("  |___/                    ")
    return text


def _print_error(message: str) -> None:
    console = Console(file=sys.stderr, soft_wrap=True)
    console.print(_logo_text("bold red"))
    console.print(Text(message, style="red"))


def _print_status(message: str) -> None:
    console = Console(file=sys.stdout, soft_wrap=True)
    console.print(_logo_text("bold green"))
    console.print(Text(message, style="green"))


def _script_template() -> str:
    return (
        "#!yeet\n"
        "import logging\n"
        "\n"
        'logger = logging.getLogger("Main")\n'
        "\n"
        "\n"
        "def main() -> None:\n"
        '    logger.info("Hello from yeetr")\n'
    )


def _create_script(path: Path) -> None:
    if path.suffix != ".py":
        _print_error(f"file not found: {path}")
        sys.exit(2)
    if not path.parent.exists():
        _print_error(f"parent directory not found: {path.parent}")
        sys.exit(2)
    try:
        path.write_text(_script_template())
        current_mode = path.stat().st_mode
        path.chmod(current_mode | stat.S_IXUSR)
    except OSError as exc:
        _print_error(f"could not create {path}: {exc}")
        sys.exit(2)
    _print_status(f"created {path}")


def _load_module(path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        _print_error(f"cannot load {path}")
        sys.exit(2)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    except Exception:
        with suppress(KeyError):
            del sys.modules[spec.name]
        raise
    finally:
        del sys.path[0]
    return module


def _is_public_local_function(module_name: str, name: str, obj: object) -> bool:
    """Return whether ``obj`` is a public ``def``/``async def`` defined in this module.

    Strict on purpose: excludes anything with a leading underscore, anything not a
    plain function (classes, callable instances, ``functools.partial``), imported
    functions (``__module__`` differs), aliases and lambdas (``__name__`` differs).
    """
    return (
        not name.startswith("_")
        and inspect.isfunction(obj)
        and obj.__module__ == module_name
        and obj.__name__ == name
    )


def _is_str_type(annotation: object) -> bool:
    if annotation is str:
        return True
    if get_origin(annotation) in (typing.Union, types.UnionType):
        non_none = [arg for arg in get_args(annotation) if arg is not types.NoneType]
        return non_none == [str]
    return False


def _main_accepts_string_positional(module: types.ModuleType) -> bool:
    """Return whether ``main`` takes a string-typed first positional CLI argument."""
    main_func = getattr(module, "main", None)
    if main_func is None or not _is_public_local_function(module.__name__, "main", main_func):
        return False
    try:
        hints = typing.get_type_hints(main_func)
    except (NameError, TypeError):
        return False
    for param in inspect.signature(main_func).parameters.values():
        if param.kind in (
            param.POSITIONAL_ONLY,
            param.POSITIONAL_OR_KEYWORD,
            param.VAR_POSITIONAL,
        ):
            return _is_str_type(hints.get(param.name))
        if param.kind is param.KEYWORD_ONLY:
            return False
    return False


def main(argv: list[str] | None = None) -> None:
    """Run the ``yeet`` command-line interface."""
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or raw[0] in {"-h", "--help"}:
        sys.stdout.write(
            "Usage: yeet FILE [FUNC] [args...]\n"
            "       yeet FUNC FILE [args...]   (as produced by a `#!yeet FUNC` shebang)\n"
            "       yeet FILE:FUNC [args...]\n"
            "\n"
            "Run a function from a Python file as a CLI. The `.py` file identifies\n"
            "itself; FUNC defaults to `main`. Anything after FILE/FUNC is forwarded\n"
            "to the function's own CLI (try `yeet FILE --help`).\n",
        )
        sys.exit(0 if raw else 2)

    # The `.py` file identifies itself. There are two explicit ways to pick a
    # function: a bare token *before* the file (what a `#!yeet FUNC` shebang
    # produces, since the kernel runs `yeet FUNC /path/to/script.py`), or the
    # `FILE.py:FUNC` form. Both bypass the file-first ambiguity check.
    explicit_func: str | None = None
    file_arg, *rest = raw
    if not file_arg.endswith(".py") and rest and rest[0].endswith(".py"):
        explicit_func, file_arg, *rest = raw
        explicit_func = explicit_func.replace("-", "_")

    # `FILE.py:FUNC` — split on the last colon so Windows drive letters survive.
    # FUNC may be written with hyphens (e.g. `add-item-to-index`); normalize to
    # underscores since that's what the actual Python identifier looks like.
    head, sep, tail = file_arg.rpartition(":")
    tail_normalized = tail.replace("-", "_")
    if sep and head.endswith(".py") and tail_normalized.isidentifier():
        file_arg, explicit_func = head, tail_normalized

    path = Path(file_arg).resolve()
    if not path.is_file():
        _create_script(path)
        return

    module = _load_module(path)

    func_name = explicit_func or "main"
    if explicit_func is None and rest and not rest[0].startswith("-"):
        candidate = rest[0].replace("-", "_")
        if _is_public_local_function(module.__name__, candidate, getattr(module, candidate, None)):
            if candidate != "main" and _main_accepts_string_positional(module):
                _print_error(
                    f"ambiguous: {candidate!r} is a function in {path.name}, but main() also "
                    f"takes a string argument, so {candidate!r} could be the function to run or "
                    f"a value for main.\n"
                    f"To pass it to main, run:  yeet {path.name} main {candidate}\n"
                    f"To run {candidate}(), give main a non-string first parameter or rename to "
                    f"remove the clash.",
                )
                sys.exit(2)
            func_name = candidate
            rest = rest[1:]

    func = getattr(module, func_name, None)
    if func is None or not _is_public_local_function(module.__name__, func_name, func):
        _print_error(
            f"{path.name} has no public function {func_name!r} to run "
            f"(yeetr runs a `def` or `async def` defined in the file).",
        )
        sys.exit(2)

    run(func, argv=rest, prog=f"yeet {path.name}")
