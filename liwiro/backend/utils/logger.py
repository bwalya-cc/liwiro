# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import logging
from flask import current_app

def get_logger(name=__name__):
    logger = logging.getLogger(name)
    logger.setLevel(current_app.config.get('LOG_LEVEL', 'INFO'))
    return logger