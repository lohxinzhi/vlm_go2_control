#!/usr/bin/env bash
# Disable tracing before loading credentials, including when invoked with -x/-v.
set +x +v
credentials_file="$HOME/.config/go2_vlm/credentials.env"
if [[ -e "$credentials_file" || -L "$credentials_file" ]]; then
    # Check the opened file, avoiding a pathname replacement between check/use.
    if ! { exec {credentials_fd}<"$credentials_file"; } 2>/dev/null; then
        printf '%s\n' 'Cannot open local VLM credentials.' >&2
        exit 1
    fi
    if ! /usr/bin/python3 -I -c '
import os, stat, sys
info = os.fstat(int(sys.argv[1]))
sys.exit(0 if stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
         and stat.S_IMODE(info.st_mode) & ~0o600 == 0 else 1)
' "$credentials_fd"; then
        printf '%s\n' 'Local VLM credentials must be owned by you with permissions 600 or stricter.' >&2
        exit 1
    fi
    # Trusted shell assignments; suppress diagnostics that could include values.
    set -a
    if ! source "/proc/self/fd/$credentials_fd" >/dev/null 2>&1; then
        set +x +v
        printf '%s\n' 'Cannot load local VLM credentials.' >&2
        exit 1
    fi
    set +x +v
    set +a
    exec {credentials_fd}<&-
fi
unset credentials_file credentials_fd
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Task 3: keep the Jazzy allowlist plus VLM settings, without secrets in argv.
exec /usr/bin/python3 -I -c '
import os
import sys

script_dir = os.path.realpath(sys.argv[1])
ws = os.path.realpath(os.environ.get("GO2_WORKSPACE") or os.path.join(script_dir, ".."))
env = {
    "HOME": os.environ["HOME"],
    "USER": os.environ["USER"],
    "LOGNAME": os.environ["USER"],
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG": "C.UTF-8",
    "DISPLAY": os.environ.get("DISPLAY", ""),
    "XAUTHORITY": os.environ.get("XAUTHORITY", ""),
    "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}",
    "GO2_CLEAN_ENV": "1",
    "GO2_WORKSPACE": ws,
}
for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "DASHSCOPE_API_KEY", "QWEN_BASE_URL"):
    if name in os.environ:
        env[name] = os.environ[name]
wrapper = os.path.join(script_dir, "jazzy_exec.bash")
os.execve(wrapper, [wrapper, *sys.argv[2:]], env)
' "$SCRIPT_DIR" "$@"
