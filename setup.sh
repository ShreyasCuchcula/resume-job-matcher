#!/usr/bin/env bash
# One-command setup for resume-job-matcher.
#
# - creates ./venv if it doesn't exist
# - installs pinned dependencies
# - downloads the spaCy model used for sentence segmentation / PII backstop
# - creates .env from .env.example if missing
# - runs Alembic migrations once db/migrations is populated (Stage 1+)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

if [ -f "$VENV_DIR/Scripts/activate" ]; then
    # Windows (venv created with the Windows py launcher / git-bash)
    PYTHON="$VENV_DIR/Scripts/python.exe"
elif [ -f "$VENV_DIR/bin/activate" ]; then
    # POSIX
    PYTHON="$VENV_DIR/bin/python"
else
    echo "Could not find a Python executable inside $VENV_DIR" >&2
    exit 1
fi

echo "Upgrading pip ..."
"$PYTHON" -m pip install --upgrade pip

echo "Installing dependencies from requirements.txt ..."
"$PYTHON" -m pip install -r requirements.txt

echo "Downloading spaCy model en_core_web_sm ..."
"$PYTHON" -m spacy download en_core_web_sm

if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example ..."
    cp .env.example .env
fi

if [ -f "alembic.ini" ]; then
    echo "Running database migrations ..."
    "$PYTHON" -m alembic upgrade head
else
    echo "alembic.ini not present yet (added in a later stage) - skipping migrations."
fi

echo ""
echo "Setup complete."
echo "Activate the environment with:"
echo "  source $VENV_DIR/Scripts/activate   (Windows/git-bash)"
echo "  source $VENV_DIR/bin/activate       (macOS/Linux)"
