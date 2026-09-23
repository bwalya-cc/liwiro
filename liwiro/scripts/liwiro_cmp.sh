#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial


# Check if required commands are available
for cmd in tree file sed; do
    if ! command -v $cmd &> /dev/null; then
        echo "Error: $cmd command is required but not installed."
        exit 1
    fi
done

output_file="liwiro.txt"

# Exclusion patterns for both directories and files
exclude_patterns=(
    "node_modules"
    "__pycache__"
    "env*"
    "dist"
    "build"
    ".next"
    ".git"
    "vvv"
    ".venv"
    "*.pyc"
    "*.log"
    ".env*"
    "$output_file"
)

# Create output file with header
{
    echo "LIWIRO FULL PROJECT STRUCTURE AND SOURCE CODE"
    echo
    echo "Project Directory Structure:"
    echo
    tree -I "$(IFS="|"; echo "${exclude_patterns[*]}")" --noreport --dirsfirst -L 3 2>/dev/null
    
    find . -type d \( $(printf -- "-name %s -o " "${exclude_patterns[@]}") -false \) -prune -o -type f ! -name "$output_file" -print | while read -r file; do
        
        # Skip binary files and empty files
        mime_type=$(file --mime-type -b "$file")
        [[ $mime_type != text/* ]] && continue
        [[ ! -s "$file" ]] && continue

        echo
        echo
        echo "=== FILE: ${file#./} ==="
        echo
        
        # Display content with line numbers and clean special chars
        awk '{printf "%5d| %s\n", NR, $0}' "$file" | sed -e 's/\x1B\[[0-9;]*[a-zA-Z]//g' -e 's/\x0D//g'
    done
    
    echo
    echo "Processing complete. Clean output saved to $output_file"
} > "$output_file"