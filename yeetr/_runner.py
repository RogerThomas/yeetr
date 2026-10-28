"""Core signature-to-argparse conversion and CLI execution helpers."""

# pylint: disable=too-many-lines

from __future__ import annotations

import argparse
import asyncio
import datetime
import decimal
import enum
import inspect
import logging
import os
import sys
import types
import typing
import uuid
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from inspect import Parameter, Signature
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.text import Text
from rich_argparse import RichHelpFormatter

from ._metadata import Arg, Opt

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence


class _Unset:
    """Sentinel marking that an argparse default was not specified on the CLI."""

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<unset>"

    def __bool__(self) -> bool:
        return False


_UNSET = _Unset()


@dataclass(slots=True)
class _PathChecks:
    exists: bool = False
    file_okay: bool = True
    dir_okay: bool = True
    readable: bool = False
    writable: bool = False

    def is_active(self) -> bool:
        """Return whether any path validation rule is enabled."""
        return (
            self.exists or not self.file_okay or not self.dir_okay or self.readable or self.writable
        )


@dataclass
class _ParamInfo:  # pylint: disable=too-many-instance-attributes
    name: str
    is_positional: bool
    long_flag: str | None = None
    aliases: list[str] = field(default_factory=list[str])
    type_label: str = ""
    default_label: str = ""
    required: bool = False
    choices: list[str] = field(default_factory=list[str])
    help_text: str = ""
    metavar: str | None = None
    is_var_positional: bool = False
    envvar: str | None = None
    hidden: bool = False
    effective_type: Any = None
    is_list: bool = False
    is_tuple: bool = False
    is_literal: bool = False
    is_enum: bool = False
    path_checks: _PathChecks = field(default_factory=_PathChecks)
    has_default: bool = False
    default: Any = None
    parent_name: str | None = None
    parent_type: Any = None
    custom_parser: Callable[..., object] | None = None


def _is_enum_type(target: Any) -> bool:
    return inspect.isclass(target) and issubclass(target, enum.Enum)


def _is_dataclass_type(target: Any) -> bool:
    return inspect.isclass(target) and is_dataclass(target)


def _is_named_tuple_type(target: Any) -> bool:
    fields_attr = getattr(target, "_fields", None)
    return inspect.isclass(target) and issubclass(target, tuple) and isinstance(fields_attr, tuple)


def _type_name(target: Any) -> str:
    return getattr(target, "__name__", str(target))


def _is_variable_tuple(effective: Any) -> bool:
    args = get_args(effective)
    return len(args) == 2 and args[1] is Ellipsis


def _tuple_inner_types(effective: Any) -> tuple[Any, ...]:
    args = get_args(effective)
    if not args:
        raise YeetrError(
            "Bare tuple annotations are not supported; use tuple[T, ...] or tuple[T, U]."
        )
    if _is_variable_tuple(effective):
        return (args[0],)
    return args


def _type_label(
    effective: Any, is_list: bool, is_tuple: bool, is_literal: bool, is_enum: bool
) -> str:
    if effective is bool:
        return "flag"
    if is_literal or is_enum:
        return "choice"
    if is_list:
        (inner_t,) = get_args(effective)
        return f"list[{_type_name(inner_t)}]"
    if is_tuple:
        inner_types = _tuple_inner_types(effective)
        if _is_variable_tuple(effective):
            return f"tuple[{_type_name(inner_types[0])}, ...]"
        return f"tuple[{', '.join(_type_name(t) for t in inner_types)}]"
    return _type_name(effective)


def _default_label(has_default: bool, default: Any, effective: Any) -> str:
    if not has_default:
        return ""
    if effective is bool:
        return repr(default)
    return _format_default(default)


class YeetrError(Exception):
    """Raised when the function signature is not convertible into a CLI."""


def _snake_to_kebab(name: str) -> str:
    return name.replace("_", "-")


def _format_default(value: Any) -> str:
    if isinstance(value, (Path, datetime.date, datetime.time, uuid.UUID, decimal.Decimal)):
        return str(value)
    if isinstance(value, list):
        items = typing.cast(list[object], value)
        return f"[{', '.join(repr(item) for item in items)}]" if items else "[]"
    if isinstance(value, tuple):
        items = typing.cast(tuple[object, ...], value)
        return f"({', '.join(repr(item) for item in items)})" if items else "()"
    if isinstance(value, enum.Enum):
        return repr(value.value)
    return repr(value)


def _with_default_suffix(help_text: str | None, default: Any) -> str:
    base = help_text or ""
    suffix = f"(default: {_format_default(default)})"
    if not base:
        return suffix
    return f"{base} {suffix}"


def _is_optional(annotation: Any) -> tuple[bool, Any]:
    origin = get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [_resolve_type_alias(a) for a in get_args(annotation) if a is not types.NoneType]
        if len(args) == 1 and len(get_args(annotation)) == 2:
            return True, args[0]
    return False, annotation


def _resolve_type_alias(annotation: Any) -> Any:
    while isinstance(annotation, typing.TypeAliasType):
        annotation = annotation.__value__
    return annotation


def _merge_arg(outer: Arg, inner: Arg) -> Arg:
    return Arg(
        help=outer.help if outer.help is not None else inner.help,
        metavar=outer.metavar if outer.metavar is not None else inner.metavar,
        min=outer.min if outer.min else inner.min,
        exists=outer.exists or inner.exists,
        file_okay=outer.file_okay and inner.file_okay,
        dir_okay=outer.dir_okay and inner.dir_okay,
        readable=outer.readable or inner.readable,
        writable=outer.writable or inner.writable,
        parser=outer.parser if outer.parser is not None else inner.parser,
    )


def _merge_opt(outer: Opt, inner: Opt) -> Opt:
    return Opt(
        alias=outer.alias if outer.alias is not None else inner.alias,
        aliases=outer.aliases if outer.aliases else inner.aliases,
        help=outer.help if outer.help is not None else inner.help,
        metavar=outer.metavar if outer.metavar is not None else inner.metavar,
        envvar=outer.envvar if outer.envvar is not None else inner.envvar,
        hidden=outer.hidden or inner.hidden,
        exists=outer.exists or inner.exists,
        file_okay=outer.file_okay and inner.file_okay,
        dir_okay=outer.dir_okay and inner.dir_okay,
        readable=outer.readable or inner.readable,
        writable=outer.writable or inner.writable,
        parser=outer.parser if outer.parser is not None else inner.parser,
    )


def _merge_metadata(outer: Arg | Opt | None, inner: Arg | Opt | None) -> Arg | Opt | None:
    if outer is None:
        return inner
    if inner is None:
        return outer
    if isinstance(outer, Arg) and isinstance(inner, Arg):
        return _merge_arg(outer, inner)
    if isinstance(outer, Opt) and isinstance(inner, Opt):
        return _merge_opt(outer, inner)
    return outer


def _unwrap_annotated(annotation: Any) -> tuple[Any, Arg | Opt | None]:
    annotation = _resolve_type_alias(annotation)
    metadata: Arg | Opt | None = None
    if get_origin(annotation) is typing.Annotated:
        args = get_args(annotation)
        base = args[0]
        for extra in args[1:]:
            if isinstance(extra, (Arg, Opt)):
                metadata = extra
        inner_base, inner_metadata = _unwrap_annotated(base)
        return inner_base, _merge_metadata(metadata, inner_metadata)
    return annotation, metadata


def _resolved_collection_item_type(annotation: Any, param_name: str) -> Any:
    item_type, metadata = _unwrap_annotated(annotation)
    if metadata is not None:
        raise YeetrError(
            f"Parameter {param_name!r} has `Arg` or `Opt` metadata on a collection item; "
            "put it on the parameter annotation instead."
        )
    return item_type


def _validate_supported_scalar_type(target: Any, param_name: str) -> None:
    target = _resolve_type_alias(target)
    if get_origin(target) is Literal:
        return
    if target in {
        str,
        int,
        float,
        Path,
        bool,
        datetime.datetime,
        datetime.date,
        datetime.time,
        uuid.UUID,
        decimal.Decimal,
    } or _is_enum_type(target):
        return
    raise YeetrError(f"Parameter {param_name!r} has unsupported type {_type_name(target)!r}.")


def _validate_parameter_types(
    effective: Any, is_list: bool, is_tuple: bool, param_name: str
) -> None:
    if is_list:
        (item_type,) = get_args(effective)
        item_type = _resolved_collection_item_type(item_type, param_name)
        _validate_supported_scalar_type(item_type, param_name)
        return
    if is_tuple:
        for item_type in _tuple_inner_types(effective):
            _validate_supported_scalar_type(
                _resolved_collection_item_type(item_type, param_name), param_name
            )
        return
    _validate_supported_scalar_type(effective, param_name)


def _field_default(field_info: Any) -> tuple[bool, Any]:
    if field_info.default is not MISSING:
        return True, field_info.default
    if field_info.default_factory is not MISSING:
        return True, field_info.default_factory()
    return False, None


def _dataclass_type_from(annotation: Any) -> Any | None:
    base, _ = _unwrap_annotated(annotation)
    return base if _is_dataclass_type(base) else None


def _named_tuple_type_from(annotation: Any) -> Any | None:
    base, _ = _unwrap_annotated(annotation)
    return base if _is_named_tuple_type(base) else None


def _synthetic_parameter_for_field(dataclass_type: Any, field_info: Any) -> Parameter:
    type_hints = typing.get_type_hints(dataclass_type, include_extras=True)
    annotation = type_hints[field_info.name]
    _, metadata = _unwrap_annotated(annotation)
    has_default, default = _field_default(field_info)
    kind = Parameter.POSITIONAL_OR_KEYWORD if isinstance(metadata, Arg) else Parameter.KEYWORD_ONLY
    return Parameter(
        field_info.name,
        kind,
        default=default if has_default else Parameter.empty,
        annotation=annotation,
    )


def _synthetic_parameter_for_named_tuple_field(named_tuple_type: Any, field_name: str) -> Parameter:
    type_hints = typing.get_type_hints(named_tuple_type, include_extras=True)
    annotation = type_hints[field_name]
    _, metadata = _unwrap_annotated(annotation)
    field_defaults = typing.cast(dict[str, Any], vars(named_tuple_type)["_field_defaults"])
    has_default = field_name in field_defaults
    kind = Parameter.POSITIONAL_OR_KEYWORD if isinstance(metadata, Arg) else Parameter.KEYWORD_ONLY
    return Parameter(
        field_name,
        kind,
        default=field_defaults[field_name] if has_default else Parameter.empty,
        annotation=annotation,
    )


def _path_checks_from(metadata: Arg | Opt | None) -> _PathChecks:
    if metadata is None:
        return _PathChecks()
    return _PathChecks(
        exists=metadata.exists,
        file_okay=metadata.file_okay,
        dir_okay=metadata.dir_okay,
        readable=metadata.readable,
        writable=metadata.writable,
    )


def _validate_path_checks_target(
    checks: _PathChecks,
    effective: Any,
    is_list: bool,
    is_tuple: bool,
    param_name: str,
) -> None:
    if not checks.is_active():
        return
    if is_list:
        (inner_t,) = get_args(effective)
        targets = (_resolved_collection_item_type(inner_t, param_name),)
    elif is_tuple:
        targets = tuple(
            _resolved_collection_item_type(inner_t, param_name)
            for inner_t in _tuple_inner_types(effective)
        )
    else:
        targets = (effective,)
    invalid = [target for target in targets if target is not Path]
    if invalid:
        target = invalid[0]
        container = str(effective) if is_tuple else f"{_type_name(target)!r}"
        raise YeetrError(
            "Path validators (exists/file_okay/dir_okay/readable/writable) are only valid on "
            f"`Path` parameters; parameter {param_name!r} is of type "
            f"{container}.",
        )


def _apply_path_checks(path: Path, checks: _PathChecks) -> Path:
    if checks.exists and not path.exists():
        raise argparse.ArgumentTypeError(f"path must exist: {path}")
    if path.exists():
        if not checks.file_okay and path.is_file():
            raise argparse.ArgumentTypeError(f"not a regular file allowed: {path}")
        if not checks.dir_okay and path.is_dir():
            raise argparse.ArgumentTypeError(f"not a directory allowed: {path}")
    if checks.readable and not os.access(path, os.R_OK):
        raise argparse.ArgumentTypeError(f"path is not readable: {path}")
    if checks.writable and not os.access(path, os.W_OK):
        raise argparse.ArgumentTypeError(f"path is not writable: {path}")
    return path


def _scalar_parser(target: Any) -> Callable[[str], Any] | None:
    parsers: dict[Any, Callable[[str], Any]] = {
        datetime.datetime: datetime.datetime.fromisoformat,
        datetime.date: datetime.date.fromisoformat,
        datetime.time: datetime.time.fromisoformat,
        uuid.UUID: uuid.UUID,
        decimal.Decimal: decimal.Decimal,
    }
    return parsers.get(target)


def _coerce_value(raw: str, target: Any, param_name: str) -> Any:  # pylint: disable=too-many-return-statements
    if target is str:
        return raw
    if target is int:
        try:
            return int(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid int value for {param_name!r}: {raw!r}",
            ) from exc
    if target is float:
        try:
            return float(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid float value for {param_name!r}: {raw!r}",
            ) from exc
    if target is Path:
        return Path(raw)
    scalar_parser = _scalar_parser(target)
    if scalar_parser is not None:
        try:
            return scalar_parser(raw)
        except (ValueError, decimal.InvalidOperation) as exc:
            raise argparse.ArgumentTypeError(
                f"invalid {_type_name(target)} value for {param_name!r}: {raw!r}",
            ) from exc
    if target is bool:
        lowered = raw.lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
        raise argparse.ArgumentTypeError(f"invalid bool value for {param_name!r}: {raw!r}")
    if _is_enum_type(target):
        return _coerce_enum_value(raw, target, param_name)
    raise YeetrError(f"Unsupported type {target!r} for parameter {param_name!r}.")


def _enum_choices(target: Any) -> list[str]:
    return [str(member.value) for member in target]


def _coerce_enum_value(raw: str, target: Any, param_name: str) -> enum.Enum:
    for member in target:
        if raw == str(member.value):
            return member
    raise argparse.ArgumentTypeError(
        f"invalid choice {raw!r} for {param_name!r}; choose from {_enum_choices(target)!r}",
    )


def _coerce_nested_value(raw: str, target: Any, param_name: str) -> Any:
    target = _resolve_type_alias(target)
    origin = get_origin(target)
    if origin is Literal:
        return _literal_caster(get_args(target), param_name)(raw)
    return _coerce_value(raw, target, param_name)


def _coerce_tuple_value(
    raw: Any,
    effective: Any,
    param_name: str,
    path_checks: _PathChecks,
) -> tuple[Any, ...]:
    if isinstance(raw, tuple):
        return typing.cast(tuple[Any, ...], raw)
    if not isinstance(raw, list):
        raise argparse.ArgumentTypeError(f"invalid tuple value for {param_name!r}: {raw!r}")
    raw_values = typing.cast(list[str], raw)

    if _is_variable_tuple(effective):
        (inner_t,) = _tuple_inner_types(effective)
        values: tuple[Any, ...] = tuple(
            _coerce_nested_value(item, inner_t, param_name) for item in raw_values
        )
    else:
        inner_types = _tuple_inner_types(effective)
        if len(raw_values) != len(inner_types):
            raise argparse.ArgumentTypeError(
                f"expected {len(inner_types)} values for {param_name!r}; got {len(raw_values)}",
            )
        values = tuple(
            _coerce_nested_value(item, inner_t, param_name)
            for item, inner_t in zip(raw_values, inner_types, strict=True)
        )

    if path_checks.is_active():
        return tuple(
            _apply_path_checks(value, path_checks) if isinstance(value, Path) else value
            for value in values
        )
    return values


def _apply_custom_parser(
    value: Any,
    custom_parser: Callable[..., object],
    param_name: str,
    raw: str,
) -> Any:
    try:
        return custom_parser(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            f"invalid value for {param_name!r}: {raw!r} ({exc})",
        ) from exc


def _resolve_parser_input_type(custom_parser: Callable[..., object], param_name: str) -> Any:
    try:
        parser_sig = inspect.signature(custom_parser)
    except (TypeError, ValueError) as exc:
        raise YeetrError(f"parser for {param_name!r} must take exactly one argument") from exc
    parser_params = list(parser_sig.parameters.values())
    bad_kinds = {Parameter.KEYWORD_ONLY, Parameter.VAR_KEYWORD}
    if len(parser_params) != 1 or parser_params[0].kind in bad_kinds:
        raise YeetrError(f"parser for {param_name!r} must take exactly one argument")
    only = parser_params[0]
    if only.annotation is Parameter.empty:
        raise YeetrError(
            f"parser for {param_name!r} has an untyped parameter; add a type annotation",
        )
    annotation = only.annotation
    if isinstance(annotation, str):
        hint_source = custom_parser if inspect.isroutine(custom_parser) else custom_parser.__call__
        annotation = typing.get_type_hints(hint_source)[only.name]
    input_type = _resolve_type_alias(annotation)
    if input_type is bool or get_origin(input_type) in {list, tuple}:
        raise YeetrError(
            f"parser for {param_name!r} takes {_type_name(input_type)!r}; "
            "bool, list, and tuple parser input types are not supported",
        )
    return input_type


def _type_caster(
    target: Any,
    param_name: str,
    path_checks: _PathChecks | None = None,
    custom_parser: Callable[..., object] | None = None,
) -> Callable[[str], Any]:
    def cast(raw: str) -> Any:
        value = _coerce_nested_value(raw, target, param_name)
        if target is Path and path_checks is not None and path_checks.is_active():
            value = _apply_path_checks(value, path_checks)
        if custom_parser is not None:
            return _apply_custom_parser(value, custom_parser, param_name, raw)
        return value

    cast.__name__ = getattr(target, "__name__", "value")
    return cast


def _literal_caster(choices: tuple[Any, ...], param_name: str) -> Callable[[str], Any]:
    str_choices = {str(c): c for c in choices}

    def cast(raw: str) -> Any:
        if raw in str_choices:
            return str_choices[raw]
        raise argparse.ArgumentTypeError(
            f"invalid choice {raw!r} for {param_name!r}; choose from {sorted(str_choices)!r}",
        )

    cast.__name__ = "choice"
    return cast


def _choices_for(effective: Any, is_literal: bool, is_enum: bool) -> list[str]:
    if is_literal:
        return [str(c) for c in get_args(effective)]
    if is_enum:
        return _enum_choices(effective)
    return []


def _tuple_nargs(effective: Any, has_default: bool, *, is_positional: bool) -> str | int:
    if _is_variable_tuple(effective):
        return "*" if has_default else "+"
    inner_types = _tuple_inner_types(effective)
    if is_positional and has_default:
        return "*"
    return len(inner_types)


def _add_var_positional(
    parser: argparse.ArgumentParser,
    param: Parameter,
) -> _ParamInfo:
    annotation = param.annotation
    if annotation is Parameter.empty:
        raise YeetrError(f"Parameter {param.name!r} is missing a type annotation.")

    base, metadata = _unwrap_annotated(annotation)

    if isinstance(metadata, Opt):
        raise YeetrError(
            f"Variadic positional parameter {param.name!r} is annotated with `Opt`; "
            "use `Arg` on `*args`.",
        )

    if get_origin(base) is list:
        raise YeetrError(
            f"Variadic positional parameter {param.name!r} is annotated as `list[T]`; "
            f"annotate `*{param.name}` with the element type `T` instead.",
        )

    arg_meta = metadata if isinstance(metadata, Arg) else None
    if arg_meta is not None and arg_meta.parser is not None:
        raise YeetrError(
            f"parser= is not supported on variadic positional parameter {param.name!r}.",
        )
    help_text = arg_meta.help if arg_meta is not None else None
    metavar = arg_meta.metavar if arg_meta is not None else None
    minimum = arg_meta.min if arg_meta is not None else 0

    path_checks = _path_checks_from(arg_meta)
    _validate_path_checks_target(
        path_checks, base, is_list=False, is_tuple=False, param_name=param.name
    )

    nargs = "+" if minimum >= 1 else "*"
    display_metavar = metavar or _snake_to_kebab(param.name).upper()

    parser.add_argument(
        param.name,
        nargs=nargs,
        type=_type_caster(base, param.name, path_checks),
        metavar=display_metavar,
        help=help_text,
    )

    return _ParamInfo(
        name=param.name,
        is_positional=True,
        is_var_positional=True,
        type_label=getattr(base, "__name__", str(base)),
        default_label="",
        required=minimum >= 1,
        help_text=help_text or "",
        metavar=display_metavar,
        effective_type=base,
    )


def _add_parameter(  # pylint: disable=too-many-locals
    parser: argparse.ArgumentParser,
    param: Parameter,
) -> _ParamInfo:
    annotation = param.annotation
    if annotation is Parameter.empty:
        raise YeetrError(f"Parameter {param.name!r} is missing a type annotation.")

    base, metadata = _unwrap_annotated(annotation)
    is_optional, inner = _is_optional(base)
    effective = inner if is_optional else base

    is_keyword_only = param.kind is Parameter.KEYWORD_ONLY
    has_default = param.default is not Parameter.empty
    default = param.default if has_default else None

    if is_keyword_only and isinstance(metadata, Arg):
        raise YeetrError(
            f"Parameter {param.name!r} is keyword-only but is annotated with `Arg`; "
            f"use `Opt` for keyword-only parameters.",
        )
    if not is_keyword_only and isinstance(metadata, Opt):
        raise YeetrError(
            f"Parameter {param.name!r} is positional but is annotated with `Opt`; "
            "use `Arg` for positional parameters.",
        )

    custom_parser = metadata.parser if metadata is not None else None
    if custom_parser is not None:
        if get_origin(effective) in {list, tuple}:
            raise YeetrError(
                f"parser= is not supported on list/tuple parameters; "
                f"parameter {param.name!r} is annotated as {effective}.",
            )
        effective = _resolve_parser_input_type(custom_parser, param.name)

    origin = get_origin(effective)
    is_list = origin is list
    is_tuple = origin is tuple
    is_literal = custom_parser is None and origin is Literal
    is_enum = custom_parser is None and _is_enum_type(effective)

    if custom_parser is None:
        _validate_parameter_types(effective, is_list, is_tuple, param.name)

    help_text = metadata.help if metadata is not None else None
    metavar = metadata.metavar if metadata is not None else None

    path_checks = _path_checks_from(metadata)
    _validate_path_checks_target(path_checks, effective, is_list, is_tuple, param.name)

    envvar = metadata.envvar if isinstance(metadata, Opt) else None
    hidden = metadata.hidden if isinstance(metadata, Opt) else False

    info = _ParamInfo(
        name=param.name,
        is_positional=not is_keyword_only,
        type_label=_type_label(effective, is_list, is_tuple, is_literal, is_enum),
        default_label=_default_label(has_default, default, effective),
        required=not has_default,
        choices=_choices_for(effective, is_literal, is_enum),
        help_text=help_text or "",
        metavar=metavar,
        envvar=envvar,
        hidden=hidden,
        effective_type=effective,
        is_list=is_list,
        is_tuple=is_tuple,
        is_literal=is_literal,
        is_enum=is_enum,
        path_checks=path_checks,
        has_default=has_default,
        default=default,
        custom_parser=custom_parser,
    )

    if is_keyword_only:
        opt_metadata = metadata if isinstance(metadata, Opt) else None
        flags = _build_flags(param.name, opt_metadata)
        _add_option(
            parser=parser,
            param_name=param.name,
            flags=flags,
            effective=effective,
            is_list=is_list,
            is_tuple=is_tuple,
            is_literal=is_literal,
            is_enum=is_enum,
            has_default=has_default,
            default=default,
            help_text=help_text,
            metavar=metavar,
            path_checks=path_checks,
            envvar_active=envvar is not None,
            custom_parser=custom_parser,
        )
        long_flag, aliases = _split_flags_for_display(param.name, flags, effective, default)
        info.long_flag = long_flag
        info.aliases = aliases
    else:
        _add_positional(
            parser=parser,
            param_name=param.name,
            effective=effective,
            is_list=is_list,
            is_tuple=is_tuple,
            is_literal=is_literal,
            is_enum=is_enum,
            has_default=has_default,
            default=default,
            help_text=help_text,
            metavar=metavar,
            path_checks=path_checks,
            custom_parser=custom_parser,
        )
    return info


def _split_flags_for_display(
    param_name: str,
    flags: list[str],
    effective: Any,
    default: Any,
) -> tuple[str, list[str]]:
    if effective is bool and default is True:
        return f"--no-{_snake_to_kebab(param_name)}", []
    primary = _default_option_flag(param_name)
    others = [f for f in flags if f != primary]
    return primary, others


def _build_flags(param_name: str, metadata: Opt | None) -> list[str]:
    default_flag = _default_option_flag(param_name)
    extras: list[str] = []
    if metadata is not None:
        if metadata.alias:
            extras.append(_normalize_flag_alias(metadata.alias))
        extras += (_normalize_flag_alias(alias) for alias in metadata.aliases)
    shorts = [f for f in extras if f.startswith("-") and not f.startswith("--")]
    longs = [f for f in extras if f.startswith("--")]
    return _unique_flags([*shorts, default_flag, *longs])


def _default_option_flag(param_name: str) -> str:
    if len(param_name) == 1:
        return f"-{param_name}"
    return f"--{_snake_to_kebab(param_name)}"


def _normalize_flag_alias(alias: str) -> str:
    if alias.startswith("-"):
        return alias
    prefix = "-" if len(alias) == 1 else "--"
    return f"{prefix}{_snake_to_kebab(alias)}"


def _unique_flags(flags: list[str]) -> list[str]:
    unique: list[str] = []
    for flag in flags:
        if flag not in unique:
            unique.append(flag)
    return unique


def _add_option(  # pylint: disable=too-many-arguments,too-many-branches,too-many-locals
    *,
    parser: argparse.ArgumentParser,
    param_name: str,
    flags: list[str],
    effective: Any,
    is_list: bool,
    is_tuple: bool,
    is_literal: bool,
    is_enum: bool,
    has_default: bool,
    default: Any,
    help_text: str | None,
    metavar: str | None,
    path_checks: _PathChecks,
    envvar_active: bool,
    custom_parser: Callable[..., object] | None,
) -> None:
    if effective is bool:
        if not has_default and not envvar_active:
            raise YeetrError(
                f"Boolean option {param_name!r} must have a default (use `= False` or `= True`).",
            )
        bool_default: Any = _UNSET if envvar_active else default
        if default is False or (not has_default and envvar_active):
            parser.add_argument(
                *flags,
                dest=param_name,
                action="store_true",
                default=bool_default,
                help=help_text,
            )
        elif default is True:
            no_flag = f"--no-{_snake_to_kebab(param_name)}"
            parser.add_argument(
                no_flag,
                dest=param_name,
                action="store_false",
                default=bool_default,
                help=help_text,
            )
        else:
            raise YeetrError(f"Boolean option {param_name!r} has a non-bool default.")
        return

    rendered_help = _with_default_suffix(help_text, default) if has_default else help_text

    argparse_default: Any
    argparse_required: bool
    if envvar_active:
        argparse_default = _UNSET
        argparse_required = False
    else:
        argparse_default = default if has_default else None
        argparse_required = not has_default

    if is_literal:
        choices = get_args(effective)
        parser.add_argument(
            *flags,
            dest=param_name,
            type=_literal_caster(choices, param_name),
            choices=list(choices),
            default=argparse_default,
            required=argparse_required,
            help=rendered_help,
            metavar=metavar,
        )
        return

    if is_enum:
        parser.add_argument(
            *flags,
            dest=param_name,
            type=_type_caster(effective, param_name, path_checks),
            choices=list(effective),
            default=argparse_default,
            required=argparse_required,
            help=rendered_help,
            metavar=metavar,
        )
        return

    if is_list:
        (inner_t,) = get_args(effective)
        inner_t = _resolved_collection_item_type(inner_t, param_name)
        parser.add_argument(
            *flags,
            dest=param_name,
            type=_type_caster(inner_t, param_name, path_checks),
            action="append",
            default=None,
            required=argparse_required,
            help=rendered_help,
            metavar=metavar,
        )
        return

    if is_tuple:
        parser.add_argument(
            *flags,
            dest=param_name,
            nargs=_tuple_nargs(effective, has_default, is_positional=False),
            default=argparse_default,
            required=argparse_required,
            help=rendered_help,
            metavar=metavar,
        )
        return

    parser.add_argument(
        *flags,
        dest=param_name,
        type=_type_caster(effective, param_name, path_checks, custom_parser),
        default=argparse_default,
        required=argparse_required,
        help=rendered_help,
        metavar=metavar,
    )


def _add_positional(  # pylint: disable=too-many-arguments
    *,
    parser: argparse.ArgumentParser,
    param_name: str,
    effective: Any,
    is_list: bool,
    is_tuple: bool,
    is_literal: bool,
    is_enum: bool,
    has_default: bool,
    default: Any,
    help_text: str | None,
    metavar: str | None,
    path_checks: _PathChecks,
    custom_parser: Callable[..., object] | None,
) -> None:
    dest = param_name
    display_metavar = metavar or _snake_to_kebab(param_name).upper()
    nargs: str | None = None
    if has_default:
        nargs = "?"

    if effective is bool:
        raise YeetrError(
            f"Positional boolean parameter {param_name!r} is not supported. "
            f"Make it keyword-only (after `*`) to expose as a --flag.",
        )

    rendered_help = _with_default_suffix(help_text, default) if has_default else help_text

    if is_literal:
        choices = get_args(effective)
        kwargs: dict[str, Any] = {
            "type": _literal_caster(choices, param_name),
            "choices": list(choices),
            "help": rendered_help,
            "metavar": display_metavar,
        }
        if has_default:
            kwargs["nargs"] = "?"
            kwargs["default"] = default
        parser.add_argument(dest, **kwargs)
        return

    if is_enum:
        kwargs: dict[str, Any] = {
            "type": _type_caster(effective, param_name, path_checks),
            "choices": list(effective),
            "help": rendered_help,
            "metavar": display_metavar,
        }
        if has_default:
            kwargs["nargs"] = "?"
            kwargs["default"] = default
        parser.add_argument(dest, **kwargs)
        return

    if is_list:
        (inner_t,) = get_args(effective)
        inner_t = _resolved_collection_item_type(inner_t, param_name)
        kwargs = {
            "type": _type_caster(inner_t, param_name, path_checks),
            "nargs": "*" if has_default else "+",
            "help": rendered_help,
            "metavar": display_metavar,
        }
        if has_default:
            kwargs["default"] = list(default) if default is not None else []
        parser.add_argument(dest, **kwargs)
        return

    if is_tuple:
        kwargs = {
            "nargs": _tuple_nargs(effective, has_default, is_positional=True),
            "help": rendered_help,
            "metavar": display_metavar,
        }
        if has_default:
            kwargs["default"] = default
        parser.add_argument(dest, **kwargs)
        return

    kwargs = {
        "type": _type_caster(effective, param_name, path_checks, custom_parser),
        "help": rendered_help,
        "metavar": display_metavar,
    }
    if nargs is not None:
        kwargs["nargs"] = nargs
    if has_default:
        kwargs["default"] = default
    parser.add_argument(dest, **kwargs)


def _add_dataclass_parameter(
    parser: argparse.ArgumentParser,
    param: Parameter,
    dataclass_type: Any,
) -> list[_ParamInfo]:
    infos: list[_ParamInfo] = []
    for field_info in fields(dataclass_type):
        if not field_info.init:
            continue
        field_param = _synthetic_parameter_for_field(dataclass_type, field_info)
        info = _add_parameter(parser, field_param)
        info.parent_name = param.name
        info.parent_type = dataclass_type
        infos.append(info)
    if not infos:
        raise YeetrError(f"Dataclass parameter {param.name!r} has no init fields.")
    return infos


def _add_named_tuple_parameter(
    parser: argparse.ArgumentParser,
    param: Parameter,
    named_tuple_type: Any,
) -> list[_ParamInfo]:
    infos: list[_ParamInfo] = []
    for field_name in named_tuple_type._fields:
        field_param = _synthetic_parameter_for_named_tuple_field(named_tuple_type, field_name)
        info = _add_parameter(parser, field_param)
        info.parent_name = param.name
        info.parent_type = named_tuple_type
        infos.append(info)
    if not infos:
        raise YeetrError(f"NamedTuple parameter {param.name!r} has no fields.")
    return infos


def _build_parser(
    func: Callable[..., Any],
    prog: str | None = None,
) -> tuple[argparse.ArgumentParser, Signature, list[_ParamInfo]]:
    sig = inspect.signature(func)
    doc = inspect.getdoc(func)
    resolved_prog = prog or _default_prog()
    parser = argparse.ArgumentParser(
        prog=resolved_prog,
        description=doc,
        add_help=True,
        formatter_class=RichHelpFormatter,
    )
    infos: list[_ParamInfo] = []
    for param in sig.parameters.values():
        if param.kind is Parameter.VAR_KEYWORD:
            raise YeetrError(
                f"Variadic keyword parameter **{param.name} is not supported.",
            )
        if param.kind is Parameter.VAR_POSITIONAL:
            infos.append(_add_var_positional(parser, param))
            continue
        dataclass_type = _dataclass_type_from(param.annotation)
        if dataclass_type is not None:
            if param.kind is Parameter.KEYWORD_ONLY:
                raise YeetrError(
                    f"Dataclass parameter {param.name!r} must not be keyword-only.",
                )
            infos += _add_dataclass_parameter(parser, param, dataclass_type)
            continue
        named_tuple_type = _named_tuple_type_from(param.annotation)
        if named_tuple_type is not None:
            if param.kind is Parameter.KEYWORD_ONLY:
                raise YeetrError(
                    f"NamedTuple parameter {param.name!r} must not be keyword-only.",
                )
            infos += _add_named_tuple_parameter(parser, param, named_tuple_type)
            continue
        infos.append(_add_parameter(parser, param))
    _install_rich_help(parser, resolved_prog, doc, infos)
    return parser, sig, infos


def _install_rich_help(
    parser: argparse.ArgumentParser,
    prog: str,
    doc: str | None,
    infos: list[_ParamInfo],
) -> None:
    def print_help(file: Any = None) -> None:
        _render_rich_help(prog, doc, infos, file=file)

    def error(message: str) -> None:
        _render_rich_help(prog, doc, infos, file=sys.stderr)
        console = Console(file=sys.stderr)
        console.print()
        console.print(Text("Errors:", style="bold red"))
        console.print(f"{prog}: error: {message}", style="red")
        parser.exit(2)

    parser.print_help = print_help  # type: ignore[method-assign]
    parser.error = error  # type: ignore[method-assign]


def _build_usage(prog: str, infos: list[_ParamInfo]) -> str:
    parts: list[str] = [prog, "[-h]"]
    for info in infos:
        if info.is_positional:
            continue
        if info.hidden:
            continue
        flag = info.long_flag or f"--{_snake_to_kebab(info.name)}"
        if info.type_label == "flag":
            token = flag
        else:
            metavar = info.metavar or info.name.upper()
            token = f"{flag} {metavar}"
        parts.append(token if info.required else f"[{token}]")
    for info in infos:
        if info.is_positional:
            display = info.metavar or _snake_to_kebab(info.name).upper()
            if info.is_var_positional:
                parts.append(f"{display} [{display} ...]" if info.required else f"[{display} ...]")
            else:
                parts.append(display if info.required else f"[{display}]")
    return " ".join(parts)


def _render_rich_help(
    prog: str,
    doc: str | None,
    infos: list[_ParamInfo],
    *,
    file: Any = None,
) -> None:
    console = Console(file=file) if file is not None else Console()

    usage = _build_usage(prog, infos)
    console.print(Text("Usage: ", style="bold yellow"), end="")
    console.print(usage)
    if doc:
        console.print()
        console.print(doc)

    positional = [i for i in infos if i.is_positional]
    options = [i for i in infos if not i.is_positional]

    if positional:
        console.print()
        console.print(_arguments_table(positional))

    console.print()
    console.print(_options_table(options))


def _required_text(required: bool) -> Text:
    return Text("yes", style="bold red") if required else Text("no", style="dim")


def _arguments_table(infos: list[_ParamInfo]) -> Table:
    table = Table(
        title="▸ Arguments",
        title_style="bold cyan",
        title_justify="left",
        show_lines=False,
    )
    table.add_column("Name", style="bold green", no_wrap=True)
    table.add_column("Type", style="magenta", no_wrap=True)
    table.add_column("Required", no_wrap=True)
    table.add_column("Default", style="yellow", no_wrap=True)
    table.add_column("Choices", style="blue")
    table.add_column("Description", style="white")
    for info in infos:
        display = info.metavar or _snake_to_kebab(info.name).upper()
        table.add_row(
            display,
            info.type_label,
            _required_text(info.required),
            info.default_label or "-",
            ", ".join(info.choices) if info.choices else "-",
            info.help_text or "-",
        )
    return table


def _options_table(infos: list[_ParamInfo]) -> Table:
    visible = [i for i in infos if not i.hidden]
    show_envvar = any(i.envvar for i in visible)
    table = Table(
        title="⚙ Options", title_style="bold cyan", title_justify="left", show_lines=False
    )
    table.add_column("Name", style="bold green", no_wrap=True)
    table.add_column("Alias(es)", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta", no_wrap=True)
    table.add_column("Required", no_wrap=True)
    table.add_column("Default", style="yellow", no_wrap=True)
    table.add_column("Choices", style="blue")
    if show_envvar:
        table.add_column("Env var", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    help_row: list[str | Text] = [
        "--help",
        "-h",
        "flag",
        _required_text(False),
        "-",
        "-",
    ]
    if show_envvar:
        help_row.append("-")
    help_row.append("show this help message and exit")
    table.add_row(*help_row)

    for info in visible:
        row: list[str | Text] = [
            info.long_flag or f"--{_snake_to_kebab(info.name)}",
            ", ".join(info.aliases) if info.aliases else "-",
            info.type_label,
            _required_text(info.required),
            info.default_label or "-",
            ", ".join(info.choices) if info.choices else "-",
        ]
        if show_envvar:
            row.append(info.envvar or "-")
        row.append(info.help_text or "-")
        table.add_row(*row)
    return table


def _default_prog() -> str:
    argv0 = sys.argv[0] if sys.argv else "app"
    return Path(argv0).name or "app"


def _build_call_args(
    sig: Signature,
    namespace: argparse.Namespace,
    infos: list[_ParamInfo],
) -> tuple[list[Any], dict[str, Any]]:
    has_var_positional = any(p.kind is Parameter.VAR_POSITIONAL for p in sig.parameters.values())
    dataclass_infos: dict[str, list[_ParamInfo]] = {}
    for info in infos:
        if info.parent_name is None:
            continue
        if info.parent_name not in dataclass_infos:
            dataclass_infos[info.parent_name] = []
        dataclass_infos[info.parent_name].append(info)

    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name in dataclass_infos:
            binding_infos = dataclass_infos[name]
            parent_type = binding_infos[0].parent_type
            value = parent_type(
                **{info.name: getattr(namespace, info.name) for info in binding_infos},
            )
        else:
            value = getattr(namespace, name)
        if param.kind is Parameter.VAR_POSITIONAL:
            args += value
        elif has_var_positional and param.kind is not Parameter.KEYWORD_ONLY:
            args.append(value)
        else:
            kwargs[name] = value
    return args, kwargs


def _normalize_parsed_values(
    parser: argparse.ArgumentParser,
    namespace: argparse.Namespace,
    infos: list[_ParamInfo],
) -> None:
    for info in infos:
        if not info.is_tuple:
            continue
        value = getattr(namespace, info.name)
        if isinstance(value, _Unset):
            continue
        try:
            setattr(
                namespace,
                info.name,
                _coerce_tuple_value(value, info.effective_type, info.name, info.path_checks),
            )
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))


def _coerce_envvar_value(raw: str, info: _ParamInfo) -> Any:
    effective = info.effective_type
    if info.is_list:
        (inner_t,) = get_args(effective)
        parts = raw.split(os.pathsep) if raw else []
        return [_coerce_value(p, inner_t, info.name) for p in parts]
    if info.is_tuple:
        parts = raw.split(os.pathsep) if raw else []
        return _coerce_tuple_value(parts, effective, info.name, info.path_checks)
    if info.is_literal:
        return _literal_caster(get_args(effective), info.name)(raw)
    value = _coerce_nested_value(raw, effective, info.name)
    if info.custom_parser is not None:
        return _apply_custom_parser(value, info.custom_parser, info.name, raw)
    return value


def _list_default(info: _ParamInfo) -> list[Any]:
    if info.default is None:
        return []
    return list(typing.cast(list[Any], info.default))


def _resolve_envvars(
    parser: argparse.ArgumentParser,
    namespace: argparse.Namespace,
    infos: list[_ParamInfo],
) -> None:
    for info in infos:
        current = getattr(namespace, info.name, _UNSET)
        if info.envvar is None:
            if info.is_list and current is None:
                setattr(namespace, info.name, _list_default(info))
            continue
        if current is not None and not isinstance(current, _Unset):
            continue
        raw = os.environ.get(info.envvar)
        if raw is not None:
            try:
                setattr(namespace, info.name, _coerce_envvar_value(raw, info))
            except argparse.ArgumentTypeError as exc:
                parser.error(f"environment variable {info.envvar}: {exc}")
        elif info.has_default:
            value = _list_default(info) if info.is_list else info.default
            setattr(namespace, info.name, value)
        else:
            raise YeetrError(
                f"option {info.name!r} requires either a CLI value or "
                f"environment variable {info.envvar!r}",
            )


def _setup_logging(namespace: argparse.Namespace) -> None:
    if logging.getLogger().handlers:
        return
    raw_level = getattr(namespace, "log_level", "info")
    level_name = raw_level.upper() if isinstance(raw_level, str) else "INFO"
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s]: %(message)s",
        handlers=[RichHandler(show_time=False, show_level=False)],
    )


def run[T](
    func: Callable[..., T] | Callable[..., Awaitable[T]],
    argv: Sequence[str] | None = None,
    *,
    prog: str | None = None,
    should_setup_logging: bool = True,
) -> T:
    """Run ``func`` as a CLI.

    The function signature defines the CLI:
    - positional parameters become positional CLI args
    - keyword-only parameters (after ``*``) become options

    If ``func`` is async, the coroutine is executed via ``uvloop.run``
    when the optional ``uvloop`` extra is installed, otherwise via
    ``asyncio.run``.

    Pass ``argv`` to bypass ``sys.argv`` (useful for tests).

    When ``should_setup_logging`` is ``True`` (the default), Rich-based
    logging is configured after argument parsing and before invoking
    ``func``. If the parsed namespace contains a ``log_level`` string, its
    value drives the level; otherwise INFO is used. Setup is idempotent:
    if the root logger already has handlers, no changes are made. Set
    ``should_setup_logging=False`` to take full control of logging
    yourself.
    """
    print(file=sys.stderr)
    parser, sig, infos = _build_parser(func, prog=prog)
    raw_argv = list(sys.argv[1:]) if argv is None else list(argv)
    namespace = parser.parse_args(raw_argv)
    _normalize_parsed_values(parser, namespace, infos)
    _resolve_envvars(parser, namespace, infos)
    if should_setup_logging:
        _setup_logging(namespace)
    call_args, call_kwargs = _build_call_args(sig, namespace, infos)
    result = func(*call_args, **call_kwargs)
    if inspect.iscoroutine(result):
        return typing.cast(T, _run_coroutine(result))
    return typing.cast(T, result)


def _run_coroutine(coro: Any) -> Any:
    try:
        import uvloop  # pyright: ignore[reportMissingImports]  # pylint: disable=import-outside-toplevel
    except ImportError:
        uvloop = None
    if uvloop is None:
        return asyncio.run(coro)
    return uvloop.run(coro)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
