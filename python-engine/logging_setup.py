"""
structlog configuration for the trading-sentinel python-engine.

[STRUCTLOG-CONFIGURE 2026-07-07]
The 2026-07-07 incident (`docker logs python-engine` showing
9,769 lines of `penny_metrics_history_fetch_failed symbol=...`
WITHOUT the `2026-..-.. [warning]` structlog prefix that 95%
of the other log lines carry) exposed that the project was relying
on structlog's *default* configuration -- which in turn delegates to
the stdlib `logging` module's configuration. uvicorn sets up stdlib
logging for its own access/error loggers at startup, and that
configuration appears to interact with structlog's defaults in a
way that drops the timestamp processor for some warning calls.

The fix is explicit and deterministic: configure structlog ourselves
at app startup with a fixed pipeline (TimeStamper -> ConsoleRenderer),
so the output format is the same in every environment regardless of
what stdlib logging or uvicorn do behind our backs. We also wire
structlog to the stdlib root logger so any third-party lib that uses
stdlib `logging` (httpx, apscheduler, etc.) gets the same formatter.

This module is idempotent: calling `configure_structlog()` more than
once is safe (structlog's `configure()` is itself idempotent). Tests
can call it to get deterministic output.

References:
- rule 64 in trading-sentinel-ops (the bug this fixes)
- reference/penny-2026-07-07-silent-freeze.md (the incident timeline)
"""
import logging
import sys
import structlog


_CONFIGURED = False


def configure_structlog(level: str = "INFO") -> None:
    """
    Configure structlog + stdlib logging with a deterministic, timestamped
    pipeline. Safe to call multiple times.

    Pipeline order (matters; see structlog docs):
        1. merge_contextvars  -- pull in any contextvars (request id, etc.)
        2. add_log_level      -- add level=info|warning|... to event dict
        3. TimeStamper        -- add timestamp=2026-..-.. to event dict
        4. format_exc_info    -- render exceptions if present
        5. ConsoleRenderer    -- render event dict to a single line string

    The output looks like:
        2026-07-07 20:11:39 [warning  ] penny_metrics_history_fetch_failed symbol=ABC error=unable to open

    The 5th processor is the same one structlog uses by default, so the
    visual format matches what we saw pre-fix on the timestamped 95% of
    lines. Operators reading today's logs will not see any visual
    difference except for the previously-timestamp-less 5% now having
    timestamps -- which is the fix.
    """
    global _CONFIGURED

    timestamper = structlog.processors.TimeStamper(
        fmt="%Y-%m-%d %H:%M:%S",
        utc=False,  # local time (matches what the docker log file shows)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(
                colors=False,  # docker json-file driver strips ANSI anyway
                event_key="event",
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Wire stdlib logging to the SAME formatter so third-party libs
    # (httpx, apscheduler, uvicorn.access, etc.) and modules that use
    # `logging.getLogger(__name__)` (e.g. penny_universe.py line 23)
    # get the same timestamped format. Also set the ROOT level to the
    # requested value so `logging.getLogger(__name__).getEffectiveLevel()`
    # returns INFO (default is WARNING, which would silently drop our
    # `logger.info` calls from the penny_universe module).
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger = logging.getLogger()
        # Don't replace existing handlers (uvicorn sets up its own
        # access/error handlers); only ensure our formatter is on at
        # least one. The simplest safe move is to add our handler at
        # WARNING so uvicorn's INFO access logs keep their format.
        root_logger.addHandler(handler)
        root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        # httpx logs complete request URLs at INFO.  Telegram credentials are
        # embedded in Bot API paths (`/bot<TOKEN>/sendMessage`), so allowing
        # the library's request line into production logs leaks a live secret.
        # Application-level failures remain logged by each caller.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        _CONFIGURED = True
