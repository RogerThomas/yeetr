# Getting Started

## Zero-boilerplate: just yeet it

Installing `yeetr` also installs a `yeet` script that finds and runs a
function in any Python file.

No `if __name__ == "__main__"` block, no `yeetr.run(...)` call — just
the function:

```python
# app.py
def main(thing: int, *, n: float = 0.1) -> None:
    print(thing, n)
```

```bash
yeet app.py 5 -n 0.2
```

If `app.py` does not exist yet, `yeet` will scaffold a runnable Python
script for you, mark it executable, and print the created path. Run the
same command a second time, or call `./app.py` directly, and it will
execute normally.

The default function name is `main`. To run another function, name it — the
target must be a **public** `def`/`async def` defined in that file (not an
import, a class, or a `_`-prefixed helper). Decorated functions qualify only
if the decorator preserves the function's identity with `functools.wraps` —
otherwise the name is not recognised as a runnable function:

```python
# app.py
def main(thing: int) -> None: ...
def greet(name: str, *, loud: bool = False) -> None: ...
```

```bash
yeet app.py greet world --loud
```

Because the `.py` file identifies itself, the function can also come first or
be attached with a colon — pick whichever reads best:

```bash
yeet greet app.py world --loud   # function first
yeet app.py:greet world --loud   # FILE:FUNC
```

Hyphens in the name are treated as underscores, so `yeet app.py
add-item-to-index` and `yeet app.py add_item_to_index` both run
`add_item_to_index`.

If `main` takes a **string** first argument, a bare `yeet app.py greet` is
genuinely ambiguous — `greet` could be the function to run *or* a value for
`main` — so yeetr raises instead of guessing. Disambiguate with
`yeet app.py main greet` (pass it to `main`) or the `app.py:greet` /
function-first forms (run `greet`).

`yeet app.py --help` prints the **target function's** help, not yeet's.

You can still use the explicit `yeetr.run(main)` form when you prefer —
the `yeet` script is just sugar on top of it.

## Explicit `yeetr.run(main)`

```python
def main(thing: int, *, n: float = 0.1) -> None:
    print(thing, n)


if __name__ == "__main__":
    import yeetr
    yeetr.run(main)
```

```bash
yeet app.py 5 -n 0.2
```

Note the bare `*` in the signature: parameters **before** it become
positional CLI args, parameters **after** it become `--options`. That's
the whole mapping — no decorators, no per-parameter annotations needed.

## Script Execution

### Hashbang

For tiny scripts, you can make the file itself executable and let `yeet`
discover `main` directly from the shebang. The short forms are:

```python
#!yeet
```

or:

```python
#!uv run yeet
```

For example:

```python
#!yeet

def main(name: str, *, loud: bool = False) -> None:
    print(name.upper() if loud else name)
```

Then run it directly:

```bash
chmod +x greet.py
./greet.py world --loud
```

To make the script run a function other than `main`, name it in the shebang —
`#!yeet greet` — and running `./greet.py ...` invokes that function directly.

## Next steps

- [Async Support](async.md) for `async def main`.
- [Parameter Types](parameter-types.md) for everything yeetr can type-check
  and parse.
