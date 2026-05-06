"""Setup centralizado de logging. Chamado UMA vez no startup, antes dos imports
que dependem de ChatOllama/agent."""

import logging
import os
import sys


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    fmt = "%(asctime)s.%(msecs)03d | %(levelname)-5s | %(name)-10s | %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))

    # libs ruidosas
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
