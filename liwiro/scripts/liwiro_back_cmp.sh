#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial


# Define the output file
OUTPUT_FILE="liwiro_backend.txt"

# Generate the tree structure and write to the output file with header
echo "Liwiro Backend Project Structure" > "$OUTPUT_FILE"
tree -I "vvv|__pycache__" >> "$OUTPUT_FILE"

# Get list of backend files except the output file, .env, vvv folder, and __pycache__
FILES=$(find . -type f -not -path "./$OUTPUT_FILE" \
    -not -path "./.env" \
    -not -path "./vvv/*" \
    -not -path "*/__pycache__/*")

# Append contents of each file to the output file
for file in $FILES; do
    echo "" >> "$OUTPUT_FILE"
    echo "=== FILE: $file ===" >> "$OUTPUT_FILE"
    echo "======================================================" >> "$OUTPUT_FILE"
    cat "$file" >> "$OUTPUT_FILE"
done

echo "LIWIRO BACKEND CODEBASE SAVED TO $OUTPUT_FILE"