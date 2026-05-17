import sys
import logging
from loguru import logger
from app.framework.config import settings

def setup_logger():
    logger.remove()

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <white>{message}</white>",
        level="INFO",
        colorize=True
    )

    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        rotation="500 MB",
        retention="10 days",
        level="INFO",
        compression="zip"
    )

    class InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    try:
        logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    except ValueError:
        logging.basicConfig(handlers=[InterceptHandler()], level=0)

setup_logger()
