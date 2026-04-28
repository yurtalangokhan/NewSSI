import asyncio
import logging
import os
import sys

import uvicorn
from dotenv import load_dotenv

from core import settings

load_dotenv()

if __name__ == "__main__":
    root_logger = logging.getLogger()
    if root_logger.handlers:
        print(
            f"Warning: Root logger already has {len(root_logger.handlers)} handler(s) configured. "
            f"basicConfig() will be ignored. Current level: {logging.getLevelName(root_logger.level)}"
        )

    logging.basicConfig(level=settings.LOG_LEVEL.to_logging_level())
    # Set Compatible event loop policy on Windows Systems.
    # On Windows systems, the default ProactorEventLoop can cause issues with
    # certain async database drivers like psycopg (PostgreSQL driver).
    # The WindowsSelectorEventLoopPolicy provides better compatibility and prevents
    # "RuntimeError: Event loop is closed" errors when working with database connections.
    # This needs to be set before running the application server.
    # Refer to the documentation for more information.
    # https://www.psycopg.org/psycopg3/docs/advanced/async.html#asynchronous-operations
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # In the container image we create a `src -> .` symlink for legacy paths.
    # Watchfiles can detect this as a filesystem loop, so disable auto-reload.
    reload_enabled = settings.is_dev()
    if reload_enabled and os.path.islink("src") and os.path.realpath("src") == os.getcwd():
        logging.getLogger(__name__).warning("Disabling reload due to /app/src symlink loop")
        reload_enabled = False

    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=reload_enabled,
        timeout_graceful_shutdown=settings.GRACEFUL_SHUTDOWN_TIMEOUT,
    )
