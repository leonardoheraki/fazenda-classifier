"""Security boundaries without importing an installed PyTorch or opening weights."""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("_fazenda_runtime_test", ROOT / "runtime.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class RuntimeSecurityTests(unittest.TestCase):
    def test_affected_releases_are_blocked(self):
        for version in ("2.2.0", "2.5.0+cpu", "2.9.1", "2.9.9"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "bloqueada"):
                runtime.require_supported_torch(version)

    def test_stable_fixed_versions_and_cpu_builds_are_accepted(self):
        for version in ("2.10.0", "2.10.0+cpu", "2.10.1", "2.10.0.post1", "2.11.0+cu130"):
            with self.subTest(version=version):
                runtime.require_supported_torch(version)

    def test_preview_unknown_or_malformed_versions_fail_closed(self):
        for version in ("2.10.0rc1", "2.10.0a0+cpu", "2.11.0.dev20261103", "unknown", "2.10", None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                runtime.require_supported_torch(version)

    def test_actual_model_module_blocks_old_torch_before_loading_weights_or_torchvision(self):
        package = "_fazenda_security_model_test"
        parent = types.ModuleType(package)
        parent.__path__ = [str(ROOT)]
        torch = types.ModuleType("torch")
        torch.__version__ = "2.5.0+cpu"
        torch.load = Mock(side_effect=RuntimeError("A model must never be opened"))
        modules = {package: parent, package + ".runtime": runtime, "torch": torch}
        spec = importlib.util.spec_from_file_location(package + ".fazenda_model", ROOT / "fazenda_model.py")
        model = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules), self.assertRaises(runtime.RuntimeCompatibilityError):
            spec.loader.exec_module(model)
        torch.load.assert_not_called()

    def test_ua_never_selects_or_deletes_a_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runtime.tempfile, "tempdir", folder):
            sentinel = Path(folder) / "previous_results.txt"
            sentinel.write_text("keep")
            first = Path(runtime.create_species_workspace("CG_001"))
            second = Path(runtime.create_species_workspace("CG_001"))
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, Path(folder))
            self.assertEqual(second.parent, Path(folder))
            self.assertNotIn("CG_001", first.name)
            self.assertEqual(sentinel.read_text(), "keep")

    def test_paths_controls_and_empty_ua_cannot_create_a_workspace(self):
        with patch.object(runtime.tempfile, "mkdtemp") as create:
            for value in ("../other", "..\\other", "C:\\data", "/data", "\\\\server\\share", "", "bad\nua", None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    runtime.create_species_workspace(value)
            create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
