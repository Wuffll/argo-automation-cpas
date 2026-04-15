import logging
import logging.handlers
import sys

from argo_automation_cpas.config import get_settings


DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_SYSLOG_ADDRESS = "/dev/log"
DEFAULT_SYSLOG_FACILITY = logging.handlers.SysLogHandler.LOG_USER

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
STDOUT_FORMAT = "%(name)s %(levelname)s %(message)s"
SYSLOG_FORMAT = "argo-cpas: %(name)s %(levelname)s %(message)s"

_KNOWN_LOGGERS = ("stdout", "file", "syslog")


def _make_stdout_handler(level, formatter):
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _make_file_handler(path, level, formatter):
    handler = logging.handlers.WatchedFileHandler(path)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _make_syslog_handler(address, facility, level):
    handler = logging.handlers.SysLogHandler(address=address, facility=facility)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(SYSLOG_FORMAT))
    return handler


def setup_logging():
    """Configure the root logger based on settings.general.loggers.

    Recognised logger names (set via [general] loggers = ...):
      stdout  — StreamHandler writing to sys.stdout
      file    — WatchedFileHandler (log_file path from [general])
      syslog  — SyslogHandler (syslog_address / syslog_facility from [general])

    Additional [general] keys consumed here:
      log_level       — e.g. DEBUG, INFO, WARNING (default: INFO)
      log_file        — path for the file handler (default: <venv>/var/log/argo-cpas.log)
      syslog_address  — socket path or host:port (default: /dev/log)
      syslog_facility — syslog facility name, e.g. LOG_USER (default: LOG_USER)
    """
    general = get_settings().general
    loggers = getattr(general, "loggers", [])

    unknown = [name for name in loggers if name not in _KNOWN_LOGGERS]
    if unknown:
        raise ValueError(
            "Unknown logger(s) in [general] loggers: %s. Supported: %s"
            % (", ".join(unknown), ", ".join(_KNOWN_LOGGERS))
        )

    level = getattr(general, "log_level", DEFAULT_LOG_LEVEL)
    log_file = getattr(general, "log_file", None)
    syslog_address = getattr(general, "syslog_address", DEFAULT_SYSLOG_ADDRESS)
    syslog_facility = getattr(general, "syslog_facility", DEFAULT_SYSLOG_FACILITY)

    formatter = logging.Formatter(LOG_FORMAT)
    stdout_formatter = logging.Formatter(STDOUT_FORMAT)
    handlers = []

    if "stdout" in loggers:
        handlers.append(_make_stdout_handler(level, stdout_formatter))

    if "file" in loggers:
        handlers.append(_make_file_handler(log_file, level, formatter))

    if "syslog" in loggers:
        handlers.append(_make_syslog_handler(syslog_address, syslog_facility, level))

    root = logging.getLogger()
    root.setLevel(level)
    for handler in handlers:
        root.addHandler(handler)
