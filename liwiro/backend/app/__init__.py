# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

def create_app(*args, **kwargs):
    from app.main import create_app as main_create_app

    return main_create_app(*args, **kwargs)
