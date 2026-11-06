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
    def model_api(self, version):
        package = "_fazenda_security_model_test"
        parent = types.ModuleType(package)
        parent.__path__ = [str(ROOT)]
        torch = types.ModuleType("torch")
        torch.__path__ = []
        torch.__version__ = version
        torch.load = Mock(return_value={"parameter": "tensor-adapter"})
        nn = types.ModuleType("torch.nn")
        nn.Module = type("Module", (), {})
        torch.nn = nn
        vision = types.ModuleType("torchvision")
        vision.transforms = object()
        pillow = types.ModuleType("PIL")
        pillow.Image = object()
        modules = {package: parent, "torch": torch, "torch.nn": nn,
                   "torchvision": vision, "PIL": pillow, "numpy": types.ModuleType("numpy")}
        spec = importlib.util.spec_from_file_location(package + ".fazenda_model", ROOT / "fazenda_model.py")
        model = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(model)
        network = Mock()
        model.LeNet = Mock(return_value=network)
        loader = model.FazendaModel.__new__(model.FazendaModel)
        loader.device, loader.class_labels = "cpu", ["AA", "CF", "OP"]
        return model, torch, network, loader

    def test_actual_model_loader_has_no_version_block_on_2_5_or_2_10(self):
        for version in ("2.5.0+cpu", "2.10.0+cpu"):
            with self.subTest(version=version):
                model, torch, network, loader = self.model_api(version)
                with patch.object(model.os.path, "exists", return_value=True):
                    self.assertIs(loader.load_model("own_weights.pth"), network)
                torch.load.assert_called_once_with("own_weights.pth", map_location="cpu", weights_only=True)
                network.load_state_dict.assert_called_once_with(torch.load.return_value)
                network.to.assert_called_once_with("cpu")
                network.eval.assert_called_once_with()

    def test_failed_load_is_not_retried_with_unsafe_flags(self):
        model, torch, network, loader = self.model_api("2.10.0+cpu")
        torch.load.side_effect = ValueError("Invalid checkpoint")
        with patch.object(model.os.path, "exists", return_value=True), self.assertRaises(ValueError):
            loader.load_model("own_weights.pth")
        torch.load.assert_called_once_with("own_weights.pth", map_location="cpu", weights_only=True)
        network.load_state_dict.assert_not_called()

    def test_missing_checkpoint_does_not_call_torch_load(self):
        model, torch, network, loader = self.model_api("2.10.0+cpu")
        with patch.object(model.os.path, "exists", return_value=False), self.assertRaises(FileNotFoundError):
            loader.load_model("missing_weights.pth")
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
