#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import os

def create_structure(base_path, structure):
    for path in structure:
        full_path = os.path.join(base_path, path)
        if path.endswith("/"):
            os.makedirs(full_path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            open(full_path, 'w').close()

structure = [
    "backend/app/",
    "backend/app/__init__.py",
    "backend/app/vdb.py",
    "backend/app/main.py",
    "backend/generators/",
    "backend/generators/__init__.py",
    "backend/generators/api_generator.py",
    "backend/models/",
    "backend/models/__init__.py",
    "backend/models/domain.py",
    "backend/utils/",
    "backend/utils/__init__.py",
    "backend/utils/constants.py",
    "backend/utils/logger.py",
    "backend/utils/process_manager.py",
    "backend/config.py",
    "backend/requirements.txt",
    "backend/run.sh"
]

create_structure(".", structure)
print("Folder structure and files created successfully.")
