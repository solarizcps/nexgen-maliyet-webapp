# -*- coding: utf-8 -*-
"""Deploy task-restart-race tests + mock dry-run."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build_flat_package(target_dir):
    files = [
        "app.py",
        "config.py",
        "wsgi.py",
        "services/repository.py",
        "static/js/app.js",
    ]
    for rel in files:
        dst = os.path.join(target_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel.replace("/", os.sep)), dst)
    with open(
        os.path.join(ROOT, "scripts", "production", "NexGen-ProcessControl.ps1"),
        encoding="utf-8",
    ) as f:
        pc = f.read()
    with open(
        os.path.join(ROOT, "scripts", "deploy", "Deploy-NexGen-KG-Fix.ps1"),
        encoding="utf-8",
    ) as f:
        dep = f.read()
    param_m = re.search(r"(?s)(param\s*\(.*?\)\s*)", dep)
    param_block = param_m.group(1) if param_m else ""
    dep_body = re.sub(r"(?s)^#requires[^\n]*\n", "", dep)
    dep_body = re.sub(r"(?s)^param\s*\(.*?\)\s*", "", dep_body, count=1)
    dep_body = re.sub(
        r"\$pcLoaded = \$false.*?if \(-not \$pcLoaded\) \{\s*throw.*?\}\n",
        "",
        dep_body,
        count=1,
        flags=re.DOTALL,
    )
    deploy_path = os.path.join(target_dir, "Deploy-NexGen-KG-Fix.ps1")
    with open(deploy_path, "w", encoding="utf-8") as f:
        f.write("#requires -Version 5.1\n")
        f.write(param_block)
        f.write(pc)
        f.write("\n")
        f.write(dep_body)
    entries = []
    for rel in files:
        path = os.path.join(target_dir, rel.replace("/", os.sep))
        import hashlib

        h = hashlib.sha256(open(path, "rb").read()).hexdigest().upper()
        entries.append({"path": rel.replace("\\", "/"), "sha256": h})
    manifest = {
        "version": "3.0.3-kg-save",
        "git_commit": "mock-test",
        "files": entries,
        "DB_INCLUDED": False,
        "SECRET_INCLUDED": False,
        "CPS_INCLUDED": False,
    }
    with open(os.path.join(target_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


class DeployTaskRaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ps1 = os.path.join(ROOT, "tests", "deploy_task_race_tests.ps1")
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", cls.ps1],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        cls.ps_output = r.stdout + r.stderr
        if r.returncode != 0:
            raise RuntimeError(f"deploy_task_race_tests.ps1 failed:\n{cls.ps_output}")

    def test_powershell_suite_passed(self):
        self.assertIn("DEPLOY_TESTS_FAILED=0", self.ps_output)

    def test_mock_deploy_dry_run(self):
        mock = tempfile.mkdtemp(prefix="nexgen-mock-deploy-")
        pkg = tempfile.mkdtemp(prefix="nexgen-pkg-flat-")
        try:
            for sub in ("data", "services", "static/js", "scripts", "backup"):
                os.makedirs(os.path.join(mock, sub.replace("/", os.sep)), exist_ok=True)
            shutil.copy2(
                os.path.join(ROOT, "scripts", "sqlite_online_backup.py"),
                os.path.join(mock, "scripts", "sqlite_online_backup.py"),
            )
            for rel in (
                "app.py",
                "config.py",
                "wsgi.py",
                "services/repository.py",
                "static/js/app.js",
            ):
                shutil.copy2(
                    os.path.join(ROOT, rel.replace("/", os.sep)),
                    os.path.join(mock, rel.replace("/", os.sep)),
                )
            with open(os.path.join(mock, "data", ".nexgen_secret"), "w", encoding="utf-8") as f:
                f.write("x" * 64)

            sys.path.insert(0, ROOT)
            import config
            from db.connection import init_db
            from services.import_data import import_localstorage

            config.DATA_DIR = os.path.join(mock, "data")
            config.DB_PATH = os.path.join(mock, "data", "nexgen_local.db")
            config.IMPORT_SOURCE = os.path.join(
                ROOT, "tests", "fixtures", "localstorage_seed.json"
            )
            init_db(force=True)
            import_localstorage(force_recreate=False)

            _build_flat_package(pkg)
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    os.path.join(pkg, "Deploy-NexGen-KG-Fix.ps1"),
                    "-TestProductionRoot",
                    mock,
                    "-SkipScheduledTask",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("DEPLOY_PASS", r.stdout)
            self.assertIn('"DEPLOY_RESULT":  "PASS"', r.stdout.replace("'", '"'))
        finally:
            shutil.rmtree(mock, ignore_errors=True)
            shutil.rmtree(pkg, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
