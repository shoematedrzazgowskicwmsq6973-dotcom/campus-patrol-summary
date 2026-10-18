"""Verify that installed OCR works even if all outbound network calls fail."""
import socket
import tkinter
from patrol_core import LocalOCR, TEMPLATE


def no_network(*args, **kwargs):
    raise RuntimeError("Network calls are disabled during local OCR verification")


if __name__ == "__main__":
    socket.socket.connect = no_network
    socket.create_connection = no_network
    socket.getaddrinfo = no_network
    root = tkinter.Tk()
    root.withdraw()
    root.destroy()
    assert TEMPLATE.is_file(), "Template is missing"
    LocalOCR()
    print("OK: desktop toolkit, template and local OCR models are ready; no network is needed.")
