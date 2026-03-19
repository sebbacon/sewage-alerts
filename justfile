# Replicates the GitHub Actions workflow locally.
# Copy .env.example to .env and fill in your credentials for `just run`.

set dotenv-load

# Create venv and install dev dependencies (run once)
devsetup:
    [ -d .venv ] || uv venv
    uv pip install -r requirements-dev.txt -q

# Run the spill check (mirrors "Check for nearby spills" step in check_spills.yml)
# Override example: POSTCODE="GL1 1AA" RADIUS=10 just run
run: devsetup
    uv run python check_spills.py --verbose \
        ${POSTCODE:+--postcode "$POSTCODE"} \
        ${RADIUS:+--radius "$RADIUS"} \
        ${EMAIL:+--email "$EMAIL"}

# Run tests
test: devsetup
    uv run pytest tests/ -v

# Interactive setup
configure:
    uv run python configure.py
