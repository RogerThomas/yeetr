"""Tests for yeetr's signature-driven CLI runner."""

# pylint: disable=import-outside-toplevel,missing-class-docstring,missing-function-docstring,redefined-builtin,too-many-lines

import asyncio
import datetime
import decimal
import enum
import logging
import stat
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

import pytest
from rich.logging import RichHandler

import yeetr
from yeetr import Arg, Opt, YeetrError


@pytest.fixture(autouse=True)
def _reset_root_logger() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


def test_positional_and_keyword_default() -> None:
    captured: dict[str, object] = {}

    def main(thing: int, *, n: float = 0.1) -> None:
        captured["thing"] = thing
        captured["n"] = n

    yeetr.run(main, argv=["5", "-n", "0.2"])
    assert captured == {"thing": 5, "n": 0.2}


def test_one_letter_option_uses_short_flag_only() -> None:
    def main(*, n: float = 0.1) -> None:
        del n

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["--n", "0.2"])


def test_default_used_when_omitted() -> None:
    captured: dict[str, object] = {}

    def main(thing: int, *, n: float = 0.1) -> None:
        captured["thing"] = thing
        captured["n"] = n

    yeetr.run(main, argv=["5"])
    assert captured == {"thing": 5, "n": 0.1}


def test_required_option() -> None:
    def main(*, n: float) -> None:
        del n

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=[])


def test_bool_false_default_flag() -> None:
    captured: dict[str, object] = {}

    def main(*, loud: bool = False) -> None:
        captured["loud"] = loud

    yeetr.run(main, argv=["--loud"])
    assert captured == {"loud": True}

    yeetr.run(main, argv=[])
    assert captured == {"loud": False}


def test_bool_true_default_uses_no_flag() -> None:
    captured: dict[str, object] = {}

    def main(*, loud: bool = True) -> None:
        captured["loud"] = loud

    yeetr.run(main, argv=["--no-loud"])
    assert captured == {"loud": False}

    yeetr.run(main, argv=[])
    assert captured == {"loud": True}


def test_required_bool_rejected() -> None:
    def main(*, flag: bool) -> None:
        del flag

    with pytest.raises(YeetrError):
        yeetr.run(main, argv=[])


def test_path_parsing() -> None:
    captured: dict[str, object] = {}

    def main(path: Path, *, output: Path | None = None) -> None:
        captured["path"] = path
        captured["output"] = output

    yeetr.run(main, argv=["input.pdf", "--output", "out.txt"])
    assert captured == {"path": Path("input.pdf"), "output": Path("out.txt")}


def test_optional_default_none() -> None:
    captured: dict[str, object] = {}

    def main(*, output: Path | None = None) -> None:
        captured["output"] = output

    yeetr.run(main, argv=[])
    assert captured == {"output": None}


def test_literal_choices() -> None:
    captured: dict[str, object] = {}

    def main(*, format: Literal["json", "csv"] = "json") -> None:
        captured["format"] = format

    yeetr.run(main, argv=["--format", "csv"])
    assert captured == {"format": "csv"}


def test_literal_rejects_bad_choice() -> None:
    def main(*, format: Literal["json", "csv"] = "json") -> None:
        del format

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["--format", "xml"])


class _Format(enum.StrEnum):
    JSON = "json"
    CSV = "csv"


class _Level(enum.IntEnum):
    LOW = 1
    HIGH = 2


def test_enum_option() -> None:
    captured: dict[str, object] = {}

    def main(*, format: _Format = _Format.JSON) -> None:
        captured["format"] = format

    yeetr.run(main, argv=["--format", "csv"])
    assert captured == {"format": _Format.CSV}


def test_enum_positional() -> None:
    captured: dict[str, object] = {}

    def main(level: _Level) -> None:
        captured["level"] = level

    yeetr.run(main, argv=["2"])
    assert captured == {"level": _Level.HIGH}


def test_enum_rejects_bad_choice() -> None:
    def main(*, format: _Format = _Format.JSON) -> None:
        del format

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["--format", "xml"])


def test_enum_help_shows_choices() -> None:
    from io import StringIO

    from rich.console import Console

    from yeetr._runner import _build_parser  # pyright: ignore[reportPrivateUsage]

    def main(*, format: _Format = _Format.JSON) -> None:
        del format

    parser, _, _ = _build_parser(main, prog="app")
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    parser.print_help(file=console.file)
    output = buf.getvalue()
    assert "json" in output
    assert "csv" in output


def test_tuple_positional_fixed_width() -> None:
    captured: dict[str, object] = {}

    def main(point: tuple[int, float]) -> None:
        captured["point"] = point

    yeetr.run(main, argv=["1", "2.5"])
    assert captured == {"point": (1, 2.5)}


def test_tuple_option_fixed_width() -> None:
    captured: dict[str, object] = {}

    def main(*, point: tuple[int, float]) -> None:
        captured["point"] = point

    yeetr.run(main, argv=["--point", "1", "2.5"])
    assert captured == {"point": (1, 2.5)}


def test_tuple_option_variable_width() -> None:
    captured: dict[str, object] = {}

    def main(*, values: tuple[int, ...] = ()) -> None:
        captured["values"] = values

    yeetr.run(main, argv=["--values", "1", "2", "3"])
    assert captured == {"values": (1, 2, 3)}


def test_tuple_rejects_bad_value() -> None:
    def main(point: tuple[int, float]) -> None:
        del point

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["1", "bad"])


def test_datetime_parsing() -> None:
    captured: dict[str, object] = {}

    def main(started: datetime.datetime) -> None:
        captured["started"] = started

    yeetr.run(main, argv=["2020-01-02T03:04:05+00:00"])
    assert captured == {"started": datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)}


def test_datetime_rejects_bad_value() -> None:
    def main(started: datetime.datetime) -> None:
        del started

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["not-a-datetime"])


def test_datetime_optional_default_none() -> None:
    captured: dict[str, object] = {}

    def main(*, started: datetime.datetime | None = None) -> None:
        captured["started"] = started

    yeetr.run(main, argv=[])
    assert captured == {"started": None}


def test_datetime_list_option() -> None:
    captured: dict[str, object] = {}

    def main(*, at: list[datetime.datetime] | None = None) -> None:
        captured["at"] = at

    yeetr.run(main, argv=["--at", "2020-01-02T03:04:05+00:00", "--at", "2021-06-07T08:09:10+00:00"])
    assert captured == {
        "at": [
            datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
            datetime.datetime(2021, 6, 7, 8, 9, 10, tzinfo=datetime.UTC),
        ]
    }


def test_envvar_datetime(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, started: Annotated[datetime.datetime | None, Opt(envvar="STARTED")] = None) -> None:
        captured["started"] = started

    monkeypatch.setenv("STARTED", "2020-01-02T03:04:05+00:00")
    yeetr.run(main, argv=[])
    assert captured == {"started": datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)}


def test_date_parsing() -> None:
    captured: dict[str, object] = {}

    def main(day: datetime.date) -> None:
        captured["day"] = day

    yeetr.run(main, argv=["2020-01-02"])
    assert captured == {"day": datetime.date(2020, 1, 2)}


def test_date_rejects_bad_value() -> None:
    def main(day: datetime.date) -> None:
        del day

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["not-a-date"])


def test_date_optional_default_none() -> None:
    captured: dict[str, object] = {}

    def main(*, day: datetime.date | None = None) -> None:
        captured["day"] = day

    yeetr.run(main, argv=[])
    assert captured == {"day": None}


def test_date_list_option() -> None:
    captured: dict[str, object] = {}

    def main(*, day: list[datetime.date] | None = None) -> None:
        captured["day"] = day

    yeetr.run(main, argv=["--day", "2020-01-02", "--day", "2021-06-07"])
    assert captured == {"day": [datetime.date(2020, 1, 2), datetime.date(2021, 6, 7)]}


def test_envvar_date(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, day: Annotated[datetime.date | None, Opt(envvar="DAY")] = None) -> None:
        captured["day"] = day

    monkeypatch.setenv("DAY", "2020-01-02")
    yeetr.run(main, argv=[])
    assert captured == {"day": datetime.date(2020, 1, 2)}


def test_time_parsing() -> None:
    captured: dict[str, object] = {}

    def main(at: datetime.time) -> None:
        captured["at"] = at

    yeetr.run(main, argv=["03:04:05"])
    assert captured == {"at": datetime.time(3, 4, 5)}


def test_time_rejects_bad_value() -> None:
    def main(at: datetime.time) -> None:
        del at

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["not-a-time"])


def test_time_optional_default_none() -> None:
    captured: dict[str, object] = {}

    def main(*, at: datetime.time | None = None) -> None:
        captured["at"] = at

    yeetr.run(main, argv=[])
    assert captured == {"at": None}


def test_time_list_option() -> None:
    captured: dict[str, object] = {}

    def main(*, at: list[datetime.time] | None = None) -> None:
        captured["at"] = at

    yeetr.run(main, argv=["--at", "03:04:05", "--at", "06:07:08"])
    assert captured == {"at": [datetime.time(3, 4, 5), datetime.time(6, 7, 8)]}


def test_envvar_time(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, at: Annotated[datetime.time | None, Opt(envvar="AT")] = None) -> None:
        captured["at"] = at

    monkeypatch.setenv("AT", "03:04:05")
    yeetr.run(main, argv=[])
    assert captured == {"at": datetime.time(3, 4, 5)}


def test_uuid_parsing() -> None:
    captured: dict[str, object] = {}

    def main(token: uuid.UUID) -> None:
        captured["token"] = token

    yeetr.run(main, argv=["00000000-0000-0000-0000-000000000001"])
    assert captured == {"token": uuid.UUID("00000000-0000-0000-0000-000000000001")}


def test_uuid_rejects_bad_value() -> None:
    def main(token: uuid.UUID) -> None:
        del token

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["not-a-uuid"])


def test_uuid_optional_default_none() -> None:
    captured: dict[str, object] = {}

    def main(*, token: uuid.UUID | None = None) -> None:
        captured["token"] = token

    yeetr.run(main, argv=[])
    assert captured == {"token": None}


def test_uuid_list_option() -> None:
    captured: dict[str, object] = {}

    def main(*, token: list[uuid.UUID] | None = None) -> None:
        captured["token"] = token

    yeetr.run(
        main,
        argv=[
            "--token",
            "00000000-0000-0000-0000-000000000001",
            "--token",
            "00000000-0000-0000-0000-000000000002",
        ],
    )
    assert captured == {
        "token": [
            uuid.UUID("00000000-0000-0000-0000-000000000001"),
            uuid.UUID("00000000-0000-0000-0000-000000000002"),
        ]
    }


def test_envvar_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, token: Annotated[uuid.UUID | None, Opt(envvar="TOKEN")] = None) -> None:
        captured["token"] = token

    monkeypatch.setenv("TOKEN", "00000000-0000-0000-0000-000000000001")
    yeetr.run(main, argv=[])
    assert captured == {"token": uuid.UUID("00000000-0000-0000-0000-000000000001")}


def test_decimal_parsing() -> None:
    captured: dict[str, object] = {}

    def main(amount: decimal.Decimal) -> None:
        captured["amount"] = amount

    yeetr.run(main, argv=["1.5"])
    assert captured == {"amount": decimal.Decimal("1.5")}


def test_decimal_rejects_bad_value() -> None:
    def main(amount: decimal.Decimal) -> None:
        del amount

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["not-a-decimal"])


def test_decimal_optional_default_none() -> None:
    captured: dict[str, object] = {}

    def main(*, amount: decimal.Decimal | None = None) -> None:
        captured["amount"] = amount

    yeetr.run(main, argv=[])
    assert captured == {"amount": None}


def test_decimal_list_option() -> None:
    captured: dict[str, object] = {}

    def main(*, amount: list[decimal.Decimal] | None = None) -> None:
        captured["amount"] = amount

    yeetr.run(main, argv=["--amount", "1.5", "--amount", "2.5"])
    assert captured == {"amount": [decimal.Decimal("1.5"), decimal.Decimal("2.5")]}


def test_envvar_decimal(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, amount: Annotated[decimal.Decimal | None, Opt(envvar="AMOUNT")] = None) -> None:
        captured["amount"] = amount

    monkeypatch.setenv("AMOUNT", "1.5")
    yeetr.run(main, argv=[])
    assert captured == {"amount": decimal.Decimal("1.5")}


def test_tuple_of_dates() -> None:
    captured: dict[str, object] = {}

    def main(*, span: tuple[datetime.date, datetime.date]) -> None:
        captured["span"] = span

    yeetr.run(main, argv=["--span", "2020-01-02", "2021-06-07"])
    assert captured == {"span": (datetime.date(2020, 1, 2), datetime.date(2021, 6, 7))}


def test_var_positional_decimals() -> None:
    captured: dict[str, object] = {}

    def main(*amounts: decimal.Decimal) -> None:
        captured["amounts"] = amounts

    yeetr.run(main, argv=["1.5", "2.5"])
    assert captured == {"amounts": (decimal.Decimal("1.5"), decimal.Decimal("2.5"))}


def test_optional_positional_uses_default_when_omitted() -> None:
    captured: dict[str, object] = {}

    def main(count: int = 3) -> None:
        captured["count"] = count

    yeetr.run(main, argv=[])
    assert captured == {"count": 3}


def test_optional_positional_list_uses_default_copy() -> None:
    captured: dict[str, object] = {}

    def main(tags: list[str] | None = None) -> None:
        captured["tags"] = tags

    yeetr.run(main, argv=[])
    assert captured == {"tags": []}


def test_optional_positional_literal_uses_default_when_omitted() -> None:
    captured: dict[str, object] = {}

    def main(format: Literal["json", "csv"] = "json") -> None:
        captured["format"] = format

    yeetr.run(main, argv=[])
    assert captured == {"format": "json"}


def test_positional_bool_rejected() -> None:
    def main(loud: _BoolAlias) -> None:
        del loud

    with pytest.raises(YeetrError, match="Positional boolean"):
        yeetr.run(main, argv=["true"])


def test_envvar_enum(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, format: Annotated[_Format, Opt(envvar="FMT")] = _Format.JSON) -> None:
        captured["format"] = format

    monkeypatch.setenv("FMT", "csv")
    yeetr.run(main, argv=[])
    assert captured == {"format": _Format.CSV}


def test_envvar_tuple_splits_on_pathsep(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    captured: dict[str, object] = {}

    def main(*, point: Annotated[tuple[int, float], Opt(envvar="POINT")] = (0, 0.0)) -> None:
        captured["point"] = point

    monkeypatch.setenv("POINT", f"1{os.pathsep}2.5")
    yeetr.run(main, argv=[])
    assert captured == {"point": (1, 2.5)}


def test_async_main() -> None:
    captured: dict[str, object] = {}

    async def main(name: str, *, loud: bool = False) -> str:
        await asyncio.sleep(0)
        captured["name"] = name
        captured["loud"] = loud
        return name.upper() if loud else name

    result = yeetr.run(main, argv=["Roger", "--loud"])
    assert captured == {"name": "Roger", "loud": True}
    assert result == "ROGER"


def test_kebab_case_conversion() -> None:
    captured: dict[str, object] = {}

    def main(input_file: Path, *, dry_run: bool = False, max_items: int = 10) -> None:
        captured["input_file"] = input_file
        captured["dry_run"] = dry_run
        captured["max_items"] = max_items

    yeetr.run(main, argv=["./file.pdf", "--dry-run", "--max-items", "20"])
    assert captured == {"input_file": Path("./file.pdf"), "dry_run": True, "max_items": 20}


def test_list_repeated_options() -> None:
    captured: dict[str, object] = {}

    def main(*, tag: list[str] | None = None) -> None:
        if tag is None:
            tag = []
        captured["tag"] = tag

    yeetr.run(main, argv=["--tag", "a", "--tag", "b"])
    assert captured == {"tag": ["a", "b"]}


def test_repeated_option_replaces_list_default() -> None:
    captured: dict[str, object] = {}

    # pylint: disable-next=dangerous-default-value
    def main(*, model: list[str] = ["default"]) -> None:  # noqa: B006
        captured["model"] = model

    yeetr.run(main, argv=[])
    assert captured == {"model": ["default"]}

    yeetr.run(main, argv=["--model", "a", "--model", "b"])
    assert captured == {"model": ["a", "b"]}


def test_opt_alias_and_help() -> None:
    captured: dict[str, object] = {}

    def main(*, workers: Annotated[int, Opt(alias="-w", help="Worker count")] = 4) -> None:
        captured["workers"] = workers

    yeetr.run(main, argv=["-w", "8"])
    assert captured == {"workers": 8}

    yeetr.run(main, argv=["--workers", "3"])
    assert captured == {"workers": 3}


def test_opt_bare_aliases_are_normalized() -> None:
    captured: dict[str, object] = {}

    def main(*, name: Annotated[str, Opt(alias="n")] = "default") -> None:
        captured["name"] = name

    yeetr.run(main, argv=["-n", "name"])
    assert captured == {"name": "name"}


def test_opt_bare_long_alias_is_normalized() -> None:
    captured: dict[str, object] = {}

    def main(*, name: Annotated[str, Opt(alias="who")] = "default") -> None:
        captured["name"] = name

    yeetr.run(main, argv=["--who", "name"])
    assert captured == {"name": "name"}


def test_opt_no_default_required() -> None:
    captured: dict[str, object] = {}

    def main(*, workers: Annotated[int, Opt(alias="-w", help="Worker count")]) -> None:
        captured["workers"] = workers

    yeetr.run(main, argv=["-w", "8"])
    assert captured == {"workers": 8}

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=[])


def test_dataclass_parameter_builds_instance_from_options() -> None:
    @dataclass(slots=True)
    class Args:
        name: Annotated[str, Opt(alias="n", help="Name")] = "default"
        tolerance: Annotated[float, Opt(aliases=("t", "tolerance"), help="Tolerance")] = 0.5

    captured: dict[str, object] = {}

    def main(args: Args) -> None:
        captured["args"] = args

    yeetr.run(main, argv=["-n", "name", "-t", "0.75"])
    assert captured == {"args": Args(name="name", tolerance=0.75)}

    yeetr.run(main, argv=["--tolerance", "0.25"])
    assert captured == {"args": Args(name="default", tolerance=0.25)}


def test_dataclass_parameter_supports_positional_arg_fields() -> None:
    @dataclass(slots=True)
    class Args:
        path: Annotated[Path, Arg(help="Path")]
        workers: Annotated[int, Opt(alias="w")] = 4

    captured: dict[str, object] = {}

    def main(args: Args) -> None:
        captured["args"] = args

    yeetr.run(main, argv=["path", "-w", "8"])
    assert captured == {"args": Args(path=Path("path"), workers=8)}


def test_dataclass_parameter_uses_unmarked_fields_as_options() -> None:
    @dataclass(slots=True)
    class Args:
        count: int

    captured: dict[str, object] = {}

    def main(args: Args) -> None:
        captured["args"] = args

    yeetr.run(main, argv=["--count", "5"])
    assert captured == {"args": Args(count=5)}


def test_dataclass_keyword_only_parameter_rejected() -> None:
    @dataclass(slots=True)
    class Args:
        count: int

    def main(*, args: Args) -> None:
        del args

    with pytest.raises(YeetrError, match="must not be keyword-only"):
        yeetr.run(main, argv=[])


def test_dataclass_parameter_with_no_init_fields_rejected() -> None:
    @dataclass(slots=True)
    class Args:
        count: int = field(init=False)

    def main(args: Args) -> None:
        del args

    with pytest.raises(YeetrError, match="no init fields"):
        yeetr.run(main, argv=[])


def test_named_tuple_parameter_builds_instance_from_options() -> None:
    class Args(NamedTuple):
        name: Annotated[str, Opt(alias="n", help="Name")] = "default"
        tolerance: Annotated[float, Opt(aliases=("t", "tol"), help="Tolerance")] = 0.5

    captured: dict[str, object] = {}

    def main(args: Args) -> None:
        captured["args"] = args

    yeetr.run(main, argv=["-n", "name", "-t", "0.75"])
    assert captured == {"args": Args(name="name", tolerance=0.75)}

    yeetr.run(main, argv=["--tol", "0.25"])
    assert captured == {"args": Args(name="default", tolerance=0.25)}


def test_named_tuple_parameter_supports_positional_arg_fields() -> None:
    class Args(NamedTuple):
        path: Annotated[Path, Arg(help="Path")]
        workers: Annotated[int, Opt(alias="w")] = 4

    captured: dict[str, object] = {}

    def main(args: Args) -> None:
        captured["args"] = args

    yeetr.run(main, argv=["path", "-w", "8"])
    assert captured == {"args": Args(path=Path("path"), workers=8)}


def test_named_tuple_keyword_only_parameter_rejected() -> None:
    class Args(NamedTuple):
        value: int

    def main(*, args: Args) -> None:
        del args

    with pytest.raises(YeetrError, match="must not be keyword-only"):
        yeetr.run(main, argv=[])


def test_arg_on_positional() -> None:
    captured: dict[str, object] = {}

    def main(path: Annotated[Path, Arg(help="Input file")]) -> None:
        captured["path"] = path

    yeetr.run(main, argv=["x.txt"])
    assert captured == {"path": Path("x.txt")}


def test_opt_on_positional_raises() -> None:
    def main(path: Annotated[Path, Opt(alias="-p")]) -> None:
        del path

    with pytest.raises(YeetrError, match="Arg"):
        yeetr.run(main, argv=["x.txt"])


def test_arg_on_keyword_only_raises() -> None:
    def main(*, workers: Annotated[int, Arg(help="nope")] = 4) -> None:
        del workers

    with pytest.raises(YeetrError, match="Opt"):
        yeetr.run(main, argv=[])


def test_missing_annotation_errors() -> None:
    def main(
        thing,  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
    ) -> None:
        del thing

    with pytest.raises(YeetrError):
        yeetr.run(main, argv=["5"])  # pyright: ignore[reportUnknownArgumentType]


def test_returns_function_result() -> None:
    def main(thing: int) -> int:
        return thing * 2

    assert yeetr.run(main, argv=["5"]) == 10


type _Workers = Annotated[int, Opt(alias="-w", help="Worker count")]
type _Count = int
type _MaybeInt = int | None
type _AliasChain = _Workers
type _BoolAlias = bool
type _ModelCode = Literal["nl2", "ch4"]


def test_type_alias_annotated_param() -> None:
    captured: dict[str, object] = {}

    def main(*, workers: _Workers = 4) -> None:
        captured["workers"] = workers

    yeetr.run(main, argv=["-w", "8"])
    assert captured == {"workers": 8}

    yeetr.run(main, argv=["--workers", "3"])
    assert captured == {"workers": 3}

    yeetr.run(main, argv=[])
    assert captured == {"workers": 4}


def test_type_alias_bare_type() -> None:
    captured: dict[str, object] = {}

    def main(count: _Count) -> None:
        captured["count"] = count

    yeetr.run(main, argv=["7"])
    assert captured == {"count": 7}


def test_type_alias_in_optional() -> None:
    captured: dict[str, object] = {}

    def main(*, value: _MaybeInt = None) -> None:
        captured["value"] = value

    yeetr.run(main, argv=["--value", "5"])
    assert captured == {"value": 5}

    yeetr.run(main, argv=[])
    assert captured == {"value": None}


def test_type_alias_transitive() -> None:
    captured: dict[str, object] = {}

    def main(*, workers: _AliasChain = 4) -> None:
        captured["workers"] = workers

    yeetr.run(main, argv=["-w", "8"])
    assert captured == {"workers": 8}


def test_type_alias_help_renders_inner_type() -> None:
    from io import StringIO

    from rich.console import Console

    from yeetr._runner import _build_parser  # pyright: ignore[reportPrivateUsage]

    def main(*, workers: _Workers = 4) -> None:
        del workers

    parser, _, _ = _build_parser(main, prog="app")
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    parser.print_help(file=console.file)
    output = buf.getvalue()
    assert "int" in output
    assert "Workers" not in output
    assert "-w" in output
    assert "Worker count" in output


def test_type_alias_outer_opt_overrides() -> None:
    captured: dict[str, object] = {}

    def main(
        *,
        workers: Annotated[_Workers, Opt(alias="-x", help="Override")] = 4,
    ) -> None:
        captured["workers"] = workers

    yeetr.run(main, argv=["-x", "9"])
    assert captured == {"workers": 9}

    yeetr.run(main, argv=["--workers", "2"])
    assert captured == {"workers": 2}


def test_type_alias_in_list() -> None:
    captured: dict[str, object] = {}

    def main(*, models: list[_ModelCode] | None = None) -> None:
        captured["models"] = models

    yeetr.run(main, argv=["--models", "nl2", "--models", "ch4"])
    assert captured == {"models": ["nl2", "ch4"]}


def test_unsupported_type_errors_when_building_parser() -> None:
    def main(*, value: dict[str, str]) -> None:
        del value

    with pytest.raises(YeetrError, match=r"Parameter 'value' has unsupported type 'dict'\."):
        yeetr.run(main, argv=[])


def test_metadata_on_list_item_errors_when_building_parser() -> None:
    def main(*, values: list[Annotated[str, Opt(alias="v")]]) -> None:
        del values

    with pytest.raises(YeetrError, match="collection item"):
        yeetr.run(main, argv=[])


def test_var_positional_zero_or_more() -> None:
    captured: dict[str, object] = {}

    def main(dst: Path, *sources: Path) -> None:
        captured["dst"] = dst
        captured["sources"] = sources

    yeetr.run(main, argv=["dst", "a", "b", "c"])
    assert captured == {"dst": Path("dst"), "sources": (Path("a"), Path("b"), Path("c"))}


def test_var_positional_empty_is_tuple() -> None:
    captured: dict[str, object] = {}

    def main(dst: Path, *sources: Path) -> None:
        captured["dst"] = dst
        captured["sources"] = sources

    yeetr.run(main, argv=["dst"])
    assert captured == {"dst": Path("dst"), "sources": ()}


def test_var_positional_with_arg_metadata() -> None:
    captured: dict[str, object] = {}

    def main(*sources: Annotated[Path, Arg(help="Source paths", metavar="SRC")]) -> None:
        captured["sources"] = sources

    yeetr.run(main, argv=["a", "b"])
    assert captured == {"sources": (Path("a"), Path("b"))}


def test_var_positional_min_one_required() -> None:
    def main(*sources: Annotated[Path, Arg(min=1)]) -> None:
        del sources

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=[])


def test_var_positional_min_one_accepts_values() -> None:
    captured: dict[str, object] = {}

    def main(*sources: Annotated[Path, Arg(min=1)]) -> None:
        captured["sources"] = sources

    yeetr.run(main, argv=["a"])
    assert captured == {"sources": (Path("a"),)}


def test_var_positional_with_keyword_only() -> None:
    captured: dict[str, object] = {}

    def main(*sources: str, loud: bool = False) -> None:
        captured["sources"] = sources
        captured["loud"] = loud

    yeetr.run(main, argv=["a", "b", "--loud"])
    assert captured == {"sources": ("a", "b"), "loud": True}


def test_var_positional_list_annotation_rejected() -> None:
    def main(*sources: list[Path]) -> None:
        del sources

    with pytest.raises(YeetrError, match="list"):
        yeetr.run(main, argv=["a"])


def test_var_positional_opt_metadata_rejected() -> None:
    def main(*sources: Annotated[Path, Opt(alias="-s")]) -> None:
        del sources

    with pytest.raises(YeetrError, match="Arg"):
        yeetr.run(main, argv=["a"])


def test_var_keyword_still_rejected() -> None:
    def main(**opts: str) -> None:
        del opts

    with pytest.raises(YeetrError):
        yeetr.run(main, argv=[])


def test_specific_signature_from_spec() -> None:
    captured: dict[str, object] = {}

    def main(thing: int, *, n: float = 0.1) -> None:
        captured["thing"] = thing
        captured["n"] = n

    yeetr.run(main, argv=["5", "-n", "0.2"])
    assert captured == {"thing": 5, "n": 0.2}


def _clear_root_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)


def test_logging_setup_on_by_default_no_log_level_param() -> None:
    def main(thing: int) -> None:
        del thing

    _clear_root_handlers()
    yeetr.run(main, argv=["5"])
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], RichHandler)
    assert logging.getLogger().level == logging.INFO


def test_logging_setup_honours_log_level_param() -> None:
    def main(*, log_level: Literal["debug", "info", "warning", "error"] = "info") -> None:
        del log_level

    _clear_root_handlers()
    yeetr.run(main, argv=["--log-level", "debug"])
    assert logging.getLogger().level == logging.DEBUG


def test_logging_setup_disabled_by_flag() -> None:
    def main(thing: int) -> None:
        del thing

    _clear_root_handlers()
    before = list(logging.getLogger().handlers)
    yeetr.run(main, argv=["5"], should_setup_logging=False)
    after = list(logging.getLogger().handlers)
    assert before == after


def test_logging_setup_is_idempotent() -> None:
    def main(thing: int) -> None:
        del thing

    _clear_root_handlers()
    yeetr.run(main, argv=["5"])
    handler_count_after_first = len(logging.getLogger().handlers)
    yeetr.run(main, argv=["6"])
    assert len(logging.getLogger().handlers) == handler_count_after_first


def test_envvar_fallback_used_when_flag_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, workers: Annotated[int, Opt(envvar="WORKERS")] = 4) -> None:
        captured["workers"] = workers

    monkeypatch.setenv("WORKERS", "8")
    yeetr.run(main, argv=[])
    assert captured == {"workers": 8}


def test_envvar_cli_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, workers: Annotated[int, Opt(envvar="WORKERS")] = 4) -> None:
        captured["workers"] = workers

    monkeypatch.setenv("WORKERS", "8")
    yeetr.run(main, argv=["--workers", "16"])
    assert captured == {"workers": 16}


def test_envvar_default_used_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, workers: Annotated[int, Opt(envvar="WORKERS")] = 4) -> None:
        captured["workers"] = workers

    monkeypatch.delenv("WORKERS", raising=False)
    yeetr.run(main, argv=[])
    assert captured == {"workers": 4}


def test_envvar_bool_accepts_truthy_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, loud: Annotated[bool, Opt(envvar="LOUD")] = False) -> None:
        captured["loud"] = loud

    for value in ("1", "true", "yes", "TRUE"):
        monkeypatch.setenv("LOUD", value)
        yeetr.run(main, argv=[])
        assert captured == {"loud": True}, value


def test_envvar_bool_accepts_falsy_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, loud: Annotated[bool, Opt(envvar="LOUD")] = True) -> None:
        captured["loud"] = loud

    for value in ("0", "false", "no", "FALSE"):
        monkeypatch.setenv("LOUD", value)
        yeetr.run(main, argv=[])
        assert captured == {"loud": False}, value


def test_envvar_literal_validates_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    def main(*, format: Annotated[Literal["json", "csv"], Opt(envvar="FMT")] = "json") -> None:
        del format

    monkeypatch.setenv("FMT", "xml")
    with pytest.raises(SystemExit):
        yeetr.run(main, argv=[])


def test_envvar_list_splits_on_pathsep(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    captured: dict[str, object] = {}

    def main(*, tag: Annotated[list[str] | None, Opt(envvar="TAGS")] = None) -> None:
        if tag is None:
            tag = []
        captured["tag"] = tag

    monkeypatch.setenv("TAGS", f"a{os.pathsep}b{os.pathsep}c")
    yeetr.run(main, argv=[])
    assert captured == {"tag": ["a", "b", "c"]}


def test_envvar_required_without_default_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def main(*, workers: Annotated[int, Opt(envvar="WORKERS")]) -> None:
        del workers

    monkeypatch.delenv("WORKERS", raising=False)
    with pytest.raises(YeetrError):
        yeetr.run(main, argv=[])


def test_envvar_required_satisfied_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, workers: Annotated[int, Opt(envvar="WORKERS")]) -> None:
        captured["workers"] = workers

    monkeypatch.setenv("WORKERS", "12")
    yeetr.run(main, argv=[])
    assert captured == {"workers": 12}


def test_envvar_shown_in_help() -> None:
    from io import StringIO

    from rich.console import Console

    from yeetr._runner import _build_parser  # pyright: ignore[reportPrivateUsage]

    def main(*, workers: Annotated[int, Opt(envvar="WORKERS")] = 4) -> None:
        del workers

    parser, _, _ = _build_parser(main, prog="app")
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    parser.print_help(file=console.file)
    output = buf.getvalue()
    assert "WORKERS" in output


def test_hidden_option_parses() -> None:
    captured: dict[str, object] = {}

    def main(*, debug: Annotated[bool, Opt(hidden=True)] = False) -> None:
        captured["debug"] = debug

    yeetr.run(main, argv=["--debug"])
    assert captured == {"debug": True}


def test_hidden_option_absent_from_help() -> None:
    from io import StringIO

    from rich.console import Console

    from yeetr._runner import _build_parser  # pyright: ignore[reportPrivateUsage]

    def main(*, debug: Annotated[bool, Opt(hidden=True)] = False, workers: int = 4) -> None:
        del debug, workers

    parser, _, _ = _build_parser(main, prog="app")
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    parser.print_help(file=console.file)
    output = buf.getvalue()
    assert "--debug" not in output
    assert "--workers" in output


def test_path_exists_rejects_missing(tmp_path: Path) -> None:
    def main(path: Annotated[Path, Arg(exists=True)]) -> None:
        del path

    missing = tmp_path / "missing"
    with pytest.raises(SystemExit):
        yeetr.run(main, argv=[str(missing)])


def test_path_exists_accepts_existing(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def main(path: Annotated[Path, Arg(exists=True)]) -> None:
        captured["path"] = path

    existing = tmp_path / "file"
    existing.write_text("x")
    yeetr.run(main, argv=[str(existing)])
    assert captured == {"path": existing}


def test_path_file_okay_false_rejects_file(tmp_path: Path) -> None:
    def main(path: Annotated[Path, Arg(file_okay=False)]) -> None:
        del path

    file = tmp_path / "file"
    file.write_text("x")
    with pytest.raises(SystemExit):
        yeetr.run(main, argv=[str(file)])


def test_path_dir_okay_false_rejects_dir(tmp_path: Path) -> None:
    def main(path: Annotated[Path, Arg(dir_okay=False)]) -> None:
        del path

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=[str(tmp_path)])


def test_path_readable_rejects_unreadable(tmp_path: Path) -> None:
    import os

    def main(path: Annotated[Path, Arg(readable=True)]) -> None:
        del path

    file = tmp_path / "file"
    file.write_text("x")
    file.chmod(0o000)
    try:
        if os.access(file, os.R_OK):
            pytest.skip("running as root; cannot test unreadable file")
        with pytest.raises(SystemExit):
            yeetr.run(main, argv=[str(file)])
    finally:
        file.chmod(0o644)


def test_path_writable_rejects_unwritable(tmp_path: Path) -> None:
    import os

    def main(path: Annotated[Path, Arg(writable=True)]) -> None:
        del path

    file = tmp_path / "file"
    file.write_text("x")
    file.chmod(0o444)
    try:
        if os.access(file, os.W_OK):
            pytest.skip("running as root; cannot test unwritable file")
        with pytest.raises(SystemExit):
            yeetr.run(main, argv=[str(file)])
    finally:
        file.chmod(0o644)


def test_path_checks_on_non_path_raises() -> None:
    def main(value: Annotated[int, Arg(exists=True)]) -> None:
        del value

    with pytest.raises(YeetrError, match="Path"):
        yeetr.run(main, argv=["5"])


def test_path_checks_on_list_path(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def main(*, paths: Annotated[list[Path] | None, Opt(exists=True)] = None) -> None:
        if paths is None:
            paths = []
        captured["paths"] = paths

    file = tmp_path / "file"
    file.write_text("x")
    yeetr.run(main, argv=["--paths", str(file)])
    assert captured == {"paths": [file]}


def test_path_checks_on_var_positional(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def main(*paths: Annotated[Path, Arg(exists=True)]) -> None:
        captured["paths"] = paths

    file = tmp_path / "file"
    file.write_text("x")
    yeetr.run(main, argv=[str(file)])
    assert captured == {"paths": (file,)}


def test_path_checks_on_var_positional_rejects_missing(tmp_path: Path) -> None:
    def main(*paths: Annotated[Path, Arg(exists=True)]) -> None:
        del paths

    missing = tmp_path / "missing"
    with pytest.raises(SystemExit):
        yeetr.run(main, argv=[str(missing)])


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _double(value: int) -> int:
    return value * 2


def _reject(value: str) -> str:
    raise ValueError(value)


def _untyped(
    value,  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
) -> str:
    del value
    return ""


def _no_params() -> str:
    return ""


def _two_params(first: str, second: str) -> str:
    return first + second


def _split_words(value: str) -> list[str]:
    return value.split()


def test_parser_opt_coerces_input_then_calls_parser(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def main(*, data: Annotated[bytes, Opt(parser=_read_bytes)]) -> None:
        captured["data"] = data

    file = tmp_path / "file"
    file.write_bytes(b"content")
    yeetr.run(main, argv=["--data", str(file)])
    assert captured == {"data": b"content"}


def test_parser_arg_coerces_input_then_calls_parser() -> None:
    captured: dict[str, object] = {}

    def main(value: Annotated[int, Arg(parser=_double)]) -> None:
        captured["value"] = value

    yeetr.run(main, argv=["5"])
    assert captured == {"value": 10}


def test_parser_with_exists_rejects_missing_before_parser(tmp_path: Path) -> None:
    def main(*, data: Annotated[bytes, Opt(parser=_read_bytes, exists=True)]) -> None:
        del data

    missing = tmp_path / "missing"
    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["--data", str(missing)])


def test_parser_with_exists_accepts_existing(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def main(*, data: Annotated[bytes, Opt(parser=_read_bytes, exists=True)]) -> None:
        captured["data"] = data

    file = tmp_path / "file"
    file.write_bytes(b"content")
    yeetr.run(main, argv=["--data", str(file)])
    assert captured == {"data": b"content"}


def test_parser_with_path_checks_on_non_path_input_raises() -> None:
    def main(*, value: Annotated[int, Opt(parser=_double, exists=True)]) -> None:
        del value

    with pytest.raises(YeetrError, match="Path"):
        yeetr.run(main, argv=["--value", "5"])


def test_parser_error_is_wrapped(capsys: pytest.CaptureFixture[str]) -> None:
    def main(*, value: Annotated[str, Opt(parser=_reject)]) -> None:
        del value

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["--value", "x"])
    err = capsys.readouterr().err
    assert "invalid value" in err


def test_parser_arg_error_is_wrapped() -> None:
    def main(value: Annotated[str, Arg(parser=_reject)]) -> None:
        del value

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["x"])


def test_parser_zero_params_rejected() -> None:
    def main(*, value: Annotated[str, Opt(parser=_no_params)]) -> None:
        del value

    with pytest.raises(YeetrError, match="must take exactly one argument"):
        yeetr.run(main, argv=["--value", "x"])


def test_parser_two_params_rejected() -> None:
    def main(value: Annotated[str, Arg(parser=_two_params)]) -> None:
        del value

    with pytest.raises(YeetrError, match="must take exactly one argument"):
        yeetr.run(main, argv=["x"])


def test_parser_untyped_param_rejected() -> None:
    opt = Opt(parser=_untyped)  # pyright: ignore[reportUnknownArgumentType]

    def main(*, value: Annotated[str, opt]) -> None:
        del value

    with pytest.raises(YeetrError, match="untyped parameter"):
        yeetr.run(main, argv=["--value", "x"])


def test_parser_help_shows_input_type(capsys: pytest.CaptureFixture[str]) -> None:
    def main(*, data: Annotated[bytes, Opt(parser=_read_bytes)]) -> None:
        del data

    with pytest.raises(SystemExit):
        yeetr.run(main, argv=["--help"])
    output = capsys.readouterr().out
    assert "Path" in output
    assert "bytes" not in output


def test_parser_on_list_rejected() -> None:
    def main(*, words: Annotated[list[str], Opt(parser=_split_words)]) -> None:
        del words

    with pytest.raises(YeetrError, match="list/tuple"):
        yeetr.run(main, argv=["--words", "a b"])


def test_parser_on_tuple_rejected() -> None:
    def main(pair: Annotated[tuple[int, int], Arg(parser=_double)]) -> None:
        del pair

    with pytest.raises(YeetrError, match="list/tuple"):
        yeetr.run(main, argv=["1", "2"])


def test_parser_on_var_positional_rejected() -> None:
    def main(*values: Annotated[int, Arg(parser=_double)]) -> None:
        del values

    with pytest.raises(YeetrError, match="variadic"):
        yeetr.run(main, argv=["5"])


def test_parser_optional_annotation(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def main(*, data: Annotated[bytes | None, Opt(parser=_read_bytes)] = None) -> None:
        captured["data"] = data

    yeetr.run(main, argv=[])
    assert captured == {"data": None}

    file = tmp_path / "file"
    file.write_bytes(b"content")
    yeetr.run(main, argv=["--data", str(file)])
    assert captured == {"data": b"content"}


def test_parser_envvar(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def main(*, value: Annotated[int, Opt(parser=_double, envvar="VALUE")] = 0) -> None:
        captured["value"] = value

    monkeypatch.setenv("VALUE", "3")
    yeetr.run(main, argv=[])
    assert captured == {"value": 6}


def _keyword_only_parser(*, value: int) -> int:
    return value


def _bool_input_parser(value: bool) -> str:  # noqa: FBT001
    return str(value)


def _list_input_parser(value: list[str]) -> str:
    return ",".join(value)


def _quoted_annotation_parser(value: "int") -> int:
    return value * 2


@dataclass(slots=True)
class _MultiplierParser:
    factor: int

    def __call__(self, value: "int") -> int:
        return value * self.factor


def test_parser_without_introspectable_signature_rejected() -> None:
    def main(*, value: Annotated[str, Opt(parser=min)]) -> None:
        del value

    with pytest.raises(YeetrError, match="must take exactly one argument"):
        yeetr.run(main, argv=["--value", "x"])


def test_parser_keyword_only_param_rejected() -> None:
    def main(*, value: Annotated[int, Opt(parser=_keyword_only_parser)]) -> None:
        del value

    with pytest.raises(YeetrError, match="must take exactly one argument"):
        yeetr.run(main, argv=["--value", "1"])


def test_parser_bool_input_type_rejected() -> None:
    def main(*, value: Annotated[str, Opt(parser=_bool_input_parser)]) -> None:
        del value

    with pytest.raises(YeetrError, match="not supported"):
        yeetr.run(main, argv=["--value", "true"])


def test_parser_list_input_type_rejected() -> None:
    def main(*, value: Annotated[str, Opt(parser=_list_input_parser)]) -> None:
        del value

    with pytest.raises(YeetrError, match="not supported"):
        yeetr.run(main, argv=["--value", "x"])


def test_parser_string_annotation_resolved() -> None:
    captured: dict[str, object] = {}

    def main(*, value: Annotated[int, Opt(parser=_quoted_annotation_parser)]) -> None:
        captured["value"] = value

    yeetr.run(main, argv=["--value", "3"])
    assert captured == {"value": 6}


def test_parser_callable_object() -> None:
    captured: dict[str, object] = {}

    def main(*, value: Annotated[int, Opt(parser=_MultiplierParser(3))]) -> None:
        captured["value"] = value

    yeetr.run(main, argv=["--value", "2"])
    assert captured == {"value": 6}


def _write_demo(tmp_path: Path) -> Path:
    file = tmp_path / "demo.py"
    file.write_text(
        "def main(thing: int, *, n: float = 0.1) -> None:\n"
        "    print(f'main thing={thing} n={n}')\n"
        "\n"
        "def greet(name: str, *, loud: bool = False) -> None:\n"
        "    msg = f'hello {name}'\n"
        "    print(msg.upper() if loud else msg)\n",
    )
    return file


def test_yeet_cli_defaults_to_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_demo(tmp_path)
    yeet_main([str(file), "5", "-n", "0.2"])
    out = capsys.readouterr().out
    assert "main thing=5 n=0.2" in out


def test_yeet_cli_explicit_func(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_demo(tmp_path)
    yeet_main([str(file), "greet", "world", "--loud"])
    out = capsys.readouterr().out
    assert "HELLO WORLD" in out


def test_yeet_cli_missing_python_file_scaffolds(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "nope.py"
    yeet_main([str(file)])

    out = capsys.readouterr().out
    assert f"created {file.resolve()}" in out
    assert file.read_text() == (
        "#!yeet\n"
        "import logging\n"
        "\n"
        'logger = logging.getLogger("Main")\n'
        "\n"
        "\n"
        "def main() -> None:\n"
        '    logger.info("Hello from yeetr")\n'
    )
    assert file.stat().st_mode & stat.S_IXUSR == stat.S_IXUSR
    assert file.stat().st_mode & stat.S_IXGRP == 0
    assert file.stat().st_mode & stat.S_IXOTH == 0


def test_yeet_cli_missing_non_python_file_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    with pytest.raises(SystemExit) as exc:
        yeet_main([str(tmp_path / "nope.txt")])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "file not found" in err


def test_yeet_cli_missing_parent_directory_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "missing" / "demo.py"
    with pytest.raises(SystemExit) as exc:
        yeet_main([str(file)])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "parent directory not found" in err


def test_yeet_cli_no_args_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    from yeetr._cli import main as yeet_main

    with pytest.raises(SystemExit) as exc:
        yeet_main([])
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "yeet FILE" in out


def test_yeet_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    from yeetr._cli import main as yeet_main

    with pytest.raises(SystemExit) as exc:
        yeet_main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "yeet FILE" in out


def test_yeet_cli_forwards_help_to_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_demo(tmp_path)
    with pytest.raises(SystemExit):
        yeet_main([str(file), "--help"])
    out = capsys.readouterr().out
    assert "THING" in out
    assert "-n" in out


def test_yeet_cli_loads_imports_from_target_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    package_dir = tmp_path / "project"
    package_dir.mkdir()
    (package_dir / "scraper.py").write_text("VALUE = 'loaded'\n")
    file = package_dir / "demo.py"
    file.write_text(
        "import scraper\n\ndef main() -> None:\n    print(scraper.VALUE)\n",
    )
    monkeypatch.chdir(tmp_path)
    yeet_main([str(file)])
    out = capsys.readouterr().out
    assert "loaded" in out


def test_yeet_cli_errors_when_target_function_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text("VALUE = 1\n")
    with pytest.raises(SystemExit) as exc:
        yeet_main([str(file)])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "has no public function 'main' to run" in err


def test_yeet_cli_errors_when_named_attribute_is_not_callable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text("thing = 1\n")
    with pytest.raises(SystemExit) as exc:
        yeet_main([str(file), "thing"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "has no public function 'main' to run" in err


def test_yeet_cli_keeps_non_callable_candidate_as_argument(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text(
        "thing = 1\n\ndef main(name: str) -> None:\n    print(name)\n",
    )
    yeet_main([str(file), "thing"])
    out = capsys.readouterr().out
    assert "thing" in out


def _write_thing_and_str_main(tmp_path: Path) -> Path:
    file = tmp_path / "demo.py"
    file.write_text(
        "def thing() -> None:\n"
        "    print('ran thing')\n"
        "\n"
        "def main(arg: str) -> None:\n"
        "    print(f'main got {arg!r}')\n",
    )
    return file


def test_yeet_cli_ambiguous_function_and_str_main_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_thing_and_str_main(tmp_path)
    with pytest.raises(SystemExit) as exc:
        yeet_main([str(file), "thing"])
    assert exc.value.code == 2
    assert "ambiguous" in capsys.readouterr().err


def test_yeet_cli_explicit_main_escapes_ambiguity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_thing_and_str_main(tmp_path)
    yeet_main([str(file), "main", "thing"])
    assert "main got 'thing'" in capsys.readouterr().out


def test_yeet_cli_imported_callable_is_not_dispatched(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text(
        "from logging import getLogger\n"
        "\n"
        "def main(arg: str) -> None:\n"
        "    print(f'main got {arg!r}')\n",
    )
    # `getLogger` is imported, not defined here -> treated as main's value, not run.
    yeet_main([str(file), "getLogger"])
    assert "main got 'getLogger'" in capsys.readouterr().out


def test_yeet_cli_private_function_is_not_dispatched(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text(
        "def _secret() -> None:\n"
        "    print('secret')\n"
        "\n"
        "def main(arg: str) -> None:\n"
        "    print(f'main got {arg!r}')\n",
    )
    yeet_main([str(file), "_secret"])
    assert "main got '_secret'" in capsys.readouterr().out


def test_yeet_cli_function_before_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_thing_and_str_main(tmp_path)
    # `yeet FUNC FILE` — the form a `#!yeet thing` shebang produces.
    yeet_main(["thing", str(file)])
    assert "ran thing" in capsys.readouterr().out


def test_yeet_cli_file_colon_function(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_thing_and_str_main(tmp_path)
    yeet_main([f"{file}:thing"])
    assert "ran thing" in capsys.readouterr().out


def _write_multiword_func(tmp_path: Path) -> Path:
    file = tmp_path / "demo.py"
    file.write_text(
        "def main() -> None:\n"
        "    print('main called')\n"
        "\n"
        "def add_item_to_index(*, item_id: str) -> None:\n"
        "    print(f'added {item_id}')\n",
    )
    return file


def test_yeet_cli_hyphenated_func_after_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_multiword_func(tmp_path)
    yeet_main([str(file), "add-item-to-index", "--item-id", "x"])
    assert "added x" in capsys.readouterr().out


def test_yeet_cli_hyphenated_func_before_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_multiword_func(tmp_path)
    # `yeet FUNC FILE` — the form a `#!yeet add-item-to-index` shebang produces.
    yeet_main(["add-item-to-index", str(file), "--item-id", "x"])
    assert "added x" in capsys.readouterr().out


def test_yeet_cli_hyphenated_file_colon_func(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = _write_multiword_func(tmp_path)
    yeet_main([f"{file}:add-item-to-index", "--item-id", "x"])
    assert "added x" in capsys.readouterr().out


def test_yeet_cli_non_function_main_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text("class main:\n    pass\n")
    with pytest.raises(SystemExit) as exc:
        yeet_main([str(file)])
    assert exc.value.code == 2
    assert "has no public function 'main' to run" in capsys.readouterr().err


def test_yeet_cli_optional_str_main_is_ambiguous(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text(
        "def thing() -> None:\n"
        "    print('ran thing')\n"
        "\n"
        "def main(arg: str | None = None) -> None:\n"
        "    print(f'main got {arg!r}')\n",
    )
    with pytest.raises(SystemExit) as exc:
        yeet_main([str(file), "thing"])
    assert exc.value.code == 2
    assert "ambiguous" in capsys.readouterr().err


def test_yeet_cli_dispatches_function_when_main_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text("def thing() -> None:\n    print('ran thing')\n")
    yeet_main([str(file), "thing"])
    assert "ran thing" in capsys.readouterr().out


def test_yeet_cli_unresolvable_main_hints_not_ambiguous(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text(
        "def thing() -> None:\n"
        "    print('ran thing')\n"
        "\n"
        "def main(arg: 'Nope') -> None:\n"
        "    del arg\n",
    )
    yeet_main([str(file), "thing"])
    assert "ran thing" in capsys.readouterr().out


def test_yeet_cli_keyword_only_main_not_ambiguous(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text(
        "def thing() -> None:\n"
        "    print('ran thing')\n"
        "\n"
        "def main(*, n: int = 1) -> None:\n"
        "    print(f'main n={n}')\n",
    )
    yeet_main([str(file), "thing"])
    assert "ran thing" in capsys.readouterr().out


def test_yeet_cli_var_keyword_main_not_ambiguous(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text(
        "def thing() -> None:\n"
        "    print('ran thing')\n"
        "\n"
        "def main(**kwargs: str) -> None:\n"
        "    del kwargs\n",
    )
    yeet_main([str(file), "thing"])
    assert "ran thing" in capsys.readouterr().out


def test_yeet_cli_zero_param_main_not_ambiguous(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from yeetr._cli import main as yeet_main

    file = tmp_path / "demo.py"
    file.write_text(
        "def thing() -> None:\n"
        "    print('ran thing')\n"
        "\n"
        "def main() -> None:\n"
        "    print('ran main')\n",
    )
    yeet_main([str(file), "thing"])
    assert "ran thing" in capsys.readouterr().out
