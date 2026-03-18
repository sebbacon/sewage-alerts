# Replicates the GitHub Actions workflow locally.
# Copy .env.example to .env and fill in your credentials for `just run`.

set dotenv-load

# Install runtime deps (mirrors "Install dependencies" step in check_spills.yml)
install:
    pip install -r requirements.txt

# Run the spill check (mirrors "Check for nearby spills" step in check_spills.yml)
run: install
    python3 check_spills.py

# Run tests
test:
    pip install -r requirements-dev.txt -q
    pytest tests/ -v

# Interactive setup
configure:
    python3 configure.py
