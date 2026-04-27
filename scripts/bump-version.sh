#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION_FILE="$ROOT/VERSION"

if [ -n "$1" ]; then
    NEW_VERSION="$1"
else
    echo "Usage: bash scripts/bump-version.sh <new-version>"
    echo "Example: bash scripts/bump-version.sh 1.3.0-beta"
    echo ""
    echo "Current version: $(cat "$VERSION_FILE")"
    exit 1
fi

OLD_VERSION=$(cat "$VERSION_FILE" | tr -d '\n')

if [ "$OLD_VERSION" = "$NEW_VERSION" ]; then
    echo "Version is already $NEW_VERSION"
    exit 0
fi

SHORT_VERSION=$(echo "$NEW_VERSION" | sed 's/\.0-/-/')

echo "Bumping version: $OLD_VERSION -> $NEW_VERSION"
echo "Short version (landing): $SHORT_VERSION"
echo ""

OLD_SHORT=$(echo "$OLD_VERSION" | sed 's/\.0-/-/')

echo "$NEW_VERSION" > "$VERSION_FILE"
echo "  [1/7] VERSION file"

sed -i "s/APP_VERSION=$OLD_VERSION/APP_VERSION=$NEW_VERSION/" "$ROOT/.env.example"
echo "  [2/7] .env.example"

if [ -f "$ROOT/.env" ]; then
    sed -i "s/APP_VERSION=$OLD_VERSION/APP_VERSION=$NEW_VERSION/" "$ROOT/.env"
    echo "  [3/7] .env"
else
    echo "  [3/7] .env (skipped — not found)"
fi

sed -i "s/app_version: str = \"$OLD_VERSION\"/app_version: str = \"$NEW_VERSION\"/" "$ROOT/backend/app/config.py"
echo "  [4/7] backend/app/config.py"

sed -i "s/^version = \"$OLD_VERSION\"/version = \"$NEW_VERSION\"/" "$ROOT/backend/pyproject.toml"
echo "  [5/7] backend/pyproject.toml"

sed -i "s/\"version\": \"$OLD_VERSION\"/\"version\": \"$NEW_VERSION\"/" "$ROOT/frontend/package.json"
echo "  [6/7] frontend/package.json"

sed -i "s/\"softwareVersion\": \"$OLD_SHORT\"/\"softwareVersion\": \"$SHORT_VERSION\"/" "$ROOT/landing/index.html"
for locale in "$ROOT"/landing/public/locales/*.json; do
    lang=$(basename "$locale" .json)
    sed -i "s/v$OLD_SHORT/v$SHORT_VERSION/" "$locale"
done
echo "  [7/7] landing (index.html + locales)"

echo ""
echo "Done. Verify:"
echo "  grep APP_VERSION .env .env.example"
echo "  grep app_version backend/app/config.py"
echo "  grep '\"version\"' frontend/package.json backend/pyproject.toml"
echo "  grep softwareVersion landing/index.html"
echo ""
echo "Then: docker compose up -d backend && landing rebuild"
