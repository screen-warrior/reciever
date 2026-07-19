"""Human-like typing engine.

Takes a string (typically code, with exact indentation/comments preserved) and
replays it as keystrokes through an injector, shaping the timing so it reads as
a real person typing:

  * variable inter-key delays drawn around a target WPM (log-normal spread)
  * short random key dwell (hold) times
  * longer pauses after punctuation and newlines, plus occasional think-pauses
  * occasional adjacent-key typos that get noticed and corrected via backspace

The engine is transport/OS agnostic -- it only talks to an injector object that
implements ``type_char``, ``backspace``, and ``tap``.
"""

from __future__ import annotations

import math
import random
import threading
import time
from typing import Optional

from shared.config import DEFAULT_PROFILE, IDE_ESC_BEFORE_ENTER, TypingProfile
from receiver.injector import get_injector


# QWERTY neighbors for believable fat-finger typos.
_QWERTY_NEIGHBORS = {
    "q": "wa", "w": "qeas", "e": "wrsd", "r": "etdf", "t": "ryfg",
    "y": "tugh", "u": "yihj", "i": "uojk", "o": "ipkl", "p": "ol",
    "a": "qwsz", "s": "awedxz", "d": "serfcx", "f": "drtgvc", "g": "ftyhbv",
    "h": "gyujnb", "j": "huikmn", "k": "jiolm", "l": "kop",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn",
    "n": "bhjm", "m": "njk",
    "1": "2", "2": "13", "3": "24", "4": "35", "5": "46", "6": "57",
    "7": "68", "8": "79", "9": "80", "0": "9",
}

_PUNCTUATION = set(".,;:!?")


def leading_ws_to_spaces(line: str, tab_width: int) -> str:
    """Expand a line's leading whitespace to literal spaces (tabs -> spaces).

    Used by IDE mode so indentation is typed as exact spaces after resetting the
    line to column 0.
    """
    i = 0
    cols = 0
    while i < len(line) and line[i] in (" ", "\t"):
        cols += tab_width if line[i] == "\t" else 1
        i += 1
    return " " * cols + line[i:]


def convert_indentation_to_tabs(text: str, tab_width: int) -> str:
    """Rewrite each line's leading whitespace using tabs where possible.

    The leading whitespace is measured in columns (existing tabs count as
    ``tab_width`` columns). It is then rebuilt as ``cols // tab_width`` tab
    characters followed by ``cols % tab_width`` spaces, so full indent levels
    become Tab presses and any partial remainder stays as spaces. Whitespace
    after the first non-space character is left untouched.
    """
    if tab_width < 1:
        return text

    out_lines = []
    for line in text.split("\n"):
        i = 0
        cols = 0
        while i < len(line) and line[i] in (" ", "\t"):
            cols += tab_width if line[i] == "\t" else 1
            i += 1
        rest = line[i:]
        indent = "\t" * (cols // tab_width) + " " * (cols % tab_width)
        out_lines.append(indent + rest)
    return "\n".join(out_lines)


class TypingEngine:
    def __init__(
        self,
        profile: Optional[TypingProfile] = None,
        injector=None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.profile = profile or DEFAULT_PROFILE
        self.injector = injector or get_injector()
        self.rng = rng or random.Random()
        self._abort = threading.Event()
        # Oscillating-speed state: a phase that advances per character so the
        # effective WPM drifts smoothly between wpm_min and wpm_max.
        self._phase = self.rng.uniform(0.0, 2.0 * math.pi)
        self._current_base = self.profile.delay_for_wpm(self.profile.wpm_mid())

    # -- control ---------------------------------------------------------
    def abort(self) -> None:
        self._abort.set()

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep so an abort takes effect promptly."""
        if seconds <= 0:
            return
        # Wait returns True if the abort flag got set during the sleep.
        self._abort.wait(seconds)

    # -- timing helpers --------------------------------------------------
    def _advance_speed(self) -> None:
        """Advance the drifting speed once per character.

        The effective WPM follows a sine wave between wpm_min and wpm_max, with
        a little random noise so the ebb and flow isn't perfectly regular.
        """
        p = self.profile
        self._phase += p.wpm_drift_rate + self.rng.uniform(
            -p.wpm_drift_noise, p.wpm_drift_noise
        )
        wpm = p.wpm_mid() + p.wpm_amplitude() * math.sin(self._phase)
        self._current_base = p.delay_for_wpm(wpm)

    def _key_delay(self) -> float:
        base = self._current_base
        # Log-normal-ish spread keeps delays positive and occasionally long.
        factor = self.rng.lognormvariate(0.0, self.profile.delay_jitter)
        return base * factor

    def _dwell(self) -> float:
        return self.rng.uniform(self.profile.dwell_min, self.profile.dwell_max)

    def _maybe_extra_pause(self, ch: str) -> float:
        p = self.profile
        extra = 0.0
        if ch in _PUNCTUATION:
            extra += p.pause_after_punctuation
        if ch == "\n":
            extra += p.pause_after_newline
        if ch == " " and self.rng.random() < p.pause_after_word_prob:
            extra += self.rng.uniform(p.pause_after_word_min, p.pause_after_word_max)
        if self.rng.random() < p.think_pause_prob:
            extra += self.rng.uniform(p.think_pause_min, p.think_pause_max)
        return extra

    # -- typos -----------------------------------------------------------
    def _typo_char(self, ch: str) -> Optional[str]:
        low = ch.lower()
        neighbors = _QWERTY_NEIGHBORS.get(low)
        if not neighbors:
            return None
        wrong = self.rng.choice(neighbors)
        return wrong.upper() if ch.isupper() else wrong

    def _do_typo(self, ch: str) -> None:
        """Type one or more wrong chars, pause as if noticing, then delete."""
        p = self.profile
        n = self.rng.randint(1, max(1, p.typo_burst_max))
        typed = 0
        for _ in range(n):
            wrong = self._typo_char(ch)
            if wrong is None:
                break
            self.injector.type_char(wrong, self._dwell())
            typed += 1
            self._sleep(self._key_delay())
            if self._abort.is_set():
                return
        if typed == 0:
            return
        # Notice the mistake.
        self._sleep(self.rng.uniform(p.typo_notice_min, p.typo_notice_max))
        for _ in range(typed):
            if self._abort.is_set():
                return
            self.injector.backspace(self._dwell())
            self._sleep(self._key_delay() * 0.6)

    # -- per-character ---------------------------------------------------
    def _type_one(self, ch: str) -> bool:
        """Type a single character with drift, optional typo, and delay.

        Returns False if aborted during the character.
        """
        self._advance_speed()
        if self._abort.is_set():
            return False

        # Chance of a fat-finger typo before the correct character.
        if ch.lower() in _QWERTY_NEIGHBORS and self.rng.random() < self.profile.typo_prob:
            self._do_typo(ch)
            if self._abort.is_set():
                return False

        self.injector.type_char(ch, self._dwell())
        self._sleep(self._key_delay() + self._maybe_extra_pause(ch))
        return not self._abort.is_set()

    # -- main ------------------------------------------------------------
    def type_text(
        self,
        text: str,
        start_delay: float = 0.0,
        ide_mode: bool = False,
        esc_before_enter: Optional[bool] = None,
    ) -> bool:
        """Type the full text. Returns True if completed, False if aborted.

        In ``ide_mode`` (for smart editors like CodeSignal that auto-indent),
        each new line is reset to column 0 and the exact indentation is typed as
        literal spaces, so the editor's auto-indent can't stack up.
        """
        self._abort.clear()
        if start_delay > 0:
            self._sleep(start_delay)

        if ide_mode:
            return self._type_ide(text, esc_before_enter)
        return self._type_plain(text)

    def _type_plain(self, text: str) -> bool:
        if self.profile.convert_indent_to_tabs:
            text = convert_indentation_to_tabs(text, self.profile.tab_width)
        for ch in text:
            if not self._type_one(ch):
                return False
        return not self._abort.is_set()

    def _type_ide(self, text: str, esc_before_enter: Optional[bool]) -> bool:
        """IDE-aware typing: control indentation ourselves, defeat auto-indent."""
        if esc_before_enter is None:
            esc_before_enter = IDE_ESC_BEFORE_ENTER

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")

        for i, line in enumerate(lines):
            if self._abort.is_set():
                return False

            if i > 0:
                # Move to a clean next line: dismiss any autocomplete popup so
                # Enter makes a newline, press Enter, then wipe the editor's
                # auto-indent back to column 0.
                if esc_before_enter:
                    self.injector.press_escape()
                    self._sleep(0.05)
                self.injector.type_char("\n", self._dwell())
                self._sleep(self.profile.pause_after_newline)
                self.injector.delete_to_line_start()
                self._sleep(0.05)

            # Type this line's exact indentation as literal spaces + content.
            line = leading_ws_to_spaces(line, self.profile.tab_width)
            for ch in line:
                if not self._type_one(ch):
                    return False

        return not self._abort.is_set()
