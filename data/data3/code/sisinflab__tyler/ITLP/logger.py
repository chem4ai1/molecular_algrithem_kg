import logging

LOGGER_NAME = "ITLP"
LOGGING_LEVEL = logging.DEBUG


def get_logger(log_level=LOGGING_LEVEL):
    # Create a logger
    time_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt=time_format
    )

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Define format for logs
    fmt = "%(asctime)s | %(levelname)8s | %(filename)s:%(lineno)2d | %(message)s"

    # Create stdout handler for logging to the console (logs all five levels)
    stdout_handler = logging.StreamHandler()
    stdout_handler.setLevel(LOGGING_LEVEL)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    return logger
