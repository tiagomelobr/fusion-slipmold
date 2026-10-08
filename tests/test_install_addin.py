"""tools/install_addin.py: ownership rules, copy mode and junction mode (temporary folders only)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import install_addin as IA  # noqa: E402


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.src = os.path.join(root, "repo", "addin", "SlipMold")
        os.makedirs(self.src)
        with open(os.path.join(self.src, IA.MANIFEST), "w", encoding="utf-8") as fh:
            json.dump({"id": "test-id"}, fh)
        with open(os.path.join(self.src, "SlipMold.py"), "w", encoding="utf-8") as fh:
            fh.write("# add-in\n")
        self.target = os.path.join(root, "AddIns", "SlipMold")

    def tearDown(self):
        self.tmp.cleanup()

    def test_copy_install_reinstall_uninstall(self):
        msg = IA.install(self.target, copy=True, source=self.src, repo="R")
        self.assertIn("copied", msg)
        self.assertEqual(IA.ownership(self.target, self.src), "own-copy")
        with open(os.path.join(self.target, IA.CONFIG), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["repo"], "R")
        IA.install(self.target, copy=True, source=self.src, repo="R2")  # replaces our own copy
        with open(os.path.join(self.target, IA.CONFIG), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["repo"], "R2")
        self.assertIn("removed", IA.uninstall(self.target, source=self.src))
        self.assertFalse(os.path.exists(self.target))
        self.assertTrue(os.path.isfile(os.path.join(self.src, "SlipMold.py")))

    def test_foreign_folder_is_never_touched(self):
        os.makedirs(self.target)
        keep = os.path.join(self.target, "user.py")
        with open(keep, "w", encoding="utf-8") as fh:
            fh.write("x")
        self.assertEqual(IA.ownership(self.target, self.src), "foreign")
        with self.assertRaises(RuntimeError):
            IA.install(self.target, source=self.src)
        with self.assertRaises(RuntimeError):
            IA.uninstall(self.target, source=self.src)
        self.assertTrue(os.path.isfile(keep))

    def test_dry_run_changes_nothing(self):
        self.assertIn("would", IA.install(self.target, dry_run=True, source=self.src))
        self.assertFalse(os.path.lexists(self.target))

    @unittest.skipUnless(os.name == "nt", "directory junctions are Windows-only")
    def test_junction_install_and_uninstall_keeps_source(self):
        msg = IA.install(self.target, source=self.src)
        self.assertIn("linked", msg)
        self.assertEqual(IA.ownership(self.target, self.src), "ours-link")
        self.assertTrue(os.path.isfile(os.path.join(self.target, "SlipMold.py")))
        self.assertIn("already linked", IA.install(self.target, source=self.src))
        IA.uninstall(self.target, source=self.src)
        self.assertFalse(os.path.lexists(self.target))
        self.assertTrue(os.path.isfile(os.path.join(self.src, "SlipMold.py")))


class AddinLoaderTest(unittest.TestCase):
    """SlipMold.py imports with adsk stubbed and finds this repository from its own folder."""

    def test_repo_root_from_addin_folder(self):
        import importlib.util
        import types

        for name in ("adsk", "adsk.core", "adsk.fusion"):
            sys.modules.setdefault(name, types.ModuleType(name))
        core = sys.modules["adsk.core"]
        if not hasattr(sys.modules["adsk"], "core"):
            sys.modules["adsk"].core = core
        for cls in ("CommandEventHandler", "CommandCreatedEventHandler", "CustomEventHandler", "HTMLEventHandler"):
            if not hasattr(core, cls):
                setattr(core, cls, type(cls, (), {"__init__": lambda self: None}))
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(repo, "addin", "SlipMold", "SlipMold.py")
        spec = importlib.util.spec_from_file_location("slipmold_addin_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(os.path.normcase(mod.repo_root()), os.path.normcase(repo))
        self.assertEqual(os.path.normcase(mod.code_dir()), os.path.normcase(os.path.dirname(path)))
        cmds = mod.impl()
        self.assertEqual(set(cmds.BUILD), {c[0] for c in mod.COMMANDS})


if __name__ == "__main__":
    unittest.main()
