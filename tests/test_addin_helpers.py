"""SlipMold add-in: the dialog-independent helpers, the icon writer and the installer's user config."""
import json
import os
import re
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "addin", "SlipMold"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import install_addin as IA  # noqa: E402
import make_icons as MI  # noqa: E402
import slipmold_helpers as H  # noqa: E402


class StageTest(unittest.TestCase):
    ORDER = ["s0_intake", "s1_params", "s4_plaster"]

    def test_stage_choice(self):
        self.assertEqual(H.stage_choice("4", self.ORDER), "s4_plaster")
        self.assertEqual(H.stage_choice("S4", self.ORDER), "s4_plaster")
        self.assertEqual(H.stage_choice("s4_plaster", self.ORDER), "s4_plaster")
        self.assertIsNone(H.stage_choice("s9", self.ORDER))

    def test_label_round_trip(self):
        self.assertEqual(H.label_stage(H.stage_label("s4_plaster")), "s4_plaster")
        self.assertEqual(H.label_stage(H.stage_label("odd")), "odd")

    def test_parse_args_json(self):
        self.assertEqual(H.parse_args_json(""), ({}, None))
        self.assertEqual(H.parse_args_json('{"maxSeconds": 6}'), ({"maxSeconds": 6}, None))
        self.assertIn("not valid JSON", H.parse_args_json("{x")[1])
        self.assertIn("JSON object", H.parse_args_json("[1]")[1])


class PrinterTest(unittest.TestCase):
    """Make mold dialog: Nozzle diameter and Fit offset (config "printer")."""

    def test_prompt_defaults_and_confirmed(self):
        pp = H.printer_prompt({})
        self.assertEqual((pp["nozzle"], pp["fitOffset"], pp["confirmed"], pp["notes"]), (0.4, 0.0, False, []))
        self.assertEqual([lab for lab, on in pp["choices"] if on], ["0.4 mm"])
        self.assertEqual(len(pp["choices"]), len(H.NOZZLE_CHOICES))
        self.assertIn("Pick the nozzle", H.printer_lines(pp)[0])
        pp = H.printer_prompt({"printer": {"nozzle": 0.6, "fitOffset": 0.05, "bedX": 220}})
        self.assertEqual((pp["nozzle"], pp["fitOffset"], pp["confirmed"]), (0.6, 0.05, True))
        self.assertTrue(H.printer_lines(pp)[0].startswith("Fit offset:"))
        self.assertTrue(H.printer_prompt({"printer": {"bedX": 220}})["confirmed"] is False)

    def test_prompt_adds_an_odd_nozzle_and_notes_overrides(self):
        pp = H.printer_prompt({"printer": {"nozzle": 0.45}}, H.printer_overrides({"mold_nozzle": "0.6 mm",
                                                                                   "mold_plasterWall": "25 mm"}))
        self.assertIn(("0.45 mm", True), pp["choices"])
        self.assertEqual(len(pp["notes"]), 1)
        self.assertIn("mold_nozzle = 0.6 mm", pp["notes"][0])
        self.assertIn(pp["notes"][0], H.printer_lines(pp))
        pp = H.printer_prompt({}, {"fitOffset": 0.1})
        self.assertIn("mold_fitOffset = 0.1 mm", pp["notes"][0])

    def test_parse_inputs(self):
        self.assertEqual(H.parse_printer_inputs("0.4 mm", "0"), ({"nozzle": 0.4, "fitOffset": 0.0}, None))
        for text, val in (("0.05", 0.05), ("0.05 mm", 0.05), ("+0.05", 0.05), ("0,05", 0.05), ("-0.1mm", -0.1),
                          ("", 0.0)):
            self.assertEqual(H.parse_printer_inputs("0.6", text)[0]["fitOffset"], val, text)
        self.assertEqual(H.parse_printer_inputs("0,35 mm", "0")[0]["nozzle"], 0.35)
        for nozzle, offset, part in (("abc", "0", "Nozzle diameter"), ("2 mm", "0", "between 0.1 and 1.2"),
                                     ("0.4", "0.5", "Fit offset"), ("0.4", "x", "for example 0.05"),
                                     ("0.4", "-0.3", "between -0.2 and +0.3")):
            out, err = H.parse_printer_inputs(nozzle, offset)
            self.assertIsNone(out)
            self.assertIn(part, err)

    def test_merge_keeps_the_other_printer_keys(self):
        cfg = {"moldsDir": "D:/m", "printer": {"bedX": 220, "nozzle": 0.4}}
        self.assertEqual(H.merge_printer(cfg, {"nozzle": 0.6, "fitOffset": -0.05}),
                         {"bedX": 220, "nozzle": 0.6, "fitOffset": -0.05})
        self.assertEqual(H.merge_printer(cfg, {"nozzle": None}), {"bedX": 220})
        self.assertEqual(H.merge_printer({"printer": "bad"}, {"nozzle": 0.4}), {"nozzle": 0.4})
        self.assertEqual(cfg["printer"], {"bedX": 220, "nozzle": 0.4})

    def test_warning_only_when_unconfirmed(self):
        self.assertEqual(H.printer_warning({}), H.NOZZLE_UNCONFIRMED)
        self.assertIsNone(H.printer_warning({"printer": {"nozzle": 0.4}}))
        self.assertIsNone(H.printer_warning({}, {"nozzle": "0.6 mm"}))


class ChainTest(unittest.TestCase):
    def test_next_action_order(self):
        self.assertEqual(H.next_action({"error": {"message": "x"}, "callAgain": True}), "error")
        self.assertEqual(H.next_action({"callAgain": True, "warnings": ["w"]}), "step")  # warnings never stop
        self.assertEqual(H.next_action({"callAgain": True}, cancelled=True), "cancel")
        self.assertEqual(H.next_action({"callAgain": True}), "step")
        self.assertEqual(H.next_action({"callAgain": True, "stage": "s7_casings"},
                                       stop_when=lambda r: r["stage"] == "s7_casings"), "cancel")
        self.assertEqual(H.next_action({"callAgain": False, "done": True}), "done")

    def test_progress_text_escapes_percent(self):
        t = H.progress_text({"stage": "s4_plaster", "status": "pass", "text": "s4_plaster: pass (3.0 s)\n10% overage"}, 4)
        self.assertTrue(t.startswith("Model done | Layout done | Plaster ... | Casings\ns4_plaster"))
        self.assertTrue(t.endswith("\nStep 4"))
        self.assertNotIn("%", t)
        t = H.progress_text({"stage": "s3_moldability", "status": "partial", "text": "s3_moldability: partial"}, 5, 3.94)
        self.assertTrue(t.startswith("Model done | Layout ... | Plaster | Casings\n"))
        self.assertTrue(t.endswith("Step 5 took 3.9 s"))

    def test_stages_done(self):
        self.assertEqual(H.stages_done({}), 0)
        self.assertEqual(H.stages_done({"stage": "s0_intake", "status": "warn"}), 1)
        self.assertEqual(H.stages_done({"stage": "s3_moldability", "status": "partial"}), 3)
        self.assertEqual(H.stages_done({"stage": "s9_export", "status": "pass"}), H.PROGRESS_MAX)
        self.assertEqual(H.group_line({"stage": "s9_export", "status": "pass"}),
                         "Model done | Layout done | Plaster done | Casings done")

    def test_history_line(self):
        res = {"stage": "s8_clips", "status": "partial", "text": "s8_clips: partial (3.5 s)\nNext: s8_clips again"}
        self.assertEqual(H.history_line(res), "s8_clips: partial (3.5 s)")
        self.assertEqual(H.history_line(res, 3.84), "s8_clips: partial (3.5 s) [3.8 s]")
        self.assertEqual(H.history_line({"stage": "s1_params", "status": "pass"}, 0.2), "s1_params: pass [0.2 s]")

    def test_friendly_error(self):
        t = H.friendly_error({"message": "s2_plug: boom", "hint": "Do X.", "report": "r.json"}, "a.log")
        self.assertIn("SlipMold stopped: s2_plug: boom", t)
        self.assertIn("What to do: Do X.", t)
        self.assertIn("Report: r.json", t)
        self.assertIn("Log: a.log", t)
        self.assertIn("plain", H.friendly_error("plain"))

    def test_paths(self):
        self.assertEqual(H.log_path("D:/m/Cup"), "D:/m/Cup/runs/addin.log")
        self.assertEqual(H.log_path(None, temp="T:/tmp"), "T:/tmp/SlipMold/addin.log")
        self.assertEqual(H.status_path("D:/m/Cup"), "D:/m/Cup/runs/addin_status.json")

    def test_status_doc_and_write(self):
        chain = {"state": "done", "steps": 5, "runWarnings": ["s3_moldability: seam across the foot"],
                 "history": ["h%d" % i for i in range(60)], "docName": "Cup", "headless": True,
                 "last": {"stage": "s9_export", "status": "pass", "text": "t", "saved": None}}
        doc = H.status_doc(chain)
        self.assertEqual((doc["state"], doc["running"], doc["stage"]), ("done", False, "s9_export"))
        self.assertEqual(doc["runWarnings"], ["s3_moldability: seam across the foot"])
        self.assertNotIn("gate", doc)
        self.assertEqual(len(doc["history"]), H.HISTORY_MAX)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "runs", "s.json")
            H.write_json(path, doc)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["state"], "done")
            self.assertFalse(os.path.exists(path + ".tmp"))
            H.append_log(os.path.join(tmp, "runs", "addin.log"), "line one")
            with open(os.path.join(tmp, "runs", "addin.log"), encoding="utf-8") as fh:
                self.assertIn("line one", fh.read())


class ModelTest(unittest.TestCase):
    def test_pick_body(self):
        c = [("cup", "Root", False), ("plug", "SlipMold", True), ("Cup", "Ware", False), ("master_part", "A", False)]
        self.assertEqual(H.pick_body(c, "cup"), (0, None))
        self.assertEqual(H.pick_body(c, "master_part"), (3, None))
        idx, err = H.pick_body(c, "plug")
        self.assertIsNone(idx)
        self.assertIn("no solid body named 'plug'", err)
        idx, err = H.pick_body(c, "CUP")
        self.assertIn("several bodies", err)

    def test_export_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, sheet = H.export_targets(tmp, {})
            self.assertTrue(folder.endswith("/exports"))
            self.assertIsNone(sheet)
            os.makedirs(os.path.join(tmp, "out"))
            open(os.path.join(tmp, "out", H.PROCESS_SHEET_HTML), "w").close()
            folder, sheet = H.export_targets(tmp, {"export": {"dir": "out"}})
            self.assertTrue(sheet.endswith("/out/process-sheet.html"))


class IconTest(unittest.TestCase):
    @staticmethod
    def command_ids():
        with open(os.path.join(ROOT, "addin", "SlipMold", "SlipMold.py"), encoding="utf-8") as fh:
            return re.findall(r'^\s+\("(SlipMold\w+)",', fh.read(), re.MULTILINE)

    def test_six_commands_three_buttons(self):
        ids = self.command_ids()
        self.assertEqual(ids, ["SlipMoldMakeMold", "SlipMoldParameters", "SlipMoldResults", "SlipMoldRunStage",
                               "SlipMoldReset", "SlipMoldHelp"])  # the last three in the Advanced dropdown

    def test_icon_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = MI.write_icons(tmp, ids=list(MI.GLYPHS)[:1])
            self.assertEqual(len(paths), len(MI.FILES))
            for (name, size), path in zip(MI.FILES, paths):
                with open(path, "rb") as fh:
                    data = fh.read()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                w, h = struct.unpack(">II", data[16:24])
                self.assertEqual((w, h), (size, size), name)
                idat_len = struct.unpack(">I", data[33:37])[0]
                raw = zlib.decompress(data[41:41 + idat_len])
                self.assertEqual(len(raw), size * (size * 4 + 1))

    def test_every_command_has_its_icons(self):
        res = os.path.join(ROOT, "addin", "SlipMold", "resources")
        for cmd_id in self.command_ids():
            for name, size in MI.FILES:
                path = os.path.join(res, cmd_id, name)
                self.assertTrue(os.path.isfile(path), (cmd_id, name))
                with open(path, "rb") as fh:
                    data = fh.read(24)
                self.assertEqual(data[:4], b"\x89PNG")
                self.assertEqual(struct.unpack(">II", data[16:24]), (size, size), path)


class InstallerConfigTest(unittest.TestCase):
    def test_set_user_config_merges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SlipMold", "config.json")
            IA.set_user_config({"saveAfterStage": False}, path)
            IA.set_user_config({"moldsDir": "D:/Molds"}, path)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), {"saveAfterStage": False, "moldsDir": "D:/Molds"})


if __name__ == "__main__":
    unittest.main()
