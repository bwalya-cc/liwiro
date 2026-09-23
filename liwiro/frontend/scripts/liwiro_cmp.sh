#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial


# Define the output file
output_file="liwiro_frontend.txt"

# Remove existing output file
rm -f $output_file

# Find and process relevant files
find . -type d \( -path "./node_modules" -o -path "./.next" -o -path "./.git" -o -path "./build" -o -path "./out" \) -prune -o \
-type f \( -name "*.ts*" -o -name "*.js*" -o -name "*.css" -o -name "*.json" -o -name "*.sh" -o -name "*.svg" -o -name "*.png" -o -name "*.jpg" \) \
! -name "$output_file" -print0 | while IFS= read -r -d '' file; do
    # Add file path header
    echo "==> $file <==" >> $output_file
    # Add file contents
    cat "$file" >> $output_file
    # Add spacing between files
    echo -e "\n\n" >> $output_file
done

# Add a final message
echo "All files have been processed and saved to $output_file."