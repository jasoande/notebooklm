#!/bin/bash

# Loop through all files and directories in the current folder
for file in *; do
    # Check if the file name actually contains a space
    if [[ "$file" == *" "* ]]; then
        # Replace all spaces with underscores
        new_name="${file// /_}"
        
        # Rename the file
        mv "$file" "$new_name"
        echo "Renamed: '$file' -> '$new_name'"
    fi
done

echo "Filename sanitization complete!"
