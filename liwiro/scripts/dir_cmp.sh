#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial


# clear terminal
clear

# check if tree is installed
if ! command -v tree &> /dev/null; then
    echo "tree could not be found, please install it to use this script."
    exit 1
fi

# Check for required parameters
if [ $# -ne 2 ]; then
    echo "Usage: $0 <output_file> <target_directory>"
    exit 1
fi

output_file="$1"
target_dir="$2"

# Verify target directory exists
if [ ! -d "$target_dir" ]; then
    echo "Error: Directory '$target_dir' does not exist."
    exit 1
fi

# Remove existing output file
rm -f "$output_file"

# Add project structure visualization using find instead of tree
echo "TARGET FOLDER STRUCTURE:" >> "$output_file"
find "$target_dir" -not \( -path "*/.git" -prune \) \
    -not \( -path "*/node_modules" -prune \) \
    -not \( -path "*/.next" -prune \) \
    -not \( -path "*/build" -prune \) \
    -not \( -path "*/dist" -prune \) \
    -not \( -path "*/out" -prune \) \
    -not \( -path "*/target" -prune \) \
    -not \( -path "*/__pycache__" -prune \) \
    -not \( -path "*/venv" -prune \) \
    -not \( -path "*/.venv" -prune \) \
    -not \( -path "*/env" -prune \) \
    -not \( -path "*/.cache" -prune \) \
    -not \( -path "*/.vscode" -prune \) \
    -not \( -path "*/.idea" -prune \) \
    -not \( -path "*/coverage" -prune \) \
    -not \( -path "*/migrations" -prune \) \
    -not \( -path "*/vendor" -prune \) \
    -not \( -path "*/bin" -prune \) \
    -not \( -path "*/temp" -prune \) \
    -not \( -path "*/tmp" -prune \) \
    -not \( -path "*/vvv" -prune \) \
    -not \( -path "*/obj" -prune \) \
    -not \( -path "*/debug" -prune \) \
    -not \( -path "*/release" -prune \) \
    -not -name "package-lock.json" \
    -not -name "yarn.lock" \
    -not -name "*.log" \
    -not -name ".DS_Store" \
    -not -name ".env*" \
    -not -name "composer.lock" \
    -not -name "*.min.*" \
    -not -name "*.spec.*" \
    -not -name "$output_file" \
    -printf "%p\n" | sed -e "s;[^/]*/; |____;g" -e "s;____|; |;g" >> "$output_file"

# Add separator between structure and content
echo -e "\n\nFILE CONTENTS:\n" >> "$output_file"


# Find and process relevant files
find "$target_dir" -type d \( \
    -path "*/.git" -o \
    -path "*/node_modules" -o \
    -path "*/.next" -o \
    -path "*/build" -o \
    -path "*/dist" -o \
    -path "*/out" -o \
    -path "*/target" -o \
    -path "*/__pycache__" -o \
    -path "*/venv" -o \
    -path "*/.venv" -o \
    -path "*/env" -o \
    -path "*/.cache" -o \
    -path "*/.vscode" -o \
    -path "*/.idea" -o \
    -path "*/coverage" -o \
    -path "*/migrations" -o \
    -path "*/vendor" -o \
    -path "*/bin" -o \
    -path "*/temp" -o \
    -path "*/tmp" -o \
    -path "*/vvv" -o \
    -path "*/obj" -o \
    -path "*/debug" -o \
    -path "*/release" \
    \) -prune -o \
    -type f \( \
        -name "*.ts*" -o \
        -name "*.js*" -o \
        -name "*.css" -o \
        -name "*.json" -o \
        -name "*.sh" -o \
        -name "*.svg" -o \
        -name "*.png" -o \
        -name "*.jpg" -o \
        -name "*.py" -o \
        -name "*.html" -o \
        -name "*.scss" -o \
        -name "*.go" -o \
        -name "*.rs" -o \
        -name "*.rb" \
    \) \
    ! -name "$output_file" \
    ! -name "package-lock.json" \
    ! -name "yarn.lock" \
    ! -name "*.log" \
    ! -name ".DS_Store" \
    ! -name ".env*" \
    ! -name "composer.lock" \
    ! -name "*.min.*" \
    ! -name "*.spec.*" \
    -print0 | while IFS= read -r -d '' file; do
    # Add file path header
    echo "==> $file <==" >> "$output_file"
    # Add file contents
    cat "$file" >> "$output_file"
    # Add spacing between files
    echo -e "\n\n" >> "$output_file"
done

# Add a final message
echo -e "\nProcess completed. All relevant files have been saved to $output_file."