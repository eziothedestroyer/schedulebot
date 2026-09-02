#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

if [[ ! -x .build-venv/bin/pyinstaller ]]; then
  python -m venv .build-venv
  .build-venv/bin/python -m pip install --upgrade pyinstaller -r requirements.txt
fi

.build-venv/bin/python -m pip install -q -r requirements.txt

.build-venv/bin/pyinstaller --clean --noconfirm ScheduleBot.spec
sha256sum dist/ScheduleBot > dist/ScheduleBot.sha256
echo "Built: dist/ScheduleBot"
echo "Checksum: dist/ScheduleBot.sha256"
