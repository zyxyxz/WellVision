#!/usr/bin/env sh
set -eu

python -m compileall -q backend/app
PYTHONPATH=backend python -m unittest discover -s backend/tests

cd frontend
npm run typecheck
npm run build
