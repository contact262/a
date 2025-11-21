# MyXL CLI Application
__version__ = "1.0.0"
__author__ = "MyXL Team"

import logging
import os

# Configure logging
def setup_logging():
    """Setup application logging"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(log_dir, 'myxl_app.log'), encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

# Initialize logging when package is imported
setup_logging()