from apps.api import app_logging
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            "%(asctime)s | %(levelname)s | %(name)s | "
            "%(message)s | %(filename)s:%(lineno)d"
        ),
        handlers=[logging.StreamHandler(sys.stdout)],
    )
