"""Bluetooth RFCOMM transport for Divoom Ditoo Pro.

Three classes:
  Transport            — abstract base
  MockTransport        — in-process fake for unit tests
  IOBluetoothTransport — real macOS RFCOMM via PyObjC IOBluetooth

Only IOBluetoothTransport imports IOBluetooth/PyObjC; the other two are
pure Python and importable on any platform.

Hardware notes (from spike/NOTES.md and spike/send_image2.py):
- Use openRFCOMMChannelAsync (NOT sync — sync returns kIOReturnError).
- Do NOT call dev.openConnection() first.
- The channel open completes via rfcommChannelOpenComplete_status_ delegate cb.
- Delegate + run loop MUST live on a dedicated background thread.
- Send with channel.writeSync_length_() from any thread while run loop is alive.
- Close cleanly with channel.closeChannel() — never SIGKILL mid-RFCOMM.
"""

from __future__ import annotations

import threading
from typing import Optional


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class Transport:
    """Abstract transport base. Subclasses implement connect/send/close."""

    def connect(self) -> None:
        raise NotImplementedError

    def send(self, packet: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Mock transport (pure Python, no Bluetooth)
# ---------------------------------------------------------------------------

class MockTransport(Transport):
    """In-process fake transport.  Usable on any platform, no hardware needed.

    Attributes:
        connected (bool): True after connect(), False after close().
        sent (list[bytes]): All packets passed to send(), in order.
    """

    def __init__(self) -> None:
        self.connected: bool = False
        self.sent: list[bytes] = []

    def connect(self) -> None:
        self.connected = True

    def send(self, packet: bytes) -> None:
        if not self.connected:
            raise ConnectionError("MockTransport: not connected")
        self.sent.append(packet)

    def close(self) -> None:
        self.connected = False


# ---------------------------------------------------------------------------
# Real macOS transport
# ---------------------------------------------------------------------------

class IOBluetoothTransport(Transport):
    """Bluetooth RFCOMM transport using PyObjC IOBluetooth (macOS only).

    The IOBluetooth API is CoreFoundation run-loop + delegate based.  To keep
    that complexity off the caller's thread (plain Python or asyncio), this
    class owns a *daemon background thread* that:
      1. Creates an NSObject delegate.
      2. Calls openRFCOMMChannelAsync_withChannelID_delegate_().
      3. Runs AppHelper.runConsoleEventLoop() — the CF run loop.

    connect() blocks (with a timeout) on a threading.Event that the delegate
    sets when rfcommChannelOpenComplete_status_ fires.

    send() calls channel.writeSync_length_() directly — IOBluetooth allows
    this from a non-run-loop thread while the channel is alive.

    close() sends closeChannel() on the run loop thread via AppHelper.callAfter
    then stops the run loop, and joins the background thread.
    """

    def __init__(self, mac: str, channel: int = 2, open_timeout: float = 15.0) -> None:
        self._mac = mac
        self._channel_id = channel
        self._open_timeout = open_timeout

        self._channel = None          # set by delegate on open complete
        self._connect_error: Optional[Exception] = None
        self._open_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the RFCOMM channel.  Blocks until open or timeout."""
        # Import here so other modules don't require PyObjC.
        from IOBluetooth import IOBluetoothDevice  # type: ignore
        from PyObjCTools import AppHelper          # type: ignore
        from Foundation import NSObject            # type: ignore

        self._open_event.clear()
        self._channel = None
        self._connect_error = None

        # Build the delegate class inside connect() so NSObject is available.
        transport_self = self  # closure ref

        class _RFCOMMDelegate(NSObject):  # type: ignore
            def rfcommChannelOpenComplete_status_(self_d, ch, status):  # noqa: N805
                if status == 0:
                    transport_self._channel = ch
                else:
                    transport_self._connect_error = ConnectionError(
                        f"RFCOMM open failed with status {status}"
                    )
                transport_self._open_event.set()

            def rfcommChannelData_data_length_(self_d, ch, data, length):  # noqa: N805
                pass  # RX data — ignored at transport layer

            def rfcommChannelClosed_(self_d, ch):  # noqa: N805
                # Channel closed by remote or error; clear our ref.
                if transport_self._channel is ch:
                    transport_self._channel = None

        def _run_loop():
            dev = IOBluetoothDevice.deviceWithAddressString_(self._mac)
            delegate = _RFCOMMDelegate.alloc().init()
            # Keep delegate alive for the lifetime of the thread.
            _run_loop._delegate = delegate  # type: ignore[attr-defined]

            dev.openRFCOMMChannelAsync_withChannelID_delegate_(
                None, self._channel_id, delegate
            )
            # Blocks until AppHelper.stopEventLoop() or os._exit().
            AppHelper.runConsoleEventLoop()

        self._thread = threading.Thread(target=_run_loop, daemon=True, name="iobluetooth-runloop")
        self._thread.start()

        # Block until delegate fires or we time out.
        fired = self._open_event.wait(timeout=self._open_timeout)
        if not fired:
            # Attempt a clean stop before raising.
            self._stop_runloop()
            raise ConnectionError(
                f"Timed out waiting for RFCOMM open after {self._open_timeout}s "
                f"(device may be audio-connected — disconnect audio and retry)"
            )
        if self._connect_error is not None:
            self._stop_runloop()
            raise self._connect_error

    def send(self, packet: bytes) -> None:
        """Write packet bytes to the RFCOMM channel (synchronous)."""
        if self._channel is None:
            raise ConnectionError("IOBluetoothTransport: not connected (channel is None)")
        result = self._channel.writeSync_length_(packet, len(packet))
        if result != 0:
            raise ConnectionError(f"writeSync_length_ returned {result}")

    def close(self) -> None:
        """Close the RFCOMM channel and stop the run loop. Safe to call when not connected."""
        ch = self._channel
        self._channel = None

        if ch is not None:
            try:
                ch.closeChannel()
            except Exception:
                pass

        self._stop_runloop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _stop_runloop(self) -> None:
        """Stop the CoreFoundation run loop on the background thread and join it."""
        if self._thread is None or not self._thread.is_alive():
            return
        try:
            from PyObjCTools import AppHelper  # type: ignore
            AppHelper.stopEventLoop()
        except Exception:
            pass
        self._thread.join(timeout=3.0)
        self._thread = None
