<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/002-extract-desktop-tokens/plan.md
<!-- SPECKIT END -->

## Development

This project uses **uv** for Python environment management. Do not create
venvs or use pip directly.

### Common commands

```bash
# Run tests
make test

# Run linters on staged changes
make check

# Run linters on all files
make check-all

# Install dev tooling (uv, pre-commit hooks)
make bootstrap
```

### Debugging

To run Python with the correct project environment:

```bash
uv run python -c "from slack_cli.slack_tokens import find_slack_installation; ..."
uv run python -m slack_cli read 'https://...'
uv run slack-cli extract --list
```

Do not use `.venv/bin/python`, `pip install -e .`, or create virtual
environments manually.
