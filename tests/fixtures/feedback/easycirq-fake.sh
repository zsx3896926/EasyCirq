#!/bin/sh
exec python "$(dirname "$0")/fake_easycirq.py" "$@"
