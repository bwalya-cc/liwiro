#!/bin/bash
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial


# Clear terminal
clear

# Check if tree is installed (for structure visualization)
if ! command -v tree &> /dev/null; then
    echo "Note: Install 'tree' for better structure visualization, using find instead."
fi

# Check for required parameters
if [ $# -lt 3 ]; then
    echo "Usage: $0 <target_file> <root_dir> <file1> [file2 ...]"
    exit 1
fi

target_file="$1"
root_dir="$2"
shift 2
filenames=("$@")

# Verify root directory exists
if [ ! -d "$root_dir" ]; then
    echo "Error: Directory '$root_dir' does not exist."
    exit 1
fi

# Remove existing output file
rm -f "$target_file"

# Add project structure visualization
echo "TARGET FOLDER STRUCTURE:" >> "$target_file"
find "$root_dir" -not \( -path "*/.git" -prune \) \
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
    -not -name "$target_file" \
    -printf "%p\n" | sed -e "s;[^/]*/; |____;g" -e "s;____|; |;g" >> "$target_file"

# Add separator between structure and content
echo -e "\n\nFILE CONTENTS:\n" >> "$target_file"

# Build find name conditions from arguments
name_conditions=()
for ((i=0; i<${#filenames[@]}; i++)); do
    if [ $i -eq 0 ]; then
        name_conditions+=(-name "${filenames[$i]}")
    else
        name_conditions+=(-o -name "${filenames[$i]}")
    fi
done

# Find and process matching files
find "$root_dir" -type d \( \
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
    -path "*/obj" -o \
    -path "*/debug" -o \
    -path "*/release" \
    \) -prune -o \
    -type f \( \
        \( "${name_conditions[@]}" \) \
    \) \
    ! -name "$target_file" \
    ! -name "package-lock.json" \
    ! -name "yarn.lock" \
    ! -name "*.log" \
    ! -name ".DS_Store" \
    ! -name ".env*" \
    ! -name "composer.lock" \
    ! -name "*.min.*" \
    ! -name "*.spec.*" \
    -print0 | while IFS= read -r -d '' file; do
    
    # Get relative path
    relative_path="${file#$root_dir/}"
    
    # Add file path header
    echo "==> $relative_path <==" >> "$target_file"
    
    # Add file contents
    cat "$file" >> "$target_file"
    
    # Add spacing between files
    echo -e "\n\n" >> "$target_file"
done

# Add final message
echo -e "\nProcess completed. Matching files have been saved to $target_file."