#!/usr/bin/env python3
"""test_hub.py — task 8: barresi build_node_cmd adaptive allow-list + input validation"""
import sys, os, unittest, importlib.util, types

# ---- hub.py ra load mikonim bedoon ajra-ye main ----
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HUB_PATH = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub", "hub.py")

def _load_hub():
    hub_dir = os.path.dirname(HUB_PATH)
    # hub.py doostat module-haye hamsaye (mesle hubcmds) ra ba sys.path-e khod peida konad
    if hub_dir not in sys.path:
        sys.path.insert(0, hub_dir)
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


class TestParseIranLs(unittest.TestCase):
    """parse_iran_ls bayad transport/sni-e sotoon-haye jadid ra begirad va ba
    khorooji-ye CLI-e ghadimi (bedoon-e in do sotoon) ham sazgar bemanad."""

    NEW = ("NAME           PORT     INBOUND      API        TRANSPORT  SNI              USER PATH\n"
           "--------------------------------------------------------------------------------\n"
           "trk01          1005     8444         -          backhaul   -                https://d/trk01\n"
           "trk02          1006     8445         9001       ws         -                https://d/trk02\n"
           "gamenode       1007     8446         -          ws         gmtrk.l1t.ir     https://d/gamenode\n"
           "noisenode      1008     8447         -          noise      -                https://d/noisenode\n")
    OLD = ("NAME           PORT     INBOUND      API        USER PATH\n"
           "--------------------------------------------------------------\n"
           "trk01          1005     8444         -          https://d/trk01\n")

    def _by_name(self, nodes):
        return {n["name"]: n for n in nodes}

    def test_new_format_transport_sni(self):
        nm = self._by_name(hub.parse_iran_ls(self.NEW))
        self.assertEqual(len(nm), 4)
        self.assertEqual(nm["trk01"]["transport"], "backhaul")
        # transport-e 'ws' = pishfarz → None (ta iranNodeMode ba noise/game eshtebah nashavad)
        self.assertIsNone(nm["trk02"]["transport"])
        self.assertIsNone(nm["trk02"]["sni"])
        self.assertEqual(nm["noisenode"]["transport"], "noise")
        self.assertEqual(nm["gamenode"]["sni"], "gmtrk.l1t.ir")
        self.assertEqual(nm["trk01"]["path"], "https://d/trk01")

    def test_old_format_still_parses(self):
        nm = self._by_name(hub.parse_iran_ls(self.OLD))
        self.assertEqual(len(nm), 1)
        self.assertEqual(nm["trk01"]["path"], "https://d/trk01")
        # CLI-e ghadimi transport/sni nadarad — nabayad KeyError bedahad
        self.assertIsNone(nm["trk01"].get("transport"))


class TestIranPerNodeActions(unittest.TestCase):
    """action-hayi ke select-e per-node-e Iran seda mizanad bayad dar allow-list
    bashand، argv-e dorost besazand va tazrigh-e name ra rad konand."""

    def test_per_node_actions_map_and_write(self):
        for act in ("noise_node_on", "noise_node_off",
                    "backhaul_node_on", "backhaul_node_off", "regen_full"):
            cmd = hub.build_iran_cmd(act, {"name": "trk02"})
            self.assertIsNotNone(cmd, act)
            if act != "regen_full":
                self.assertIn(act in WRITE_ACTIONS, (True,), act)

    def test_per_node_name_injection_rejected(self):
        for act in ("noise_node_on", "backhaul_node_on"):
            self.assertIsNone(hub.build_iran_cmd(act, {"name": "trk02; rm -rf /"}))
            self.assertIsNone(hub.build_iran_cmd(act, {"name": "trk02\n"}))


class TestUpstreamLogsStatus(unittest.TestCase):
    """upstream logs/status: read-only node actions ta upstream-ha ghabel-e ayb-yabi bashand."""

    def test_upstream_logs_and_status_argv(self):
        self.assertEqual(build_node_cmd("upstream_logs", {"id": "iranviph"}),
                         ["ratholenode", "upstream", "logs", "iranviph"])
        self.assertEqual(build_node_cmd("upstream_status", {"id": "iranviph"}),
                         ["ratholenode", "upstream", "status", "iranviph"])

    def test_upstream_logs_status_injection_rejected(self):
        self.assertIsNone(build_node_cmd("upstream_logs", {"id": "a; rm -rf /"}))
        self.assertIsNone(build_node_cmd("upstream_status", {"id": "a\n"}))

    def test_upstream_logs_status_are_read_only(self):
        self.assertNotIn("upstream_logs", WRITE_ACTIONS)
        self.assertNotIn("upstream_status", WRITE_ACTIONS)


class TestUpstreamCarrier(unittest.TestCase):
    """hamel-e per-upstream: har upstream mesl-e tunnel-e asli ws/kcp/plain/noise darad."""

    def test_plain_argv(self):
        self.assertEqual(build_node_cmd("upstream_plain_on", {"id": "u1", "remote": "1.2.3.4:8880"}),
                         ["ratholenode", "upstream", "plain", "u1", "on", "1.2.3.4:8880"])
        self.assertEqual(build_node_cmd("upstream_plain_off", {"id": "u1"}),
                         ["ratholenode", "upstream", "plain", "u1", "off"])

    def test_noise_argv_and_pubkey_validation(self):
        pk = "A" * 44
        self.assertEqual(build_node_cmd("upstream_noise_on",
                                        {"id": "u1", "remote": "1.2.3.4:2334", "pubkey": pk}),
                         ["ratholenode", "upstream", "noise", "u1", "on", "1.2.3.4:2334", pk])
        # pubkey-e namotabar bayad rad shavad
        self.assertIsNone(build_node_cmd("upstream_noise_on",
                                         {"id": "u1", "remote": "1.2.3.4:2334", "pubkey": "x"}))

    def test_ws_reset_argv(self):
        self.assertEqual(build_node_cmd("upstream_ws", {"id": "u1"}),
                         ["ratholenode", "upstream", "ws", "u1"])

    def test_carrier_actions_reject_injection(self):
        for act in ("upstream_plain_off", "upstream_noise_off", "upstream_ws"):
            self.assertIsNone(build_node_cmd(act, {"id": "u1; rm -rf /"}))
        self.assertIsNone(build_node_cmd("upstream_plain_on",
                                         {"id": "u1", "remote": "1.2.3.4:80; id"}))

    def test_carrier_actions_are_writes(self):
        for act in ("upstream_plain_on", "upstream_plain_off",
                    "upstream_noise_on", "upstream_noise_off", "upstream_ws"):
            self.assertIn(act, WRITE_ACTIONS, act)


if __name__ == "__main__":
    unittest.main(verbosity=2)
