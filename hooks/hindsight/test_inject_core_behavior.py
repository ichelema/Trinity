"""Parita' tra inject-core-behavior.sh (lettura flag in puro bash) e
lib/hindsight_config.py, che resta la fonte di verita' della config.

Per ogni caso costruisce un plugin finto in una tempdir (lo script sotto test,
una copia di lib/ e i JSON di config), poi confronta i blocchi RETAIN/RECALL
iniettati dallo script con quello che avrebbe deciso il vecchio hook: blocco
scartato solo se `hindsight_config.py --get <chiave>` stampa "True".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "hooks" / "bin" / "inject-core-behavior.sh"
BASH = shutil.which("bash") or "bash"  # su Windows "bash" nudo sarebbe WSL

CORE = """intro
<!-- OS:windows -->
solo-windows
<!-- /OS:windows -->
<!-- OS:linux -->
solo-linux
<!-- /OS:linux -->
<!-- RECALL:manual --> <!-- commento -->
corpo-recall
<!-- /RECALL:manual -->
<!-- RETAIN:manual --> <!-- commento -->
corpo-retain
<!-- /RETAIN:manual -->
fine
"""

ENV_KEYS = ("CLAUDE_PROJECT_DIR", "HS_CONFIG_FILE", "HS_CFG_RETAIN_ENABLED", "HS_CFG_RECALL_ENABLED")


class InjectCoreBehaviorParity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "plugin"
        (self.root / "hooks" / "bin").mkdir(parents=True)
        shutil.copy(SCRIPT, self.root / "hooks" / "bin" / "inject-core-behavior.sh")
        shutil.copytree(REPO / "hooks" / "hindsight" / "lib", self.root / "hooks" / "hindsight" / "lib")
        (self.root / "core-behavior.md").write_text(CORE, encoding="utf-8", newline="\n")
        self.project = self.tmp / "project"
        self.project.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, path: Path, data):
        text = data if isinstance(data, str) else json.dumps(data, indent=2)
        path.write_text(text, encoding="utf-8", newline="\n")

    def _env(self, extra: dict) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
        env.update(extra)
        return env

    def _python_drops(self, env: dict) -> dict:
        cfg_py = self.root / "hooks" / "hindsight" / "lib" / "hindsight_config.py"
        out = {}
        for key in ("retain_enabled", "recall_enabled"):
            r = subprocess.run([sys.executable, str(cfg_py), "--get", key], env=env,
                               capture_output=True, text=True, timeout=60)
            out[key] = r.stdout.strip() == "True"
        return out

    def _bash(self, env: dict) -> str:
        r = subprocess.run([BASH, (self.root / "hooks" / "bin" / "inject-core-behavior.sh").as_posix()],
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def _check(self, plugin, project=None, extra=None):
        """Confronta lo script con hindsight_config.py; ritorna i drop attesi."""
        if plugin is not None:
            self._write(self.root / "hindsight.config.json", plugin)
        if project is not None:
            self._write(self.project / "hindsight.config.json", project)
        env = self._env({"CLAUDE_PROJECT_DIR": str(self.project), **(extra or {})})
        expected = self._python_drops(env)
        out = self._bash(env)
        self.assertEqual("corpo-retain" not in out, expected["retain_enabled"], out)
        self.assertEqual("corpo-recall" not in out, expected["recall_enabled"], out)
        self.assertNotIn("RETAIN:manual", out)
        self.assertNotIn("RECALL:manual", out)
        self.assertTrue(out.startswith("intro\n") and out.endswith("fine\n"), out)
        return expected

    def test_both_false_keeps_blocks(self):
        exp = self._check({"recall_enabled": False, "retain_enabled": False})
        self.assertEqual(exp, {"retain_enabled": False, "recall_enabled": False})

    def test_both_true_drops_blocks(self):
        exp = self._check({"recall_enabled": True, "retain_enabled": True})
        self.assertEqual(exp, {"retain_enabled": True, "recall_enabled": True})

    def test_missing_keys_use_default_true(self):
        self._check({"debug_log_enabled": True})

    def test_missing_plugin_file_uses_default_true(self):
        self._check(None)

    def test_project_overrides_plugin(self):
        self._check({"recall_enabled": False, "retain_enabled": False}, {"retain_enabled": True})

    def test_project_null_is_ignored(self):
        self._check({"recall_enabled": False, "retain_enabled": True}, {"retain_enabled": None, "recall_enabled": None})

    def test_project_non_bool_keeps_block(self):
        self._check({"recall_enabled": True, "retain_enabled": True}, {"retain_enabled": "yes", "recall_enabled": 1})

    def test_env_overrides_files(self):
        self._check({"recall_enabled": False, "retain_enabled": True}, None,
                    {"HS_CFG_RECALL_ENABLED": "1", "HS_CFG_RETAIN_ENABLED": "NO"})

    def test_env_invalid_is_ignored(self):
        self._check({"recall_enabled": False, "retain_enabled": True}, None,
                    {"HS_CFG_RECALL_ENABLED": "si", "HS_CFG_RETAIN_ENABLED": "off"})

    def test_forced_file_skips_plugin_and_project(self):
        forced = self.tmp / "forced.json"
        self._write(forced, {"recall_enabled": True, "retain_enabled": False})
        self._check({"recall_enabled": False, "retain_enabled": True}, {"recall_enabled": False},
                    {"HS_CONFIG_FILE": str(forced)})

    def test_minified_json_on_one_line(self):
        self._check('{"recall_enabled":true,"retain_enabled":false}')

    def test_os_blocks(self):
        self._write(self.root / "hindsight.config.json", {"recall_enabled": False, "retain_enabled": False})
        out = self._bash(self._env({}))
        keep, drop = ("solo-windows", "solo-linux") if sys.platform == "win32" else ("solo-linux", "solo-windows")
        self.assertIn(keep, out)
        self.assertNotIn(drop, out)
        self.assertNotIn("<!-- OS:", out)


if __name__ == "__main__":
    unittest.main()
