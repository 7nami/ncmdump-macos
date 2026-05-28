#!/bin/zsh
set -u

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found."
  echo "Install Python 3 first, then run this command again."
  echo
  read "?Press Enter to close..."
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "Error: openssl not found."
  echo "Install OpenSSL first, then run this command again."
  echo
  read "?Press Enter to close..."
  exit 1
fi

python3 "$SCRIPT_DIR/ncmdump_mac.py" --interactive --workers 4 --max-failures 3
status=$?

echo
if [[ $status -eq 0 ]]; then
  echo "All done."
elif [[ $status -eq 130 ]]; then
  echo "Interrupted."
else
  echo "Finished with errors. Exit code: $status"
fi
read "?Press Enter to close..."
exit "$status"
