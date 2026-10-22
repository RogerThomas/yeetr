<p align="center">
  <a href="https://rogerthomas.github.io/yeetr/">
    <img src="https://raw.githubusercontent.com/RogerThomas/yeetr/main/docs/assets/yeetr.png" alt="yeetr" width="500">
  </a>
</p>
<p align="center">
  <em>yeetr, build tiny CLIs. Easy to code. Based on Python type hints.</em>
</p>
<p align="center">
  <a href="https://github.com/RogerThomas/yeetr/actions/workflows/main.yml?query=branch%3Amain">
    <img src="https://img.shields.io/github/actions/workflow/status/RogerThomas/yeetr/main.yml?branch=main" alt="Build">
  </a>
  <a href="https://github.com/RogerThomas/yeetr/releases">
    <img src="https://img.shields.io/github/v/release/RogerThomas/yeetr" alt="Release">
  </a>
  <a href="https://codecov.io/gh/RogerThomas/yeetr">
    <img src="https://codecov.io/gh/RogerThomas/yeetr/graph/badge.svg" alt="Coverage">
  </a>
  <a href="https://pypi.org/project/yeetr">
    <img src="https://img.shields.io/pypi/v/yeetr?color=%2334D058&label=pypi%20package" alt="Package version">
  </a>
  <a href="https://pypi.org/project/yeetr">
    <img src="https://img.shields.io/pypi/pyversions/yeetr" alt="Supported Python versions">
  </a>
  <a href="https://github.com/RogerThomas/yeetr/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/RogerThomas/yeetr" alt="License">
  </a>
</p>

# yeetr

A tiny, typed, signature-driven CLI runner. Supports Python 3.13, 3.14, and 3.15.

> No decorators.
> No command classes.
> No ceremony.
> Just yeet the function.

Write a plain function, run it from the command line — `yeetr` turns the
signature into args and options for you:

```python
# app.py
def main(thing: int, *, n: float = 0.1) -> None:
    print(thing, n)
```

```bash
yeet app.py 5 -n 0.2
```

No `if __name__ == "__main__"` block, no `yeetr.run(...)` call, no
decorators. Parameters **before** the bare `*` become positional args,
parameters **after** it become `--options`.

## Install

```bash
uv add yeetr
```

## Highlights

- **Zero boilerplate** — `yeet app.py` finds and runs `main` — or any
  public function you name — and scaffolds the file if it doesn't exist yet.
- **Executable shebangs** — `#!yeet` makes a script runnable on its own;
  `#!yeet FUNC` picks the function to run.
- **Fully typed** — `str`, `int`, `float`, `bool`, `Path`, `datetime`,
  `date`, `time`, `UUID`, `Decimal`, `Literal`, `Enum`, `T | None`,
  `list[T]`, tuples, and structured `dataclass`/`NamedTuple` args, all
  Pyright-strict clean.
- **Async-native** — `async def main` just works, with automatic
  [uvloop](https://github.com/MagicStack/uvloop) if it's installed.
- **Rich output** — formatted logging and help/error tables out of the box.

<p align="center">
  <img class="no-radius" src="https://raw.githubusercontent.com/RogerThomas/yeetr/main/docs/assets/yeetr-help.png" alt="yeetr help output" width="900">
</p>

## Docs

The full guide — parameter metadata, env var fallback, path validators,
runtime behavior, a [yeetr vs. typer](https://rogerthomas.github.io/yeetr/comparison/)
comparison, and the API reference — lives at
**[rogerthomas.github.io/yeetr](https://rogerthomas.github.io/yeetr/)**.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up a dev environment,
run the test suite, and submit changes.

## License

[MIT](LICENSE)
