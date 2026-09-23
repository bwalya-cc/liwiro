#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial


# Remove existing output file
rm -f liwiro_frontend.txt

# Find and process all files
find . -type f \( ! -path "./node_modules/*" ! -name "liwiro_frontend.txt" \) -print0 | while IFS= read -r -d '' file; do
    # Add file path header
    echo "==> $file <==" >> liwiro_frontend.txt
    # Add file contents
    cat "$file" >> liwiro_frontend.txt
    # Add spacing between files
    echo -e "\n\n" >> liwiro_frontend.txt

done

# Add a final message
echo "All files have been processed and saved to $output_file."