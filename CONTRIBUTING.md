# Contributing to CodeAtlas

Thanks for your interest. Bug reports, ideas and pull requests are all welcome.

## Set up

You need Python 3.11+, Node.js 20+ and `make`.

```bash
git clone https://github.com/Amrittr/codeatlas.git
cd codeatlas
make setup
make dev      # http://localhost:8000
```

## Test

```bash
make test                                  # backend + frontend unit tests
backend/.venv/bin/playwright install chromium   # once, for browser tests
make test-e2e                              # browser tests
make check                                 # syntax check
```

[docs/TESTING.md](docs/TESTING.md) explains what each suite covers.

## Principles for changes

These come from the product's goals, and reviews will check for them:

1. **Never execute uploaded code.** Treat every archive and file as hostile.
2. **Facts and inferences stay separate.** Anything guessed carries a confidence and a reason.
   Never invent files, imports or relationships.
3. **Every visible control works,** or is clearly marked as unavailable.
4. **Measure before claiming scale.** Add a benchmark or a test, not an adjective.
5. **Keep it simple.** The frontend is vanilla ES modules with no framework or bundler, and
   every new dependency needs a reason.

## Good places to start

- A new language: add an adapter in `backend/app/analyzers/parsers/` (see `__init__.py`).
- More frameworks and services: extend `backend/app/analyzers/architecture/knowledge.py`.
- The [roadmap](docs/IMPLEMENTATION_PLAN.md) lists what comes next.

## Pull requests

Keep them focused, add tests, and update the docs when behavior changes. CI must pass.

## Security issues

Please report them privately: see [docs/SECURITY.md](docs/SECURITY.md#reporting).

## License

By contributing, you agree that your contributions are licensed under the
[AGPL-3.0](LICENSE), the license of this project.
