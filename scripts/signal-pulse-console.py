"""Deliver Ctrl+C to a caller-verified process in its separate Windows console."""

import ctypes
from ctypes import wintypes
import os
import sys
import time


def _send_interrupt(kernel, pid: int) -> None:
    processes = (wintypes.DWORD * 128)()
    count = kernel.GetConsoleProcessList(processes, len(processes))
    if count > len(processes) or pid in processes[:count] or pid == os.getpid():
        raise RuntimeError("target must have a separate console")
    kernel.FreeConsole()
    if not kernel.AttachConsole(pid):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # Event zero is Ctrl+C. The sender ignores its own broadcast.
        if not kernel.SetConsoleCtrlHandler(None, True) or not kernel.GenerateConsoleCtrlEvent(0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(0.2)
    finally:
        kernel.FreeConsole()


def interrupt(pid: int, expected_creation: int) -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.AttachConsole.argtypes = (wintypes.DWORD,)
    kernel.GenerateConsoleCtrlEvent.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.GetConsoleProcessList.argtypes = (ctypes.POINTER(wintypes.DWORD), wintypes.DWORD)
    kernel.SetConsoleCtrlHandler.argtypes = (ctypes.c_void_p, wintypes.BOOL)
    target = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not target:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        times = (wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME())
        if not kernel.GetProcessTimes(target, *times):
            raise ctypes.WinError(ctypes.get_last_error())
        creation = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        if creation != expected_creation:
            raise RuntimeError("target process identity changed")
        _send_interrupt(kernel, pid)
    finally:
        kernel.CloseHandle(target)


if __name__ == "__main__":
    interrupt(int(sys.argv[1]), int(sys.argv[2]))
