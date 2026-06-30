#!/bin/sh
set -e

alembic -c alembic.ini upgrade head

exec uvicorn hotline_prices.app:app --host 0.0.0.0 --port 8999
