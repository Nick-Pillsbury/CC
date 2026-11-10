"""Check deployment scope and failure handling without running Docker."""

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from deploy import deploy, find_compose
from offline_test import docker_command


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(redirect_stdout(StringIO()))
        self.folder = self.enterContext(TemporaryDirectory())
        self.project = Path(self.folder).resolve()
        self.source = self.project / "master-container"
        self.source.mkdir()
        (self.source / "compose.server.yaml").touch()
        self.compose = self.project / "docker-compose.yml"
        self.compose.touch()
        self.config = subprocess.CompletedProcess([], 0, stdout=json.dumps({
            "services": {"master-api": {
                "image": "master-api-image:latest", "build": {"context": str(self.source)},
            }},
        }))

    def test_finds_pi_compose_filename(self):
        self.assertEqual(self.compose, find_compose(self.project))

    def test_deploy_tests_before_restarting_only_master(self):
        with patch("deploy.subprocess.run", return_value=self.config) as run:
            deploy(self.source, self.compose)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(5, len(commands))
        for command in (commands[0], commands[1], commands[3], commands[4]):
            self.assertEqual(["docker", "compose", "-f", str(self.compose), "-f",
                              str(self.source / "compose.server.yaml")], command[:6])
        self.assertEqual(["build", "master-api"], commands[1][6:])
        self.assertEqual(docker_command(self.source, "master-api-image:latest"), commands[2])
        self.assertEqual("none", commands[2][commands[2].index("--network") + 1])
        self.assertIn("--no-deps", commands[3])
        self.assertEqual("master-api", commands[3][-1])
        self.assertIn("/api/v1/telemetry", commands[4][-1])

    def test_failed_offline_tests_do_not_restart_master(self):
        with patch("deploy.subprocess.run", side_effect=[
            self.config, subprocess.CompletedProcess([], 0),
            subprocess.CalledProcessError(1, ["docker", "run"]),
        ]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                deploy(self.source, self.compose)
        self.assertEqual(3, run.call_count)

    def test_wrong_build_folder_prevents_deployment(self):
        body = json.loads(self.config.stdout)
        body["services"]["master-api"]["build"]["context"] = str(self.project / "other")
        self.config.stdout = json.dumps(body)
        with patch("deploy.subprocess.run", return_value=self.config) as run:
            with self.assertRaisesRegex(ValueError, "build context"):
                deploy(self.source, self.compose)
        self.assertEqual(1, run.call_count)
