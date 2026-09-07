import logging
import sys
from backend.app.core.config import settings


def setup_logging():
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    logger = logging.getLogger("rooman_billing")
    logger.info("Structured logging initialized for %s in %s environment", settings.PROJECT_NAME, settings.ENVIRONMENT)
    return logger


logger = setup_logging()
