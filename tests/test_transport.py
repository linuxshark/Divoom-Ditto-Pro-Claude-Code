"""Unit tests for transport.py.

MockTransport — fully exercised in-process (no hardware).
IOBluetoothTransport — import/subclass/pre-connect-send checks only.
  connect() is NOT called; that requires hardware.
"""

import sys
import os
import pytest

# Make repo root importable (same pattern as test_divoom_proto.py).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from transport import Transport, MockTransport, IOBluetoothTransport


# ---------------------------------------------------------------------------
# Transport abstract base
# ---------------------------------------------------------------------------

class TestTransportBase:
    def test_connect_raises(self):
        t = Transport()
        with pytest.raises(NotImplementedError):
            t.connect()

    def test_send_raises(self):
        t = Transport()
        with pytest.raises(NotImplementedError):
            t.send(b"\x00")

    def test_close_is_noop(self):
        t = Transport()
        t.close()  # must not raise


# ---------------------------------------------------------------------------
# MockTransport
# ---------------------------------------------------------------------------

class TestMockTransport:
    def test_starts_disconnected(self):
        m = MockTransport()
        assert m.connected is False

    def test_sent_starts_empty(self):
        m = MockTransport()
        assert m.sent == []

    def test_connect_sets_connected(self):
        m = MockTransport()
        m.connect()
        assert m.connected is True

    def test_send_appends_to_sent(self):
        m = MockTransport()
        m.connect()
        pkt1 = b"\x01\x02\x03"
        pkt2 = b"\xAA\xBB"
        m.send(pkt1)
        m.send(pkt2)
        assert m.sent == [pkt1, pkt2]

    def test_send_before_connect_raises(self):
        m = MockTransport()
        with pytest.raises(ConnectionError):
            m.send(b"\x00")

    def test_close_sets_disconnected(self):
        m = MockTransport()
        m.connect()
        m.close()
        assert m.connected is False

    def test_close_when_not_connected_is_safe(self):
        m = MockTransport()
        m.close()  # must not raise
        assert m.connected is False

    def test_reconnect_after_close(self):
        m = MockTransport()
        m.connect()
        m.close()
        m.connect()
        assert m.connected is True

    def test_sent_accumulates_across_sends(self):
        m = MockTransport()
        m.connect()
        for i in range(5):
            m.send(bytes([i]))
        assert len(m.sent) == 5
        assert m.sent[3] == bytes([3])

    def test_send_empty_bytes_allowed(self):
        m = MockTransport()
        m.connect()
        m.send(b"")
        assert m.sent == [b""]


# ---------------------------------------------------------------------------
# IOBluetoothTransport — no hardware, structural checks only
# ---------------------------------------------------------------------------

class TestIOBluetoothTransport:
    def test_importable(self):
        """IOBluetoothTransport is importable from transport module."""
        from transport import IOBluetoothTransport as T  # noqa: F401

    def test_is_subclass_of_transport(self):
        assert issubclass(IOBluetoothTransport, Transport)

    def test_constructor_accepts_mac(self):
        t = IOBluetoothTransport("b1-21-81-8c-c0-b5")
        assert t._mac == "b1-21-81-8c-c0-b5"
        assert t._channel_id == 2
        assert t._open_timeout == 15.0

    def test_constructor_accepts_custom_channel_and_timeout(self):
        t = IOBluetoothTransport("aa-bb-cc-dd-ee-ff", channel=1, open_timeout=5.0)
        assert t._channel_id == 1
        assert t._open_timeout == 5.0

    def test_send_before_connect_raises_connection_error(self):
        """send() must raise ConnectionError when channel is None (not yet connected)."""
        t = IOBluetoothTransport("b1-21-81-8c-c0-b5")
        # _channel is None by construction; send() must raise without touching Bluetooth.
        with pytest.raises(ConnectionError):
            t.send(b"\x01\x02\x03")

    def test_close_before_connect_is_safe(self):
        """close() must not raise when called before connect()."""
        t = IOBluetoothTransport("b1-21-81-8c-c0-b5")
        t.close()  # must not raise
