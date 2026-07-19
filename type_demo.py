"""Quick local test of the human-typing engine (no networking).

Prints a countdown, then types a sample code snippet into whatever window is
focused. Focus a Notepad / VS Code / Chrome textbox during the countdown.

    python type_demo.py

Press ESC to abort mid-type.
"""

from __future__ import annotations

import threading
import time

import keyboard

from receiver.typing_engine import TypingEngine


SAMPLE = '''def fibonacci(n):
    """Return the nth Fibonacci number."""
    # iterative approach
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


if __name__ == "__main__":
    print(fibonacci(10))
'''


def main() -> None:
    engine = TypingEngine()
    keyboard.add_hotkey("esc", engine.abort)

    print("Focus your target window now. Typing starts in:")
    for i in range(5, 0, -1):
        print(f"  {i} ...")
        time.sleep(1)

    print("Typing! (press ESC to abort)")
    completed = engine.type_text(SAMPLE)
    print("done" if completed else "aborted")


if __name__ == "__main__":
    main()
