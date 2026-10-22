<div class="hero">
  <a href="https://github.com/RogerThomas/yeetr">
    <img class="hero-logo" src="assets/yeetr-light.png" alt="yeetr">
  </a>

  <p><em>yeetr, build tiny CLIs. Easy to code. Based on Python type hints.</em></p>

  <p class="hero-badges">
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
</div>

# yeetr

A tiny, typed, signature-driven CLI runner.

PyPI distribution: `yeetr`
Python import package: `yeetr`
CLI command: `yeet`

> No decorators.
> No command classes.
> No ceremony.
> Just yeet the function.

## Install

Requires Python 3.13, 3.14, or 3.15.

```bash
uv add yeetr
```

## 30-second tour

Write a plain function:

```python
# app.py
def main(thing: int, *, n: float = 0.1) -> None:
    print(thing, n)
```

Run it — no `if __name__ == "__main__"`, no `yeetr.run(...)` call:

```bash
yeet app.py 5 -n 0.2
```

Parameters **before** the bare `*` become positional CLI args. Parameters
**after** it become `--options`. That's the whole mapping.

## Where to go next

- [Getting Started](guide/getting-started.md) — installation, the `yeet`
  script and how it picks the function to run, the explicit `yeetr.run(main)`
  form, and executable shebangs.
- [Async Support](guide/async.md) — `async def main`, handled natively.
- [Parameter Types](guide/parameter-types.md) — every type yeetr understands,
  from `Path` to `Enum` to tuples and variadic `*args`.
- [Parameter Metadata](guide/parameter-metadata.md) — `Arg`/`Opt`, env var
  fallback, hidden options.
- [Bundled Args](guide/bundled-args.md) — group related parameters into a
  `dataclass` or `NamedTuple`.
- [Path Validators](guide/path-validators.md) — `exists`, `file_okay`,
  `dir_okay`, `readable`, and `writable` checks.
- [CLI Rules](guide/cli-rules.md) — the short reference for how signatures
  map to flags.
- [Runtime Behavior](guide/runtime.md) — logging, testing, and how help and
  error output is rendered.
- [yeetr vs. typer](comparison.md) — an honest comparison so you can pick the
  right tool.
- [API Reference](modules.md) — generated reference for the public API.
- [Releases](releases.md) — how `yeetr` is versioned and shipped.
