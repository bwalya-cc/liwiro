#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial


PID=$1  # Get the PID from the first script argument

if ps -p "$PID" > /dev/null
then
   echo "$PID is running"
   # Do something knowing the pid exists
else
   echo "$PID is not running"
fi
