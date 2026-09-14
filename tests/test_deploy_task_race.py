# -*- coding: utf-8 -*-
"""Deploy task-restart-race tests + mock dry-run."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PRODUCTION_FILES = [
    "app.py",
    "config.py",
    "wsgi.py",
    "services/repository.py",
    "static/js/app.js",
    "scripts/production/NexGen-ProcessControl.ps1",
    "scripts/production/Stop-NexGen-2333.ps1",
]


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest().upper()


def _build_v3_package(target_dir):
    for rel in PRODUCTION_FILES:
        dst = os.path.join(target_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel.replace("/", os.sep)), dst)
    shutil.copy2(
        os.path.join(ROOT, "scripts", "deploy", "Deploy-NexGen-KG-Fix.ps1"),
        os.path.join(target_dir, "Deploy-NexGen-KG-Fix.ps1"),
    )
    shutil.copy2(
        os.path.join(ROOT, "scripts", "deploy", "ROLLBACK.txt"),
        os.path.join(target_dir, "ROLLBACK.txt"),
    )
    entries = []
    for rel in PRODUCTION_FILES:
        path = os.path.join(target_dir, rel.replace("/", os.sep))
        entries.append({"path": rel.replace("\\", "/"), "sha256": _sha256(path)})
    deploy_path = os.path.join(target_dir, "Deploy-NexGen-KG-Fix.ps1")
    manifest = {
        "version": "3.0.3-kg-save",
        "package_revision": "V3-complete-task-race-fix",
        "git_commit": "mock-test",
        "production_files_count": 7,
        "deploy_helper_files_count": 3,
        "total_files_count": 10,
        "files": entries,
        "deploy_script": {"path": "Deploy-NexGen-KG-Fix.ps1", "sha256": _sha256(deploy_path)},
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

    def test_v3_package_inventory(self):
        pkg = tempfile.mkdtemp(prefix="nexgen-v3-inventory-")
        try:
            _build_v3_package(pkg)
            expected = {
                "app.py",
                "config.py",
                "wsgi.py",
                os.path.join("services", "repository.py"),
                os.path.join("static", "js", "app.js"),
                os.path.join("scripts", "production", "NexGen-ProcessControl.ps1"),
                os.path.join("scripts", "production", "Stop-NexGen-2333.ps1"),
                "manifest.json",
                "Deploy-NexGen-KG-Fix.ps1",
                "ROLLBACK.txt",
            }
            found = set()
            for dirpath, _, filenames in os.walk(pkg):
                for name in filenames:
                    rel = os.path.relpath(os.path.join(dirpath, name), pkg)
                    found.add(rel.replace("\\", "/").replace("/", os.sep))
            self.assertEqual(len(found), 10)
            for item in expected:
                self.assertIn(item.replace("/", os.sep), found)
            with open(os.path.join(pkg, "manifest.json"), encoding="utf-8") as f:
                manifest = json.load(f)
            self.assertEqual(manifest["production_files_count"], 7)
            self.assertEqual(len(manifest["files"]), 7)
        finally:
            shutil.rmtree(pkg, ignore_errors=True)

    def test_mock_deploy_dry_run(self):
        mock = tempfile.mkdtemp(prefix="nexgen-mock-deploy-")
        pkg = tempfile.mkdtemp(prefix="nexgen-pkg-flat-")
        try:
            for sub in ("data", "services", "static/js", "scripts/production", "backup"):
                os.makedirs(os.path.join(mock, sub.replace("/", os.sep)), exist_ok=True)
            shutil.copy2(
                os.path.join(ROOT, "scripts", "sqlite_online_backup.py"),
                os.path.join(mock, "scripts", "sqlite_online_backup.py"),
            )
            for rel in PRODUCTION_FILES:
                dst = os.path.join(mock, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(os.path.join(ROOT, rel.replace("/", os.sep)), dst)
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

            _build_v3_package(pkg)
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
            self.assertIn("scripts/production/NexGen-ProcessControl.ps1", r.stdout)
        finally:
            shutil.rmtree(mock, ignore_errors=True)
            shutil.rmtree(pkg, ignore_errors=True)

    def test_validate_only_v3(self):
        pkg = tempfile.mkdtemp(prefix="nexgen-v3-validate-")
        try:
            _build_v3_package(pkg)
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    os.path.join(pkg, "Deploy-NexGen-KG-Fix.ps1"),
                    "-ValidateOnly",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("PACKAGE_VALIDATE_PASS", r.stdout)
        finally:
            shutil.rmtree(pkg, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
