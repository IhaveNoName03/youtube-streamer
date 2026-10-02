#!/usr/bin/env python3
"""Logging setup for the YouTube Stream app.

Writes to both the console and data/app.log. Enabled automatically; set
YT_LOG_LEVEL=DEBUG for verbose output, or YT_LOG_FILE to redirect.

This exists because the app previously had no logging at all, which made two
real failures invisible: a daemon worker thread dying silently (the search()
TypeError), and the Flask child being orphaned when the GUI exited.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = '%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s'

# Everything hangs off this root so child loggers (…auth, …search, …server)
# inherit the handlers. Configuring a child directly would leave the others
# with nowhere to write.
ROOT_LOGGER = 'youtube_stream'
_configured = False


def setup_logging(name=None, level=None, log_dir=None) -> logging.Logger:
    """Configure and return a logger. Safe to call more than once.

    Always configures the ROOT logger's handlers, whichever name is passed
    first. Otherwise a caller like app.py doing setup_logging('…boot') would
    attach handlers to that child only, and every later
    setup_logging() would no-op — silently discarding auth/search logs.
    """
    global _configured
    logger = logging.getLogger(ROOT_LOGGER)

    if not _configured:
        if level is None:
            level = os.environ.get('YT_LOG_LEVEL', 'INFO').upper()
        logger.setLevel(getattr(logging, level, logging.INFO))

        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(console)

        if log_dir is None:
            base = Path(__file__).resolve().parent.parent / 'data'
            log_dir = os.environ.get('YT_LOG_DIR', str(base))
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            path = Path(log_dir) / os.environ.get('YT_LOG_FILE', 'app.log')
            fh = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3,
                                     encoding='utf-8')
            fh.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(fh)
            logger.info('Logging to %s', path)
        except OSError as exc:
            logger.warning('File logging disabled: %s', exc)

        logger.propagate = False
        _configured = True

    return logging.getLogger(name) if name else logger


def get_logger(suffix: str = '') -> logging.Logger:
    """Child logger, e.g. get_logger('auth') -> youtube_stream.auth"""
    return logging.getLogger('youtube_stream' + (f'.{suffix}' if suffix else ''))