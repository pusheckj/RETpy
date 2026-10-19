#!/usr/bin/env bash
set -euo pipefail

# Retirement Monte Carlo - UI launcher

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

echo "======================================================================"
echo "  Retirement Monte Carlo"
echo "======================================================================"

if ! python3 -c "import streamlit" >/dev/null 2>&1; then
    echo ""
    echo "Streamlit is not installed. Install with:"
    echo "    pip install -r ui/requirements-ui.txt"
    echo ""
    exit 1
fi

cd "$PROJECT_ROOT"
exec streamlit run ui/app.py "$@"
