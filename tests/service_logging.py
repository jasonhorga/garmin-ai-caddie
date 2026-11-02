"""Keep application startup logging changes local to the test that starts it."""

from contextlib import contextmanager
import logging


@contextmanager
def preserve_service_logging():
    from server_v2.main import SERVICE_INFO_LOGGERS

    snapshots = []
    for name in (*SERVICE_INFO_LOGGERS, "uvicorn.access", "uvicorn.error", "", "alembic"):
        logger = logging.getLogger(name)
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
