#!/usr/bin/env bash
set -e
python -m app.cli init
python -m app.scheduler &
exec python -m app.web
