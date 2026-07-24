#!/usr/bin/env python3
"""test_hub.py — task 8: barresi build_node_cmd adaptive allow-list + input validation"""
import sys, os, unittest, importlib.util, types

# ---- hub.py ra load mikonim bedoon ajra-ye main ----
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HUB_PATH = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub", "hub.py")

def _load_hub():
    spec = importlib.util.spec_from_file_location("hub", HUB_PATH)
    mod = importlib.util.module_from_spec(spec)
    # stub environment so hub doesn't try to read config files
    import io
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    os.environ.setdefault("RATHOLEHUB_CONF", "/dev/null")
    os.environ.setdefault("RATHOLEHUB_INV",  "/dev/null")
    spec.loader.exec_module(mod)
    return mod

hub = _load_hub()
build_node_cmd = hub.build_node_cmd
WRITE_ACTIONS  = hub.WRITE_ACTIONS


class TestAdaptiveAllowList(unittest.TestCase):

    # --- adaptive_off: bedoon arg ---
    def test_adaptive_off_no_args(self):
        self.assertEqual(build_node_cmd("adaptive_off", {}),
                         ["ratholenode", "adaptive", "off"])

    # --- adaptive_status: read-only ---
    def test_adaptive_status(self):
        self.assertEqual(build_node_cmd("adaptive_status", {}),
                         ["ratholenode", "adaptive", "status"])

    # --- adaptive_test: --json bayad ezafe shavad ---
    def test_adaptive_test_json(self):
        self.assertEqual(build_node_cmd("adaptive_test", {}),
                         ["ratholenode", "adaptive", "test", "--json"])

    # --- adaptive_on: motabar ---
    def test_adaptive_on_valid(self):
        self.assertEqual(
            build_node_cmd("adaptive_on", {"interval": "30", "failures": "3", "recoveries": "5"}),
            ["ratholenode", "adaptive", "on", "--interval", "30", "--failures", "3", "--recoveries", "5"],
        )

    # --- adaptive_on: injection dar interval ---
    def test_adaptive_on_injection_interval(self):
        self.assertIsNone(build_node_cmd("adaptive_on", {"interval": "30;id", "failures": "3", "recoveries": "5"}))

    # --- adaptive_on: injection dar failures ---
    def test_adaptive_on_injection_failures(self):
        self.assertIsNone(build_node_cmd("adaptive_on", {"interval": "30", "failures": "3$(id)", "recoveries": "5"}))

    # --- adaptive_on: meghdar-e ghayr-adadi ---
    def test_adaptive_on_non_numeric(self):
        self.assertIsNone(build_node_cmd("adaptive_on", {"interval": "abc", "failures": "3", "recoveries": "5"}))

    # --- adaptive_on: khaali (default-ha lazem ast) ---
    def test_adaptive_on_defaults(self):
        cmd = build_node_cmd("adaptive_on", {})
        # bayad default-ha ra estefade konad (30, 3, 5)
        self.assertIsNotNone(cmd)
        self.assertIn("--interval", cmd)
        self.assertIn("30", cmd)

    # --- adaptive_off dar WRITE_ACTIONS ast ---
    def test_adaptive_off_in_write_actions(self):
        self.assertIn("adaptive_off", WRITE_ACTIONS)

    # --- adaptive_on dar WRITE_ACTIONS ast ---
    def test_adaptive_on_in_write_actions(self):
        self.assertIn("adaptive_on", WRITE_ACTIONS)

    # --- adaptive_status NIST dar WRITE_ACTIONS (read-only) ---
    def test_adaptive_status_not_in_write_actions(self):
        self.assertNotIn("adaptive_status", WRITE_ACTIONS)

    # --- adaptive_test NIST dar WRITE_ACTIONS ---
    def test_adaptive_test_not_in_write_actions(self):
        self.assertNotIn("adaptive_test", WRITE_ACTIONS)

    # --- JSON namotabar bayad field-e amn bargardanad ---
    def test_parse_adaptive_state_malformed(self):
        """parse_adaptive_state (agar vojood darad) bayad baraye JSON namotabar safe bemanad"""
        if hasattr(hub, "parse_adaptive_state"):
            result = hub.parse_adaptive_state("not-json")
            self.assertIsNotNone(result)
            # nabayad exception biahandazad va nabayad field-e makhfi dashte bashad
            self.assertNotIn("WS_PATH", str(result))
        else:
            # tabe vojood nadarad hanooz — skip mikonim
            self.skipTest("parse_adaptive_state hanooz piade nashode (Task 8 step 2)")

    # --- hich field-e makhfi az adaptive_test CMD pass nemishavad ---
    def test_no_secret_in_adaptive_test_cmd(self):
        cmd = build_node_cmd("adaptive_test", {"WS_PATH": "/_rh/secret", "token": "abc"})
        self.assertIsNotNone(cmd)
        self.assertNotIn("/_rh/secret", cmd)
        self.assertNotIn("abc", cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
