# V6 MASTER PRO workspace shortcuts.
# This file is sourced by .config/bashrc when a Replit shell opens in this project.

project_root="${REPL_HOME:-$(pwd)}"

sp() {
  find "$project_root" \
    -path "$project_root/.git" -prune -o \
    -path "$project_root/node_modules" -prune -o \
    -path "$project_root/dist" -prune -o \
    -type f -print | sort > "$project_root/project.txt"
  printf 'Project structure written to %s/project.txt\n' "$project_root"
}

req() {
  python -m pip freeze
}

deploy() {
  pnpm run typecheck &&
    pnpm --filter @workspace/api-server run build &&
    PORT="${PORT:-24527}" BASE_PATH="${BASE_PATH:-/}" pnpm --filter @workspace/v6-master-pro run build &&
    printf 'Build checks passed. Publish through Replit; Render still needs a configured service.\n'
}

push() {
  git add -- \
    .bash_aliases \
    '*_blueprint.txt' \
    artifacts/api-server/src/routes/trading.ts \
    artifacts/api-server/src/services/market-data.ts \
    artifacts/v6-master-pro/src/App.tsx \
    lib/api-spec/openapi.yaml \
    lib/api-client-react/src/generated/ \
    lib/api-zod/src/generated/
  if git diff --cached --quiet; then
    printf 'No staged changes to commit.\n'
    return 0
  fi
  git commit -m "${*:-Sync V6 MASTER PRO}"
  git push origin main
}

# Destructive by design: restores HEAD and removes untracked files/directories.
# Run only when a hard rollback is intentional.
original() {
  git reset --hard HEAD && git clean -fd
}
