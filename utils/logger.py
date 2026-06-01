"""
utils/logger.py — Colorama-powered terminal logger
"""

import sys
import logging
from datetime import datetime, timezone
from colorama import Fore, Back, Style, init

init(autoreset=True)

LEVEL_STYLES = {
    "INFO":     (Fore.CYAN,    "INFO    "),
    "SUCCESS":  (Fore.GREEN,   "SUCCESS "),
    "SEARCH":   (Fore.MAGENTA, "SEARCH  "),
    "DATABASE": (Fore.BLUE,    "DATABASE"),
    "ALERT":    (Fore.YELLOW,  "ALERT   "),
    "ERROR":    (Fore.RED,     "ERROR   "),
    "WARNING":  (Fore.YELLOW,  "WARNING "),
    "DEBUG":    (Fore.WHITE,   "DEBUG   "),
    "BOT":      (Fore.LIGHTCYAN_EX,  "BOT     "),
    "USERBOT":  (Fore.LIGHTBLUE_EX,  "USERBOT "),
    "SETUP":    (Fore.LIGHTGREEN_EX, "SETUP   "),
}


class ColorLogger:
    """Custom colored logger for terminal output."""

    def __init__(self, name: str = "TGMonitor") -> None:
        self.name = name

    def _log(self, level: str, message: str) -> None:
        color, label = LEVEL_STYLES.get(level, (Fore.WHITE, level.ljust(8)))
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        prefix = (
            Style.DIM + f"[{ts}] "
            + Style.BRIGHT + color + f"[{label}] "
            + Style.RESET_ALL
        )
        print(prefix + color + message + Style.RESET_ALL, file=sys.stdout)

    def info(self, msg: str) -> None:
        self._log("INFO", msg)

    def success(self, msg: str) -> None:
        self._log("SUCCESS", msg)

    def search(self, msg: str) -> None:
        self._log("SEARCH", msg)

    def database(self, msg: str) -> None:
        self._log("DATABASE", msg)

    def alert(self, msg: str) -> None:
        self._log("ALERT", msg)

    def error(self, msg: str) -> None:
        self._log("ERROR", msg)

    def warning(self, msg: str) -> None:
        self._log("WARNING", msg)

    def debug(self, msg: str) -> None:
        self._log("DEBUG", msg)

    def bot(self, msg: str) -> None:
        self._log("BOT", msg)

    def userbot(self, msg: str) -> None:
        self._log("USERBOT", msg)

    def setup(self, msg: str) -> None:
        self._log("SETUP", msg)

    def banner(self) -> None:
        banner = f"""
{Fore.CYAN}{Style.BRIGHT}
╔══════════════════════════════════════════════╗
║        TG MONITOR — Production v1.0          ║
║   Telegram Keyword Monitoring System         ║
╚══════════════════════════════════════════════╝
{Style.RESET_ALL}"""
        print(banner)


# Intercept standard logging to colorlog
class PythonLoggingHandler(logging.Handler):
    def __init__(self, color_logger: ColorLogger) -> None:
        super().__init__()
        self.cl = color_logger

    def emit(self, record: logging.LogRecord) -> None:
        level = record.levelname
        msg = self.format(record)
        if level in ("ERROR", "CRITICAL"):
            self.cl.error(msg)
        elif level == "WARNING":
            self.cl.warning(msg)
        elif level == "DEBUG":
            self.cl.debug(msg)
        else:
            self.cl.info(msg)


logger = ColorLogger()


def setup_python_logging() -> None:
    """Redirect stdlib logging to our color logger."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Remove existing handlers
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = PythonLoggingHandler(logger)
    handler.setFormatter(logging.Formatter("%(name)s — %(message)s"))
    root.addHandler(handler)
    # Suppress noisy libraries
    for noisy in ("telethon", "aiogram", "motor", "pymongo", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
