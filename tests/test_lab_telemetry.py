"""Joebot Lab payload normalization — no live rack or HTTP needed."""

from nexus.lab import normalize_device


def test_smx_board_presence_is_normalized_without_losing_lab_state():
    telemetry = normalize_device({
        "status": "ok", "online": True, "summary": "4 boards • 2 active signal(s)",
        "last_seen_ago": 0,
        "raw": {"2*0LS": "0000300000000000"},
        "boards": [{
            "slot": 2, "plane": "02", "label": "VIDEO 16x16", "audio": False,
            "signals": [{"label": "1", "state": "gray"}, {"label": "5", "state": "ok"}],
        }],
    })
    assert telemetry["source"] == "joebot_lab"
    assert telemetry["online"] is True
    board = telemetry["boards"][0]
    assert board["slot"] == 2 and board["plane"] == "02"
    assert board["signals"] == [
        {"channel": "1", "presence": "absent", "lab_state": "gray"},
        {"channel": "5", "presence": "present", "lab_state": "ok"},
    ]


def test_missing_signal_list_is_not_misreported_as_absent():
    telemetry = normalize_device({"status": "ok", "online": True,
                                  "boards": [{"slot": 6, "plane": "04", "label": "AUDIO", "audio": True}]})
    assert telemetry["boards"][0]["signals"] == []


def test_flat_dms_signals_become_one_logical_all_plane():
    telemetry = normalize_device({
        "status": "bad", "online": True, "summary": "36x36 • 2/36 inputs active",
        "signals": [{"label": "1", "state": "ok"}, {"label": "2", "state": "gray"}],
    })
    assert len(telemetry["boards"]) == 1
    board = telemetry["boards"][0]
    assert board["plane"] == "all" and board["port_count"] == 2
    assert board["signals"] == [
        {"channel": "1", "presence": "present", "lab_state": "ok"},
        {"channel": "2", "presence": "absent", "lab_state": "gray"},
    ]
