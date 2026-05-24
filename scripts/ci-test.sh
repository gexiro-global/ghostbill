#!/usr/bin/env bash
# =============================================================================
# GhostBill — Local CI Test Runner
# =============================================================================
# Mirrors the GitHub Actions pipeline for local verification.
# Run from repo root: ./scripts/ci-test.sh
#
# Prerequisites: docker, docker compose, pip install ruff
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE="docker compose -p ghostbill-ci -f docker-compose.test.yml"
PASSED=true

cleanup() {
    echo ""
    echo "=== Cleanup ==="
    $COMPOSE down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

echo "=== GhostBill CI Test Runner ==="
echo "Started: $(date)"
echo ""

# --- Step 1: Environment ---
echo "=== Step 1: Environment ==="
if [ ! -f .env.test ]; then
    cp .env.test.example .env.test
    echo "Created .env.test from .env.test.example"
fi

# --- Step 2: Lint ---
echo ""
echo "=== Step 2: Lint (ruff check) ==="
if command -v ruff &>/dev/null; then
    ruff check --config backend/pyproject.toml backend/app/
    echo "ruff check: PASSED"
else
    echo "WARNING: ruff not installed, skipping lint"
fi

# --- Step 3: Format ---
echo ""
echo "=== Step 3: Format (ruff format --check) ==="
if command -v ruff &>/dev/null; then
    ruff format --check --config backend/pyproject.toml backend/app/
    echo "ruff format: PASSED"
else
    echo "WARNING: ruff not installed, skipping format check"
fi

# --- Step 4: Build ---
echo ""
echo "=== Step 4: Build containers ==="
$COMPOSE build --no-cache backend
echo "Build: PASSED"

# --- Step 5: Start infrastructure ---
echo ""
echo "=== Step 5: Start PostgreSQL + Redis ==="
$COMPOSE up -d postgres redis
echo "Waiting for healthy..."
sleep 5

# --- Step 6: Start backend (runs alembic upgrade head via command) ---
echo ""
echo "=== Step 6: Start backend + migrate ==="
$COMPOSE up -d backend
echo "Waiting for backend healthy..."
for i in $(seq 1 30); do
    if $COMPOSE exec backend curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "Backend healthy after ${i}s"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Backend failed to start"
        $COMPOSE logs backend | tail -30
        exit 1
    fi
    sleep 1
done

# --- Step 8: Test ---
echo ""
echo "=== Step 8: pytest ==="
# CI TEST SCOPE: wave5 only.
# wave5 tests are service-level tests designed for CI (use app DB URL).
# Other test directories are excluded for specific reasons:
# - Root-level (e2e_simulated, edge_cases, etc.): manual integration tests
#   using cached merchants and host port mappings (127.0.0.1:5445).
# - wave1: asyncpg direct connections to host port 5445.
# - wave2, wave3a, wave3b, wave4: static analysis tests using
#   Path("backend/app/...") relative paths that don't resolve in Docker.
# TODO: refactor wave1-4 tests to use app DB URL / __file__ base paths
# so they can run in CI.
$COMPOSE exec backend python3 -m pytest \
    tests/wave5 \
    -v --tb=short || PASSED=false

# --- Result ---
echo ""
echo "=== CI Complete ==="
echo "Finished: $(date)"
if [ "$PASSED" = true ]; then
    echo "RESULT: ALL CHECKS PASSED"
    exit 0
else
    echo "RESULT: TESTS FAILED"
    exit 1
fi
