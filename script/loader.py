#!/usr/bin/env python3

import sys
sys.dont_write_bytecode = True

from itertools import cycle
from shutil import get_terminal_size
from threading import Thread
from time import sleep
from utils import scriptutils

class Loader:
    def __init__(self, desc="Loading...", success_msg="Done!", error_msg="Error!", timeout=0.1):
        """
        A loader-like context manager

        Args:
            desc (str, optional): The loader's description. Defaults to "Loading...".
            success_msg (str, optional): Final success print. Defaults to "Done!".
            error_msg (str, optional): Final error print. Defaults to "Error!".
            timeout (float, optional): Sleep time between prints. Defaults to 0.1.
        """
        self.desc = desc
        self.error_msg = error_msg
        self.success_msg = success_msg
        self.timeout = timeout

        self._thread = Thread(target=self._animate, daemon=True)
        self.steps = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
        self.done = False

    def start(self):
        self._thread.start()
        return self

    def _animate(self):
        for c in cycle(self.steps):
            if self.done:
                break
            print(scriptutils.warning(f"\r{self.desc} {c}"), flush=True, end="")
            sleep(self.timeout)

    def __enter__(self):
        self.start()

    def success(self):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        print(scriptutils.success(f"\r{self.success_msg}"), flush=True)

    def error(self):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        print(scriptutils.error(f"\r{self.error_msg}"), flush=True)

    def __exit__(self, exc_type, exc_value, tb):
        # handle exceptions with those variables ^
        self.stop()


if __name__ == "__main__":
    with Loader("Loading with context manager..."):
        for i in range(10):
            sleep(0.25)

    loader = Loader("Loading with object...", "That was fast!", 0.05).start()
    for i in range(10):
        sleep(0.25)
    loader.stop()