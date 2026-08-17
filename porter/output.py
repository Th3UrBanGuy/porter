"""
Formatted output utilities for the CLI.
"""

import sys


COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
}


def _supports_color():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = _supports_color()


def c(text, color):
    if not USE_COLOR:
        return str(text)
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


OK = "\033[32m\u2714\033[0m" if USE_COLOR else "[OK]"
ERR = "\033[31m\u2718\033[0m" if USE_COLOR else "[ERR]"
WARN = "\033[33m\u26a0\033[0m" if USE_COLOR else "[!]"
ARROW = "\033[36m\u2192\033[0m" if USE_COLOR else ">>"
BULLET = "\033[36m\u2022\033[0m" if USE_COLOR else "*"


def success(msg):
    print(f"  {OK} {msg}")


def error(msg):
    print(f"  {ERR} {c(msg, 'red')}", file=sys.stderr)


def warning(msg):
    print(f"  {WARN} {c(msg, 'yellow')}")


def info(msg):
    print(f"  {ARROW} {msg}")


def bullet(msg):
    print(f"  {BULLET} {msg}")


def header(text):
    print(f"\n{c(text, 'bold')}")


def subheader(text):
    print(f"\n{c(text, 'cyan')}")


def dim(text):
    return c(text, "dim") if USE_COLOR else text


def table_row(col1, col2, col3=""):
    if col3:
        print(f"  {col1:<20} {col2:<30} {col3}")
    else:
        print(f"  {col1:<20} {col2}")


def print_key(key_data):
    """Print an API key with copy-friendly format."""
    print(f"\n  {c('API Key Created!', 'green')}")
    print(f"  {'─' * 40}")
    print(f"  Name:   {key_data.get('name', 'unknown')}")
    print(f"  ID:     {dim(key_data.get('id', 'unknown'))}")
    print(f"  Key:    {c(key_data['key'], 'yellow')}")
    print(f"\n  {c('Copy this key now. It will not be shown again.', 'dim')}")
    print()
