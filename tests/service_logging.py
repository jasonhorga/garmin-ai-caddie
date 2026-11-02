"""Keep application startup logging changes local to the test that starts it."""

from contextlib import contextmanager
import logging


@contextmanager
def preserve_service_logging():
    from server_v2.main import SERVICE_INFO_LOGGERS

    add_handler = logging.Logger.addHandler
    snapshots = []
    existing = {name: value for name, value in logging.Logger.manager.loggerDict.items()
                if isinstance(value, logging.Logger)}
    for logger in (logging.getLogger(), *existing.values()):
        snapshots.append((logger, logger.handlers[:], logger.filters[:],
                          logger.level, logger.propagate, logger.disabled))
    handler_filters = {handler: handler.filters[:] for value in logging.Logger.manager.loggerDict.values()
                       if isinstance(value, logging.Logger) for handler in value.handlers}
    for handler in (*logging.getLogger().handlers, logging.lastResort):
        if handler is not None:
            handler_filters.setdefault(handler, handler.filters[:])
    try:
        yield
    finally:
        logging.Logger.addHandler = add_handler
        for name, logger in logging.Logger.manager.loggerDict.copy().items():
            if isinstance(logger, logging.Logger) and name not in existing:
                logger.handlers[:] = []
                logger.filters[:] = []
                logger.setLevel(logging.NOTSET)
                logger.propagate = True
                logger.disabled = False
        for handler, filters in handler_filters.items():
            handler.filters[:] = filters
        for logger, handlers, filters, level, propagate, disabled in snapshots:
            logger.handlers[:] = handlers
            logger.filters[:] = filters
            logger.setLevel(level)
            logger.propagate = propagate
            logger.disabled = disabled


class ServiceLoggingIsolationMixin:
    """Scope all startup logging mutations to the class exercising them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enterClassContext(preserve_service_logging())
