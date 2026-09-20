#!/usr/bin/env bash
# Import the audited external source checkout; never install system packages.
set -euo pipefail
export GIT_OPTIONAL_LOCKS=0
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

usage() {
  cat <<'HELP'
Usage: bootstrap_dependencies.bash --workspace PATH [--apply-patches | --verify-source-only | --verify-only]
       [--allow-project-workspace]

Default: import missing dependencies using vcs import, then verify the source pin.
Existing checkouts are never fetched, reset, or switched automatically.
--apply-patches: explicitly apply the reviewed patch, or detect it already applied.
--verify-only: no network or writes; require pinned/patched source and all six
               ROS packages discoverable from this workspace's installation.
--verify-source-only: no network or writes; verify the pinned/patched source
                      checkout and six package manifests without an install.
--allow-project-workspace: explicitly permit imports inside this project checkout.
The protected reference workspace name is always refused for mutation.
HELP
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
workspace=''
apply_patches=0
verify_only=0
verify_source_only=0
allow_project=0
while (($#)); do
  case "$1" in
    --workspace)
      (($# >= 2)) || die '--workspace needs a path'
      [[ -n "$2" && "$2" != --* ]] || die '--workspace needs a path'
      [[ -z "$workspace" ]] || die '--workspace was specified twice'
      workspace=$2; shift 2 ;;
    --apply-patches) apply_patches=1; shift ;;
    --verify-only) verify_only=1; shift ;;
    --verify-source-only) verify_source_only=1; shift ;;
    --allow-project-workspace) allow_project=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done
[[ -n "$workspace" ]] || die 'An explicit --workspace path is required'
(( !(apply_patches && (verify_only || verify_source_only)) )) || die 'Verification modes cannot be combined with --apply-patches'
(( !(verify_only && verify_source_only) )) || die 'Verification modes cannot be combined'
for command in git realpath python3; do
  command -v "$command" >/dev/null || die "Missing prerequisite: $command"
done
project=$(realpath -- "$(dirname -- "${BASH_SOURCE[0]}")/..")
workspace=$(realpath -m -- "$workspace")
[[ "$workspace" != / ]] || die 'The filesystem root is not a workspace'
[[ "$workspace" != *$'\n'* && "$workspace" != *$'\t'* ]] || die 'Workspace path must not contain tabs or newlines'
manifest="$project/dependencies.repos"
patch="$project/patches/unitree_go2_ros2/0001-fix-unitree-application-dependency.patch"
[[ -f "$patch" ]] || die 'Reviewed patch file is missing'
# Fail on unsupported manifest shapes instead of accidentally importing extra repos.
metadata=$(python3 -B - "$manifest" <<'PY'
import re
import sys
try:
    import yaml
    with open(sys.argv[1], encoding='utf-8') as stream:
        data = yaml.safe_load(stream)
    assert set(data) == {'repositories'}
    assert set(data['repositories']) == {'unitree_go2_ros2'}
    entry = data['repositories']['unitree_go2_ros2']
    assert set(entry) == {'type', 'url', 'version'}
    assert entry['type'] == 'git'
    assert entry['url'] == 'https://github.com/khaledgabr77/unitree_go2_ros2.git'
    assert isinstance(entry['version'], str) and re.fullmatch(r'[0-9a-f]{40}', entry['version'])
    print(entry['url'])
    print(entry['version'])
except Exception:
    sys.exit('Invalid audited dependency manifest or missing PyYAML prerequisite')
PY
) || die 'Could not validate dependencies.repos'
mapfile -t fields <<< "$metadata"
expected_url=${fields[0]}
expected_revision=${fields[1]}
repo="$workspace/src/unitree_go2_ros2"
# Reject path redirection before invoking Git or creating anything.
[[ "$(realpath -m -- "$workspace/src")" == "$workspace/src" ]] || die 'Workspace src must not be a redirected symlink'
[[ "$(realpath -m -- "$repo")" == "$repo" ]] || die 'Dependency path must not be a redirected symlink'
if (( !verify_only && !verify_source_only )); then
  case "$workspace/" in
    */go2_jazzy_ws/*) die 'Refusing to modify the protected reference workspace' ;;
  esac
  if [[ "$workspace" == "$project" || "$workspace" == "$project/"* ]]; then
    (( allow_project )) || die 'Import inside the project requires --allow-project-workspace'
  fi
fi
packages=(unitree_go2_sim unitree_go2_description unitree_application champ champ_base champ_msgs)
failed=0
printf 'Workspace: %s\nRepository: unitree_go2_ros2\nExpected revision: %s\n' "$workspace" "$expected_revision"
if [[ ! -e "$repo" ]]; then
  if (( verify_only || verify_source_only )); then
    printf 'Repository: MISSING\nActual revision: unavailable\nPatch: NOT APPLIED (repository missing)\n'
    failed=1
  else
    command -v vcs >/dev/null || die 'Missing prerequisite: vcs (vcstool)'
    mkdir -p -- "$workspace/src"
    vcs import "$workspace/src" < "$manifest"
  fi
fi
source_ok=0
if [[ -e "$repo" ]]; then
  [[ -d "$repo/.git" && ! -L "$repo/.git" ]] || die 'Expected an independent Git checkout, not a linked worktree'
  [[ "$(git -C "$repo" rev-parse --show-toplevel)" == "$repo" ]] || die 'Dependency Git root does not match its expected path'
  [[ "$(realpath -- "$(git -C "$repo" rev-parse --absolute-git-dir)")" == "$repo/.git" ]] || die 'Dependency Git directory is redirected'
  actual=$(git -C "$repo" rev-parse HEAD)
  printf 'Repository: PRESENT\nActual revision: %s\n' "$actual"
  origin=$(git -C "$repo" remote get-url origin) || die 'Dependency has no origin remote'
  [[ "$origin" == "$expected_url" ]] || die 'Dependency origin differs from the audited URL'
  if [[ "$actual" != "$expected_revision" ]]; then
    printf 'Patch: NOT CHECKED (unexpected revision)\n' >&2
    (( verify_only || verify_source_only )) || die 'Refusing to patch an unexpected revision'
    failed=1
  else
    [[ -z "$(git -C "$repo" ls-files -v | sed -n '/^[a-zS]/p')" ]] || die 'Dependency has hidden index flags (assume-unchanged or skip-worktree)'
    git -C "$repo" diff --cached --quiet || die 'Dependency has staged changes'
    [[ -z "$(git -C "$repo" ls-files --others --exclude-standard)" ]] || die 'Dependency has unrelated untracked files'
    # Exact diff comparison rejects unrelated edits, including changes in the same file.
    actual_diff=$(git -C "$repo" -c color.ui=false diff --no-ext-diff --no-textconv --binary --src-prefix=a/ --dst-prefix=b/ HEAD --)
    expected_diff=$(cat -- "$patch")
    if [[ -z "$actual_diff" ]]; then
      git -C "$repo" apply --check "$patch" || die 'Reviewed patch does not apply cleanly'
      if (( apply_patches )); then
        git -C "$repo" apply "$patch"
        printf 'Patch: APPLIED\n'
      else
        printf 'Patch: NOT APPLIED (use --apply-patches)\n'
        if (( verify_only || verify_source_only )); then failed=1; fi
      fi
      source_ok=1
    elif [[ "$actual_diff" == "$expected_diff" ]]; then
      git -C "$repo" apply --reverse --check "$patch" || die 'Patch state could not be verified'
      printf 'Patch: ALREADY APPLIED\n'
      source_ok=1
    else
      die 'Dependency changes do not match the reviewed patch; leaving them untouched'
    fi
    if (( apply_patches )); then
      [[ "$(git -C "$repo" -c color.ui=false diff --no-ext-diff --no-textconv --binary --src-prefix=a/ --dst-prefix=b/ HEAD --)" == "$expected_diff" ]] || die 'Post-patch diff verification failed'
    fi
  fi
fi
IFS=: read -r -a prefixes <<< "${AMENT_PREFIX_PATH:-}"
for package in "${packages[@]}"; do
  if [[ -f "$repo/$package/package.xml" ]] && python3 -B - "$repo/$package/package.xml" "$package" <<'PY'
import sys
import xml.etree.ElementTree as ET
try:
    sys.exit(0 if ET.parse(sys.argv[1]).findtext('name') == sys.argv[2] else 1)
except (OSError, ET.ParseError):
    sys.exit(1)
PY
  then
    printf '%s: source discoverable; ' "$package"
  else
    printf '%s: source NOT discoverable; ' "$package"
    failed=1
  fi
  found=''
  for prefix in "${prefixes[@]}"; do
    [[ -n "$prefix" ]] || continue
    if [[ -f "$prefix/share/ament_index/resource_index/packages/$package" ]]; then
      found=$(realpath -m -- "$prefix")
      break
    fi
  done
  if (( verify_source_only )); then
    printf 'source-only verification: installed ROS environment not required\n'
  elif [[ -z "$found" ]]; then
    printf 'ROS environment NOT discoverable\n'
    if (( verify_only )); then failed=1; fi
  elif [[ "$found" == "$workspace/install" || "$found" == "$workspace/install/"* ]]; then
    printf 'ROS environment discoverable: %s\n' "$found"
  else
    printf 'ROS environment discoverable from ANOTHER workspace: %s\n' "$found"
    if (( verify_only )); then failed=1; fi
  fi
done
if (( verify_only || verify_source_only )); then
  (( source_ok && !failed )) || exit 1
  if (( verify_source_only )); then
    printf 'Source-only verification passed; no files changed.\n'
  else
    printf 'Verification passed; no files changed.\n'
  fi
else
  (( source_ok && !failed )) || die 'Source verification failed'
  printf 'Source checkout verified. Build and source the selected workspace, then run --verify-only.\n'
fi
