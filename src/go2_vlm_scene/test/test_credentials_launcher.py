"""Credential launcher regression tests use dummy values only."""
import os
from pathlib import Path
import subprocess

import pytest

WRAPPER = Path(__file__).resolve().parents[3] / "scripts/jazzy_vlm_exec.bash"
CHECK = "import os; assert os.environ.get('OPENAI_API_KEY') == 'dummy-openai'; assert os.environ.get('GEMINI_API_KEY') == 'dummy-gemini'; assert os.environ['ROS_DISTRO'] == 'jazzy'; assert os.environ['ROS_DOMAIN_ID'] == '42'; assert 'UNRELATED_SETTING' not in os.environ"


def run_launcher(tmp_path, mode=None, traced=False):
    env = dict(os.environ, HOME=str(tmp_path), USER=os.environ['USER'],
               OPENAI_API_KEY='dummy-openai', GEMINI_API_KEY='dummy-gemini',
               UNRELATED_SETTING='discard-me')
    if mode is not None:
        target = tmp_path / '.config/go2_vlm/credentials.env'
        target.parent.mkdir(parents=True)
        target.write_text('OPENAI_API_KEY=dummy-openai\nGEMINI_API_KEY=dummy-gemini\n')
        target.chmod(mode)
        env['OPENAI_API_KEY'] = env['GEMINI_API_KEY'] = 'overridden'
    args = (['bash', '-xv'] if traced else []) + [str(WRAPPER), '/usr/bin/python3', '-c', CHECK]
    result = subprocess.run(args, env=env, capture_output=True, text=True)
    # Never include captured output in assertion diagnostics.
    assert 'dummy-openai' not in result.stdout + result.stderr
    assert 'dummy-gemini' not in result.stdout + result.stderr
    return result.returncode


@pytest.mark.parametrize('mode', [None, 0o600, 0o400])
def test_credentials_and_isolation(tmp_path, mode):
    assert run_launcher(tmp_path, mode) == 0


@pytest.mark.parametrize('mode', [0o640, 0o604, 0o660, 0o606, 0o644, 0o700])
def test_reject_insecure_permissions(tmp_path, mode):
    assert run_launcher(tmp_path, mode) != 0


def test_tracing_does_not_expose_keys(tmp_path):
    assert run_launcher(tmp_path, 0o600, traced=True) == 0
