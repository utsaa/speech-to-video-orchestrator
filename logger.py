import logging
import os
from datetime import datetime

def setup_logger():
    # Create master logs directory if it doesn't exist
    base_log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(base_log_dir, exist_ok=True)

    # Generate timestamped run directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(base_log_dir, f"run_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    
    # Export for other components (like S2S/Web App) to hook into the same folder
    os.environ["S2V_RUN_DIR"] = run_dir

    log_file = os.path.join(run_dir, f"orchestrator_{timestamp}.log")

    # Set up root logger
    logger = logging.getLogger("orchestrator")
    logger.setLevel(logging.DEBUG)

    # File handler inside the run folder
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # Add handlers
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger

logger = setup_logger()
