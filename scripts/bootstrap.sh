#!/usr/bin/env bash
set -Eeuo pipefail

DEFAULT_UPSTREAM_REPO="${GIT_SWEATY_UPSTREAM_REPO:-aspain/git-sweaty}"
SETUP_SCRIPT_REL="scripts/setup_auth.py"
BOOTSTRAP_SELECTED_REPO_DIR=""
BOOTSTRAP_DETECTED_FORK_REPO=""
BOOTSTRAP_SELECTED_FORK_REPO=""

info() {
  printf '%s\n' "$*"
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

is_wsl() {
  [[ -n "${WSL_DISTRO_NAME:-}" || -n "${WSL_INTEROP:-}" ]] && return 0
  [[ -r /proc/version ]] && grep -qi "microsoft" /proc/version
}

expand_path() {
  local path="$1"
  local drive rest wsl_mount_prefix
  if [[ "$path" == "~" ]]; then
    printf '%s\n' "$HOME"
    return 0
  fi
  if [[ "$path" == ~/* ]]; then
    printf '%s/%s\n' "$HOME" "${path#~/}"
    return 0
  fi
  if is_wsl && [[ "$path" =~ ^([A-Za-z]):[\\/](.*)$ ]]; then
    drive="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]')"
    rest="${BASH_REMATCH[2]}"
    rest="${rest//\\//}"
    wsl_mount_prefix="${GIT_SWEATY_WSL_MOUNT_PREFIX:-/mnt}"
    wsl_mount_prefix="${wsl_mount_prefix%/}"
    printf '%s/%s/%s\n' "$wsl_mount_prefix" "$drive" "$rest"
    return 0
  fi
  printf '%s\n' "$path"
}

is_compatible_clone() {
  local repo_dir="$1"
  [[ -e "$repo_dir/.git" && -f "$repo_dir/$SETUP_SCRIPT_REL" ]] || return 1
  git -C "$repo_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

prompt_yes_no() {
  local prompt="$1"
  local default="${2:-Y}"
  local suffix="[y/N]"
  local answer

  if [[ "$default" == "Y" ]]; then
    suffix="[Y/n]"
  fi

  while true; do
    if ! read -r -p "$prompt $suffix: " answer; then
      [[ "$default" == "Y" ]] && return 0 || return 1
    fi
    answer="$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')"
    case "$answer" in
      "")
        [[ "$default" == "Y" ]] && return 0 || return 1
        ;;
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *) printf '%s\n' "Please enter y or n." >&2 ;;
    esac
  done
}

trim_whitespace() {
  local value="$1"
  printf '%s' "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

prompt_setup_mode() {
  local choice
  printf '\n' >&2
  printf '%s\n' "Choose setup mode:" >&2
  printf '%s\n' "  1) Recommended (Online-only, no local clone) [default]" >&2
  printf '%s\n' "  2) Advanced (Local clone + git remotes)" >&2

  while true; do
    read -r -p "Selection (1-2, default 1): " choice || return 1
    choice="$(trim_whitespace "$choice")"
    choice="$(printf '%s' "$choice" | tr '[:upper:]' '[:lower:]')"
    case "$choice" in
      ""|1|recommended|recommended\ mode|online|online\ mode|online-only)
        printf '%s\n' "online"
        return 0
        ;;
      2|advanced|advanced\ mode|local|local\ mode)
        printf '%s\n' "local"
        return 0
        ;;
      *)
        printf '%s\n' "Please enter 1 or 2." >&2
        ;;
    esac
  done
}

prompt_fork_name() {
  local default_name="$1"
  local answer

  if ! prompt_yes_no "Use a custom name for your fork?" "N"; then
    printf '%s\n' "$default_name"
    return 0
  fi

  while true; do
    read -r -p "Fork name (repo only, default: ${default_name}): " answer || return 1
    answer="$(trim_whitespace "$answer")"
    if [[ -z "$answer" ]]; then
      answer="$default_name"
    fi

    if [[ "$answer" =~ ^[A-Za-z0-9._-]+$ ]]; then
      printf '%s\n' "$answer"
      return 0
    fi
    warn "Invalid fork name. Use only letters, numbers, '.', '_' or '-'."
  done
}

is_valid_repo_slug() {
  local slug="$1"
  [[ "$slug" =~ ^[^/[:space:]]+/[^/[:space:]]+$ ]]
}

normalize_repo_input() {
  local value normalized
  value="$(trim_whitespace "$1")"
  if [[ -z "$value" ]]; then
    return 1
  fi

  normalized="$value"
  if [[ "$value" =~ ^https?://github\.com/([^/]+)/([^/]+)/*$ ]]; then
    normalized="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  elif [[ "$value" =~ ^git@github\.com:([^/]+)/([^/]+)\.git$ ]]; then
    normalized="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  fi

  normalized="${normalized%.git}"
  normalized="${normalized%/}"
  normalized="$(trim_whitespace "$normalized")"
  if ! is_valid_repo_slug "$normalized"; then
    return 1
  fi
  printf '%s\n' "$normalized"
}

list_writable_repos_for_user() {
  local login="$1"
  gh repo list "$login" \
    --limit 200 \
    --json nameWithOwner,viewerPermission \
    --jq '.[] | select(.viewerPermission == "ADMIN" or .viewerPermission == "MAINTAIN" or .viewerPermission == "WRITE") | .nameWithOwner' \
    2>/dev/null \
    || true
}

prompt_repo_slug() {
  local default_repo="${1:-}"
  local login="${2:-}"
  local prompt answer selected normalized
  local -a suggestions=()
  local index raw_choice default_choice

  if [[ -n "$login" ]]; then
    while IFS= read -r selected; do
      selected="$(trim_whitespace "$selected")"
      [[ -n "$selected" ]] || continue
      suggestions+=("$selected")
    done < <(list_writable_repos_for_user "$login")
  fi

  if (( ${#suggestions[@]} > 0 )); then
    printf '\n' >&2
    printf '%s\n' "Detected writable repositories for ${login}:" >&2
    for index in "${!suggestions[@]}"; do
      printf '  %d) %s\n' "$((index + 1))" "${suggestions[$index]}" >&2
    done
    printf '%s\n' "Enter a number, OWNER/REPO, or GitHub URL." >&2
  fi

  prompt="Repository to configure (OWNER/REPO or URL)"
  default_choice=""
  if [[ -n "$default_repo" ]]; then
    normalized="$(normalize_repo_input "$default_repo" || true)"
    if [[ -n "$normalized" ]]; then
      default_choice="$normalized"
      prompt="${prompt} (default: ${default_choice})"
    fi
  elif (( ${#suggestions[@]} > 0 )); then
    default_choice="${suggestions[0]}"
    prompt="${prompt} (default: ${default_choice})"
  fi
  prompt="${prompt}: "

  while true; do
    read -r -p "$prompt" answer || return 1
    answer="$(trim_whitespace "$answer")"
    if [[ "$answer" =~ ^[0-9]+$ ]] && (( ${#suggestions[@]} > 0 )); then
      raw_choice="$answer"
      if (( raw_choice >= 1 && raw_choice <= ${#suggestions[@]} )); then
        answer="${suggestions[$((raw_choice - 1))]}"
      else
        printf '%s\n' "Selection out of range. Choose one of the listed numbers." >&2
        continue
      fi
    fi

    if [[ -z "$answer" ]]; then
      if [[ -n "$default_choice" ]]; then
        answer="$default_choice"
      else
        printf '%s\n' "A repository target is required." >&2
        continue
      fi
    fi

    normalized="$(normalize_repo_input "$answer" || true)"
    if [[ -z "$normalized" ]]; then
      printf '%s\n' "Invalid format. Use OWNER/REPO or https://github.com/OWNER/REPO." >&2
      continue
    fi
    answer="$normalized"

    if ! gh repo view "$answer" >/dev/null 2>&1; then
      warn "Repository is not accessible with current gh auth: $answer"
      continue
    fi

    local can_push
    can_push="$(gh api "repos/${answer}" --jq '.permissions.push' 2>/dev/null || true)"
    if [[ "$can_push" != "true" ]]; then
      warn "Current gh account does not have write access to: $answer"
      continue
    fi

    printf '%s\n' "$answer"
    return 0
  done
}

require_cmd() {
  have_cmd "$1" || fail "Missing required command: $1"
}

gh_is_authenticated() {
  gh auth status >/dev/null 2>&1
}

ensure_gh_auth() {
  require_cmd gh
  if gh_is_authenticated; then
    return 0
  fi

  info "GitHub CLI is not authenticated."
  if prompt_yes_no "Run gh auth login now?" "Y"; then
    gh auth login
  fi

  gh_is_authenticated || fail "GitHub CLI auth is required. Run 'gh auth login' and re-run bootstrap."
}

repo_name_from_slug() {
  local slug="$1"
  printf '%s\n' "${slug##*/}"
}

discover_existing_fork_repo() {
  local login="$1"
  local upstream_repo="$2"

  gh repo list "$login" \
    --fork \
    --limit 1000 \
    --json nameWithOwner,parent \
    --jq ".[] | select(.parent.nameWithOwner == \"$upstream_repo\") | .nameWithOwner" \
    2>/dev/null \
    | head -n 1 \
    || true
}

discover_existing_fork_repo_via_api() {
  local login="$1"
  local upstream_repo="$2"

  gh api "repos/${upstream_repo}/forks?per_page=100" \
    --paginate \
    --jq ".[] | select(.owner.login == \"$login\") | .full_name" \
    2>/dev/null \
    | head -n 1 \
    || true
}

detect_existing_fork_repo() {
  local upstream_repo="$1"
  local login="$2"
  local explicit="${GIT_SWEATY_FORK_REPO:-}"
  local discovered discovered_api

  if [[ -n "$explicit" ]]; then
    gh repo view "$explicit" >/dev/null 2>&1 || return 1
    printf '%s\n' "$explicit"
    return 0
  fi

  discovered="$(discover_existing_fork_repo "$login" "$upstream_repo")"
  if [[ -n "$discovered" ]] && gh repo view "$discovered" >/dev/null 2>&1; then
    printf '%s\n' "$discovered"
    return 0
  fi

  discovered_api="$(discover_existing_fork_repo_via_api "$login" "$upstream_repo")"
  if [[ -n "$discovered_api" ]] && gh repo view "$discovered_api" >/dev/null 2>&1; then
    printf '%s\n' "$discovered_api"
    return 0
  fi

  return 1
}

resolve_fork_repo() {
  local upstream_repo="$1"
  local login="$2"
  local detected

  detected="$(detect_existing_fork_repo "$upstream_repo" "$login" || true)"
  if [[ -n "$detected" ]]; then
    printf '%s\n' "$detected"
    return 0
  fi

  fail "Unable to find an accessible fork for ${upstream_repo} under ${login}. Set GIT_SWEATY_FORK_REPO=<owner>/<repo> and retry."
}

ensure_fork_exists() {
  local upstream_repo="$1"
  local ask_reuse_existing="${2:-N}"
  local login existing_fork fork_repo fork_name default_fork_name
  local fork_cmd

  BOOTSTRAP_SELECTED_FORK_REPO=""
  ensure_gh_auth

  login="$(gh api user --jq .login 2>/dev/null || true)"
  [[ -n "$login" ]] || fail "Unable to resolve GitHub username from current gh auth session."

  existing_fork="$(detect_existing_fork_repo "$upstream_repo" "$login" || true)"
  if [[ -n "$existing_fork" ]]; then
    info "Found existing fork: $existing_fork"
    if [[ "$ask_reuse_existing" != "Y" ]] || prompt_yes_no "Use this fork?" "Y"; then
      gh repo view "$existing_fork" >/dev/null 2>&1 || fail "Fork is not accessible: $existing_fork"
      BOOTSTRAP_SELECTED_FORK_REPO="$existing_fork"
      return 0
    fi
  fi

  default_fork_name="$(repo_name_from_slug "$upstream_repo")"
  fork_name="$(prompt_fork_name "$default_fork_name")"
  fork_repo="${login}/${fork_name}"
  info "Creating fork repository: $fork_repo"

  fork_cmd=(gh repo fork "$upstream_repo" --clone=false --remote=false)
  if [[ "$fork_name" != "$default_fork_name" ]]; then
    fork_cmd+=(--fork-name "$fork_name")
  fi
  if ! "${fork_cmd[@]}" >/dev/null 2>&1; then
    warn "Fork creation command did not succeed cleanly. Continuing if fork already exists."
  fi

  if ! gh repo view "$fork_repo" >/dev/null 2>&1; then
    fork_repo="$(resolve_fork_repo "$upstream_repo" "$login")"
  fi

  gh repo view "$fork_repo" >/dev/null 2>&1 || fail "Fork is not accessible: $fork_repo"
  BOOTSTRAP_SELECTED_FORK_REPO="$fork_repo"
}

detect_local_repo_root() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 1
  fi

  local root
  root="$(git rev-parse --show-toplevel)"
  if [[ -f "$root/$SETUP_SCRIPT_REL" ]]; then
    printf '%s\n' "$root"
    return 0
  fi
  return 1
}

ensure_repo_dir_ready() {
  local repo_dir="$1"
  if is_compatible_clone "$repo_dir"; then
    return 0
  fi
  if [[ -e "$repo_dir" ]]; then
    fail "Path already exists and is not a compatible clone: $repo_dir"
  fi
}

prompt_existing_clone_path() {
  local default_repo_dir="$1"
  local raw repo_dir

  printf '\n' >&2
  printf 'Default clone directory is: %s\n' "$default_repo_dir" >&2
  printf 'Choose this for a fresh setup, or point to an existing compatible clone.\n' >&2
  if ! prompt_yes_no "Use an existing local clone path?" "N"; then
    return 1
  fi

  while true; do
    read -r -p "Existing clone path (press Enter to cancel): " raw || return 1
    raw="$(printf '%s' "$raw" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    if [[ -z "$raw" ]]; then
      return 1
    fi

    repo_dir="$(expand_path "$raw")"
    if is_compatible_clone "$repo_dir"; then
      printf '%s\n' "$repo_dir"
      return 0
    fi

    warn "Not a compatible clone: $repo_dir"
    warn "Expected both: $repo_dir/.git and $repo_dir/$SETUP_SCRIPT_REL"
  done
}

configure_fork_remotes() {
  local repo_dir="$1"
  local upstream_repo="$2"
  local fork_repo="$3"

  git -C "$repo_dir" remote set-url origin "https://github.com/${fork_repo}.git"
  if git -C "$repo_dir" remote get-url upstream >/dev/null 2>&1; then
    git -C "$repo_dir" remote set-url upstream "https://github.com/${upstream_repo}.git"
  else
    git -C "$repo_dir" remote add upstream "https://github.com/${upstream_repo}.git"
  fi
}

prefer_existing_fork_clone_dir() {
  local repo_dir="$1"
  local fork_repo="$2"
  local fork_repo_dir

  fork_repo_dir="$(dirname "$repo_dir")/$(repo_name_from_slug "$fork_repo")"
  if [[ "$fork_repo_dir" == "$repo_dir" ]]; then
    printf '%s\n' "$repo_dir"
    return 0
  fi

  if is_compatible_clone "$fork_repo_dir"; then
    printf '%s\n' "$fork_repo_dir"
    return 0
  fi

  printf '%s\n' "$repo_dir"
}

detect_wsl_windows_clone_by_repo_name() {
  local repo_name="$1"
  local old_ifs
  local users_root user_home base candidate owner_dir
  local default_users_roots="/mnt/c/Users:/mnt/d/Users:/mnt/e/Users"
  local users_roots="${GIT_SWEATY_WSL_USERS_ROOTS:-$default_users_roots}"

  is_wsl || return 1
  [[ -n "$repo_name" ]] || return 1

  old_ifs="$IFS"
  IFS=":"
  for users_root in $users_roots; do
    [[ -d "$users_root" ]] || continue
    for user_home in "$users_root"/*; do
      [[ -d "$user_home" ]] || continue
      for base in \
        "$user_home/source/repos" \
        "$user_home/repos" \
        "$user_home/source" \
        "$user_home/Documents/GitHub" \
        "$user_home/Documents/repos" \
        "$user_home/code" \
        "$user_home/dev"; do
        [[ -d "$base" ]] || continue
        candidate="$base/$repo_name"
        if is_compatible_clone "$candidate"; then
          IFS="$old_ifs"
          printf '%s\n' "$candidate"
          return 0
        fi
        for owner_dir in "$base"/*; do
          [[ -d "$owner_dir" ]] || continue
          candidate="$owner_dir/$repo_name"
          if is_compatible_clone "$candidate"; then
            IFS="$old_ifs"
            printf '%s\n' "$candidate"
            return 0
          fi
        done
      done
    done
  done
  IFS="$old_ifs"
  return 1
}

auto_detect_existing_compatible_clone() {
  local upstream_repo="$1"
  local default_repo_dir="$2"
  local login fork_repo fork_name upstream_name candidate_dir detected_wsl

  BOOTSTRAP_SELECTED_REPO_DIR=""
  BOOTSTRAP_DETECTED_FORK_REPO=""

  if is_compatible_clone "$default_repo_dir"; then
    BOOTSTRAP_SELECTED_REPO_DIR="$default_repo_dir"
    return 0
  fi

  if have_cmd gh && gh_is_authenticated; then
    login="$(gh api user --jq .login 2>/dev/null || true)"
    if [[ -n "$login" ]]; then
      fork_repo="$(detect_existing_fork_repo "$upstream_repo" "$login" || true)"
      if [[ -n "$fork_repo" ]]; then
        fork_name="$(repo_name_from_slug "$fork_repo")"
        upstream_name="$(repo_name_from_slug "$upstream_repo")"
        candidate_dir="$(dirname "$default_repo_dir")/$fork_name"
        if is_compatible_clone "$candidate_dir"; then
          BOOTSTRAP_SELECTED_REPO_DIR="$candidate_dir"
          BOOTSTRAP_DETECTED_FORK_REPO="$fork_repo"
          return 0
        fi

        detected_wsl="$(detect_wsl_windows_clone_by_repo_name "$fork_name" || true)"
        if [[ -n "$detected_wsl" ]]; then
          BOOTSTRAP_SELECTED_REPO_DIR="$detected_wsl"
          BOOTSTRAP_DETECTED_FORK_REPO="$fork_repo"
          return 0
        fi

        if [[ "$fork_name" != "$upstream_name" ]]; then
          detected_wsl="$(detect_wsl_windows_clone_by_repo_name "$upstream_name" || true)"
          if [[ -n "$detected_wsl" ]]; then
            BOOTSTRAP_SELECTED_REPO_DIR="$detected_wsl"
            return 0
          fi
        fi
      fi
    else
      upstream_name="$(repo_name_from_slug "$upstream_repo")"
      detected_wsl="$(detect_wsl_windows_clone_by_repo_name "$upstream_name" || true)"
      if [[ -n "$detected_wsl" ]]; then
        BOOTSTRAP_SELECTED_REPO_DIR="$detected_wsl"
        return 0
      fi
    fi
  fi

  upstream_name="$(repo_name_from_slug "$upstream_repo")"
  detected_wsl="$(detect_wsl_windows_clone_by_repo_name "$upstream_name" || true)"
  if [[ -n "$detected_wsl" ]]; then
    BOOTSTRAP_SELECTED_REPO_DIR="$detected_wsl"
    return 0
  fi
  return 1
}

fork_and_clone() {
  local upstream_repo="$1"
  local repo_dir="$2"
  local fork_repo

  ensure_fork_exists "$upstream_repo"
  fork_repo="$BOOTSTRAP_SELECTED_FORK_REPO"
  info "Using fork repository: $fork_repo"
  local preferred_repo_dir
  preferred_repo_dir="$(prefer_existing_fork_clone_dir "$repo_dir" "$fork_repo")"
  if [[ "$preferred_repo_dir" != "$repo_dir" ]]; then
    info "Detected existing local fork clone at $preferred_repo_dir"
    repo_dir="$preferred_repo_dir"
  fi

  if is_compatible_clone "$repo_dir"; then
    info "Using existing clone at $repo_dir"
  else
    ensure_repo_dir_ready "$repo_dir"
    info "Cloning fork into $repo_dir"
    git clone "https://github.com/${fork_repo}.git" "$repo_dir"
  fi

  configure_fork_remotes "$repo_dir" "$upstream_repo" "$fork_repo"
  BOOTSTRAP_SELECTED_REPO_DIR="$repo_dir"
}

run_online_setup() {
  local upstream_repo="$1"
  shift || true
  local login target_repo default_branch archive_url tmp_dir archive_path extract_dir extracted_root setup_script status

  require_cmd curl
  require_cmd python3
  require_cmd tar
  ensure_gh_auth

  login="$(gh api user --jq .login 2>/dev/null || true)"
  [[ -n "$login" ]] || fail "Unable to resolve GitHub username from current gh auth session."

  if prompt_yes_no "Create/use a fork in your GitHub account first? (recommended)" "Y"; then
    ensure_fork_exists "$upstream_repo" "Y"
    target_repo="$BOOTSTRAP_SELECTED_FORK_REPO"
  else
    info "Using non-fork mode: target repository must be writable by the current gh account."
    target_repo="$(prompt_repo_slug "$(detect_existing_fork_repo "$upstream_repo" "$login" || true)" "$login")"
  fi

  info ""
  info "Setup summary:"
  info "- Mode: Recommended (Online-only)"
  info "- Target repository: $target_repo"
  if ! prompt_yes_no "Proceed?" "Y"; then
    info "Skipped online setup."
    return 0
  fi

  default_branch="$(gh api "repos/${upstream_repo}" --jq .default_branch 2>/dev/null || true)"
  [[ -n "$default_branch" ]] || default_branch="main"
  archive_url="https://github.com/${upstream_repo}/archive/refs/heads/${default_branch}.tar.gz"
  tmp_dir="$(mktemp -d)"
  archive_path="${tmp_dir}/source.tar.gz"
  extract_dir="${tmp_dir}/source"

  info "Downloading setup source bundle from ${archive_url}"
  if ! curl -fsSL "$archive_url" -o "$archive_path"; then
    rm -rf "$tmp_dir"
    fail "Unable to download setup source bundle from ${archive_url}"
  fi

  mkdir -p "$extract_dir"
  if ! tar -xzf "$archive_path" -C "$extract_dir"; then
    rm -rf "$tmp_dir"
    fail "Unable to extract setup source bundle."
  fi

  extracted_root="$(find "$extract_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1 || true)"
  setup_script="${extracted_root}/${SETUP_SCRIPT_REL}"
  if [[ -z "$extracted_root" || ! -f "$setup_script" ]]; then
    rm -rf "$tmp_dir"
    fail "Setup script not found in downloaded source bundle (${SETUP_SCRIPT_REL})."
  fi

  info ""
  info "Launching online setup (no local clone)..."
  set +e
  python3 "$setup_script" --repo "$target_repo" "$@"
  status=$?
  set -e

  rm -rf "$tmp_dir"
  return "$status"
}

clone_upstream() {
  local upstream_repo="$1"
  local repo_dir="$2"

  if is_compatible_clone "$repo_dir"; then
    info "Using existing clone at $repo_dir"
    BOOTSTRAP_SELECTED_REPO_DIR="$repo_dir"
    return 0
  fi

  ensure_repo_dir_ready "$repo_dir"
  info "Cloning upstream repository into $repo_dir"
  git clone "https://github.com/${upstream_repo}.git" "$repo_dir"
  BOOTSTRAP_SELECTED_REPO_DIR="$repo_dir"
}

run_setup() {
  local repo_root="$1"
  shift || true

  [[ -f "$repo_root/$SETUP_SCRIPT_REL" ]] || fail "Missing setup script: $repo_root/$SETUP_SCRIPT_REL"
  ensure_gh_auth
  require_cmd python3

  info ""
  info "Launching setup script..."
  (cd "$repo_root" && python3 "$SETUP_SCRIPT_REL" "$@")
}

main() {
  local upstream_repo="$DEFAULT_UPSTREAM_REPO"
  local repo_dir local_root existing_clone_path setup_mode

  require_cmd python3

  if have_cmd git; then
    if local_root="$(detect_local_repo_root)"; then
      info "Detected local clone: $local_root"
      if prompt_yes_no "Run setup now?" "Y"; then
        run_setup "$local_root" "$@"
      else
        info "Skipped setup. Run this when ready:"
        info "  (cd \"$local_root\" && ./scripts/bootstrap.sh)"
      fi
      return 0
    fi
  fi

  repo_dir="$(pwd)/$(repo_name_from_slug "$upstream_repo")"
  setup_mode="$(prompt_setup_mode)"
  if [[ "$setup_mode" == "online" ]]; then
    run_online_setup "$upstream_repo" "$@"
    return 0
  fi

  require_cmd git
  info "No compatible local clone detected in current working tree."
  info "Upstream repository: $upstream_repo"
  info "Default clone directory: $repo_dir"
  if auto_detect_existing_compatible_clone "$upstream_repo" "$repo_dir"; then
    repo_dir="$BOOTSTRAP_SELECTED_REPO_DIR"
    info "Detected existing compatible local clone at $repo_dir"
    if [[ -n "$BOOTSTRAP_DETECTED_FORK_REPO" ]]; then
      configure_fork_remotes "$repo_dir" "$upstream_repo" "$BOOTSTRAP_DETECTED_FORK_REPO"
    fi
    info ""
    info "Setup summary:"
    info "- Mode: Advanced (Local clone + git remotes)"
    info "- Local clone path: $repo_dir"
    if [[ -n "$BOOTSTRAP_DETECTED_FORK_REPO" ]]; then
      info "- Fork repository: $BOOTSTRAP_DETECTED_FORK_REPO"
    fi
    if prompt_yes_no "Run setup now?" "Y"; then
      run_setup "$repo_dir" "$@"
    else
      info "Setup not run. Next step:"
      info "  (cd \"$repo_dir\" && ./scripts/bootstrap.sh)"
    fi
    return 0
  fi

  if existing_clone_path="$(prompt_existing_clone_path "$repo_dir")"; then
    repo_dir="$existing_clone_path"
    info "Using existing clone at $repo_dir"
    info ""
    info "Setup summary:"
    info "- Mode: Advanced (Local clone + git remotes)"
    info "- Local clone path: $repo_dir"
    if prompt_yes_no "Run setup now?" "Y"; then
      run_setup "$repo_dir" "$@"
    else
      info "Setup not run. Next step:"
      info "  (cd \"$repo_dir\" && ./scripts/bootstrap.sh)"
    fi
    return 0
  fi

  if ! prompt_yes_no "Proceed with fork-based local setup? (for non-fork targets, choose online mode)" "Y"; then
    info "Skipped local setup."
    info "Use option 1 (Recommended online-only mode) if you want a non-fork target repository."
    return 0
  fi
  fork_and_clone "$upstream_repo" "$repo_dir"

  if [[ -n "$BOOTSTRAP_SELECTED_REPO_DIR" ]]; then
    repo_dir="$BOOTSTRAP_SELECTED_REPO_DIR"
  fi

  info ""
  info "Setup summary:"
  info "- Mode: Advanced (Local clone + git remotes)"
  info "- Local clone path: $repo_dir"
  if [[ -n "$BOOTSTRAP_SELECTED_FORK_REPO" ]]; then
    info "- Fork repository: $BOOTSTRAP_SELECTED_FORK_REPO"
  fi
  if prompt_yes_no "Run setup now?" "Y"; then
    run_setup "$repo_dir" "$@"
  else
    info "Setup not run. Next step:"
    info "  (cd \"$repo_dir\" && ./scripts/bootstrap.sh)"
  fi
}

main "$@"
