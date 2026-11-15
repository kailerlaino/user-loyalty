#!/bin/bash
# Stop hook: block the end of a turn (once) when files in the repo changed after PROJECT_CONTEXT.md,
# so the living project summary stays current. Generated output (logs/, transcripts/, previews/),
# caches, .git, .venv and .claude/ don't count. See CLAUDE.md.
input=$(cat)
# Already continuing because of this hook: let the turn end, so it can never loop.
if printf '%s' "$input" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0
ctx=PROJECT_CONTEXT.md
if [ ! -f "$ctx" ]; then
  echo "PROJECT_CONTEXT.md is missing. Recreate it (see CLAUDE.md) before ending the turn." >&2
  exit 2
fi
changed=$(find . \( -path ./logs -o -path ./transcripts -o -path ./previews -o -path ./.git \
    -o -path ./.venv -o -path ./.claude -o -name __pycache__ -o -name .pytest_cache \
    -o -name .ruff_cache -o -name .DS_Store \) -prune -o -type f -newer "$ctx" -print \
  | sed 's|^\./||' | sort | head -15)
[ -z "$changed" ] && exit 0
{
  echo "These project files changed after PROJECT_CONTEXT.md was last updated:"
  printf '%s\n' "$changed" | sed 's/^/  - /'
  echo "Update PROJECT_CONTEXT.md for this turn (where it stands, results, decisions, open threads," \
       "git state, the 'Last updated' date) before ending the turn. If nothing in it needs to change," \
       "update only its 'Last updated' line."
} >&2
exit 2
