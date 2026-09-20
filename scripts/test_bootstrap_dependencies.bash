#!/usr/bin/env bash
# Offline tests for bootstrap_dependencies.bash. Requires --fixture PATH to an
# already-imported local checkout; never contacts a remote repository.
set -euo pipefail
fixture=''
while (($#)); do
  case "$1" in
    --fixture) (($# >= 2)) || { echo 'missing --fixture path' >&2; exit 2; }; fixture=$2; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$fixture" && -d "$fixture/.git" ]] || { echo 'use --fixture with a local dependency checkout' >&2; exit 2; }
helper="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/bootstrap_dependencies.bash"
patch="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../patches/unitree_go2_ros2" && pwd)/0001-fix-unitree-application-dependency.patch"
root=$(mktemp -d "${TMPDIR:-/tmp}/bootstrap-offline.XXXXXX")
trap 'rm -rf -- "$root"' EXIT
clone() { local name=$1; mkdir -p "$root/$name/src"; git clone --quiet --no-hardlinks "$fixture" "$root/$name/src/unitree_go2_ros2"; git -C "$root/$name/src/unitree_go2_ros2" remote set-url origin https://github.com/khaledgabr77/unitree_go2_ros2.git; git -C "$root/$name/src/unitree_go2_ros2" apply "$patch"; }
run_expect() { local expected=$1; shift; set +e; "$@" >/dev/null 2>&1; local actual=$?; set -e; [[ "$actual" == "$expected" ]] || { echo "expected $expected, got $actual: $*" >&2; exit 1; }; }
clone success
[[ ! -e "$root/success/install" ]]
output=$("$helper" --workspace "$root/success" --verify-source-only)
[[ "$output" == *'Source-only verification passed'* ]]
[[ "$output" == *'unitree_go2_sim: source discoverable'* ]]
[[ "$output" == *'champ_msgs: source discoverable'* ]]
[[ ! -e "$root/success/install" ]]
echo 'PASS source-only success and package inventory'
run_expect 1 "$helper" --workspace "$root/missing" --verify-source-only
[[ ! -e "$root/missing" ]]
echo 'PASS missing repository'
clone wrong
( cd "$root/wrong/src/unitree_go2_ros2" && git reset --quiet --hard HEAD^ )
run_expect 1 "$helper" --workspace "$root/wrong" --verify-source-only
echo 'PASS wrong revision'
clone modified
printf '\n<!-- unrelated offline test edit -->\n' >> "$root/modified/src/unitree_go2_ros2/unitree_go2_sim/package.xml"
run_expect 1 "$helper" --workspace "$root/modified" --verify-source-only
echo 'PASS unexpected modification'
clone unpatched
( cd "$root/unpatched/src/unitree_go2_ros2" && git apply --reverse "$patch" )
run_expect 1 "$helper" --workspace "$root/unpatched" --verify-source-only
echo 'PASS unapplied patch'
clone full
run_expect 1 "$helper" --workspace "$root/full" --verify-only
[[ ! -e "$root/full/install" ]]
echo 'PASS full verify-only still requires install discovery'
