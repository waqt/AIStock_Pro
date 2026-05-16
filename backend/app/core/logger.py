import sys
import logging
from loguru import logger
from app.core.config import settings

def setup_logger():
    # Remove default handler
    logger.remove()

    # Windows 控制台 UTF-8 兼容
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    # Standard output for console
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <white>{message}</white>",
        level="INFO",
        colorize=True
    )
    
    # File output for production tracing
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        rotation="500 MB",
        retention="10 days",
        level="INFO",
        compression="zip"
    )
    
    # Redirect standard logging to loguru
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
        # Python 3.7 不支持 force 参数，回退
        logging.basicConfig(handlers=[InterceptHandler()], level=0)

setup_logger()
