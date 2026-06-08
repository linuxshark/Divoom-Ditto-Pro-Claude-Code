"""Bluetooth RFCOMM transport for Divoom Ditoo Pro.

Three classes:
  Transport            — abstract base
  MockTransport        — in-process fake for unit tests
  IOBluetoothTransport — real macOS RFCOMM via PyObjC IOBluetooth

Only IOBluetoothTransport imports IOBluetooth/PyObjC; the other two are
pure Python and importable on any platform.

Hardware-verified architecture (spike/NOTES.md, spike/mainloop_test.py):
- Transport is Bluetooth Classic RFCOMM/SPP, channel 2, async open only
  (sync open returns kIOReturnError).
- IOBluetooth delivers RFCOMM delegate callbacks ONLY on the thread running the
  CFRunLoop — in practice the MAIN thread. So:
    * The OWNER runs run_forever() on its MAIN thread.
    * start()/send()/stop() marshal the actual BT calls onto that runloop via
      AppHelper.callAfter/callLater and are safe to call from a worker thread.
- macOS aggressively reconnects the Ditoo as an audio device, which blocks
  RFCOMM. dev.closeConnection() drops that audio link (returns 0); opening RFCOMM
  immediately after then succeeds. This is the SPP-only tradeoff: while we hold
  the channel the Ditoo is NOT a Mac audio output.
- Never SIGKILL mid-RFCOMM (wedges the device SPP server; recover by power-cycle).
"""

from __future__ import annotations

import threading
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class Transport:
    """Abstract transport base. Subclasses implement send."""

    def send(self, packet: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Mock transport (pure Python, no Bluetooth)
# ---------------------------------------------------------------------------

class MockTransport(Transport):
    """In-process fake transport.  Usable on any platform, no hardware needed.

    Mirrors the IOBluetoothTransport API the daemon uses (start/run_forever/
    send/stop/wait_ready) plus a simple connect() for direct unit tests.

    Attributes:
        connected (bool): True after connect()/start(), False after close()/stop().
        sent (list[bytes]): All packets passed to send(), in order.
    """

    def __init__(self) -> None:
        self.connected: bool = False
        self.sent: list[bytes] = []
        self._stop_evt = threading.Event()
        self.on_ready: Optional[Callable[[], None]] = None
        self.on_closed: Optional[Callable[[], None]] = None

    # Simple API (direct tests)
    def connect(self) -> None:
        self.connected = True

    def send(self, packet: bytes) -> None:
        if not self.connected:
            raise ConnectionError("MockTransport: not connected")
        self.sent.append(packet)

    def close(self) -> None:
        self.connected = False
        self._stop_evt.set()

    # Daemon-shaped API
    def start(
        self,
        on_ready: Optional[Callable[[], None]] = None,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_ready = on_ready
        self.on_closed = on_closed
        self.connected = True
        if on_ready is not None:
            on_ready()

    def run_forever(self) -> None:
        self._stop_evt.wait()

    def stop(self) -> None:
        self.close()

    def wait_ready(self, timeout: Optional[float] = None) -> bool:
        return self.connected

    @property
    def is_ready(self) -> bool:
        return self.connected


# ---------------------------------------------------------------------------
# Real macOS transport (main-runloop model)
# ---------------------------------------------------------------------------

# Cached ObjC delegate class. Built once on first use — an ObjC class name can
# only be registered with the runtime once per process, so defining it inside a
# method breaks on the second instance ("overriding existing Objective-C class").
_DELEGATE_CLASS = None


def _get_delegate_class():
    global _DELEGATE_CLASS
    if _DELEGATE_CLASS is not None:
        return _DELEGATE_CLASS

    from Foundation import NSObject  # type: ignore

    class _RFCOMMDelegate(NSObject):  # type: ignore
        # `transport` is attached after alloc().init() by the caller.
        def rfcommChannelOpenComplete_status_(self, ch, status):  # noqa: N805
            t = self.transport
            if status == 0:
                t._channel = ch
                t._ready.set()
                if t._on_ready is not None:
                    try:
                        t._on_ready()
                    except Exception:
                        pass
            else:
                t._channel = None
                t._open_error = ConnectionError(
                    f"RFCOMM open failed with status {status}"
                )
                t._ready.set()
                t._stop_loop()  # let run_forever() return so the owner can retry

        def rfcommChannelData_data_length_(self, ch, data, length):  # noqa: N805
            pass  # RX data (ACKs) — ignored at transport layer

        def rfcommChannelClosed_(self, ch):  # noqa: N805
            t = self.transport
            t._channel = None
            t._ready.clear()
            if t._on_closed is not None:
                try:
                    t._on_closed()
                except Exception:
                    pass
            # Stop the run loop so the owner's start()/run_forever() cycle can
            # re-open the channel synchronously (open delivers its callback only
            # when initiated outside a running loop — see NOTES.md).
            if not t._stopping:
                t._stop_loop()

    _DELEGATE_CLASS = _RFCOMMDelegate
    return _DELEGATE_CLASS


class IOBluetoothTransport(Transport):
    """RFCOMM transport using PyObjC IOBluetooth (macOS only), main-runloop model.

    Usage (in the owner):
        t = IOBluetoothTransport(MAC)
        t.start(on_ready=..., on_closed=...)   # main thread, non-blocking
        # ... start a worker thread that waits on t.wait_ready() then t.send() ...
        t.run_forever()                        # main thread, blocks (CFRunLoop)

    start()/send()/reopen()/stop() are safe to call from any thread; they marshal
    the real BT calls onto the main CFRunLoop.
    """

    SETTLE_AFTER_AUDIO_CLOSE = 0.4  # seconds between closeConnection() and open

    def __init__(self, mac: str, channel: int = 2, open_timeout: float = 15.0) -> None:
        self._mac = mac
        self._channel_id = channel
        self._open_timeout = open_timeout

        self._channel = None
        self._delegate = None
        self._stopping = False
        self._ready = threading.Event()
        self._open_error: Optional[Exception] = None
        self._on_ready: Optional[Callable[[], None]] = None
        self._on_closed: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------
    # Run loop control (MAIN thread)
    # ------------------------------------------------------------------

    def run_forever(self) -> None:
        """Run the CoreFoundation run loop on the MAIN thread. Returns when the
        channel closes, the open fails, the open times out, or stop() is called —
        so the owner can retry start()/run_forever() with backoff, or exit."""
        from PyObjCTools import AppHelper  # type: ignore
        AppHelper.runConsoleEventLoop()

    def _stop_loop(self) -> None:
        from PyObjCTools import AppHelper  # type: ignore
        try:
            AppHelper.stopEventLoop()
        except Exception:
            pass

    def stop(self) -> None:
        """Permanently stop: mark stopping, close the channel, stop the loop.
        Safe from any thread."""
        self._stopping = True
        from PyObjCTools import AppHelper  # type: ignore
        AppHelper.callAfter(self._do_stop)

    # ------------------------------------------------------------------
    # Open
    # ------------------------------------------------------------------

    def start(
        self,
        on_ready: Optional[Callable[[], None]] = None,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        """Initiate an RFCOMM open and arm the open watchdog. Call on the MAIN
        thread, then call run_forever().

        The open is initiated synchronously here (outside the running loop)
        because IOBluetooth only delivers the open-complete callback for opens
        initiated *outside* a running CFRunLoop — confirmed on hardware (see
        spike/NOTES.md). Reconnects therefore use a fresh start()/run_forever()
        cycle rather than reopening inside the live loop.
        """
        from PyObjCTools import AppHelper  # type: ignore
        self._on_ready = on_ready
        self._on_closed = on_closed
        self._stopping = False
        self._channel = None
        self._ready.clear()
        self._open_error = None
        self._close_audio_then_open()
        # Watchdog fires inside run_forever(); stops the loop if not open in time.
        AppHelper.callLater(self._open_timeout, self._open_watchdog)

    def _open_watchdog(self) -> None:
        if self._channel is None and not self._stopping:
            self._open_error = ConnectionError(
                f"RFCOMM open timed out after {self._open_timeout}s "
                f"(device off / out of range / audio re-grabbed the link)"
            )
            self._ready.set()
            self._stop_loop()

    def _close_audio_then_open(self) -> None:
        import time
        from IOBluetooth import IOBluetoothDevice  # type: ignore

        dev = IOBluetoothDevice.deviceWithAddressString_(self._mac)
        if dev.isConnected():
            # Drop the macOS audio (A2DP/HFP) link so RFCOMM can open; a brief
            # settle then keeps the open on this thread (registers on main loop).
            dev.closeConnection()
            time.sleep(self.SETTLE_AFTER_AUDIO_CLOSE)
        self._do_open()

    def _do_open(self) -> None:
        # runs on the main run loop thread
        from IOBluetooth import IOBluetoothDevice  # type: ignore

        dev = IOBluetoothDevice.deviceWithAddressString_(self._mac)
        delegate = _get_delegate_class().alloc().init()
        delegate.transport = self
        self._delegate = delegate  # keep alive
        res = dev.openRFCOMMChannelAsync_withChannelID_delegate_(
            None, self._channel_id, delegate
        )
        code = res[0] if isinstance(res, tuple) else res
        if code != 0:
            self._open_error = ConnectionError(
                f"openRFCOMMChannelAsync returned {code}"
            )
            self._ready.set()

    def wait_ready(self, timeout: Optional[float] = None) -> bool:
        """Block (off the run loop) until the channel is open. Returns True if
        open, False on timeout. Raises if the open errored."""
        if timeout is None:
            timeout = self._open_timeout
        ok = self._ready.wait(timeout)
        if self._open_error is not None:
            err = self._open_error
            self._open_error = None
            raise err
        return ok and self._channel is not None

    @property
    def is_ready(self) -> bool:
        return self._channel is not None

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(self, packet: bytes) -> None:
        """Write packet bytes to the channel. Safe from any thread; the write is
        marshaled onto the run loop. Raises if not currently open."""
        if self._channel is None:
            raise ConnectionError("IOBluetoothTransport: not connected")
        from PyObjCTools import AppHelper  # type: ignore
        AppHelper.callAfter(self._do_send, packet)

    def _do_send(self, packet: bytes) -> None:
        # runs on the main run loop thread
        ch = self._channel
        if ch is None:
            return
        ch.writeSync_length_(packet, len(packet))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_stop(self) -> None:
        from PyObjCTools import AppHelper  # type: ignore
        ch = self._channel
        self._channel = None
        self._ready.clear()
        if ch is not None:
            try:
                ch.closeChannel()
            except Exception:
                pass
        try:
            AppHelper.stopEventLoop()
        except Exception:
            pass

    def close(self) -> None:
        """Alias for stop() to satisfy the Transport base contract."""
        self.stop()
