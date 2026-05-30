#!/bin/zsh

# Directory to scan (defaults to current directory if not specified)
TARGET_DIR="${1:-.}"
TARGET_DIR=$(realpath "$TARGET_DIR")

echo "🚀 Starting batch PDF conversion in: $TARGET_DIR"
echo "------------------------------------------------"

# ---------------------------------------------------------
# 1. Process LOCAL Files (.docx and .xlsx)
# ---------------------------------------------------------
# Check if LibreOffice is installed where expected
SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"

if [ -f "$SOFFICE" ]; then
    # Convert .docx files
    for doc_file in "$TARGET_DIR"/*.docx(N); do
        [[ -e "$doc_file" ]] || continue
        echo "📄 Converting local Word: $(basename "$doc_file")"
        "$SOFFICE" --headless --convert-to pdf --outdir "$TARGET_DIR" "$doc_file" &>/dev/null
    done

    # Convert .xlsx files
    for xls_file in "$TARGET_DIR"/*.xlsx(N); do
        [[ -e "$xls_file" ]] || continue
        echo "📊 Converting local Excel: $(basename "$xls_file")"
        "$SOFFICE" --headless --convert-to pdf --outdir "$TARGET_DIR" "$xls_file" &>/dev/null
    done
else
    echo "⚠️ LibreOffice not found at $SOFFICE. Skipping local .docx/.xlsx files."
fi

# ---------------------------------------------------------
# 2. Process GOOGLE Cloud Files (.gdoc, .gsheet, .gslides)
# ---------------------------------------------------------
# Note: On macOS, Google Drive desktop shortcuts are usually .gdoc/.gsheet files 
# containing a JSON string with the URL and document ID.

for gfile in "$TARGET_DIR"/*.(gdoc|gsheet|gslides)(N); do
    [[ -e "$gfile" ]] || continue
    
    # Extract the URL from the Google shortcut file
    # This parses out the "url" value from the file's JSON structure
    gurl=$(grep -o '"url": "[^"]*' "$gfile" | sed 's/"url": "//')
    
    if [[ -n "$gurl" ]]; then
        filename=$(basename "${gfile%.*}")
        echo "☁️  Processing Google Workspace link: $filename"

        # Parse the unique Doc/Sheet/Slides ID from the URL
        doc_id=$(echo "$gurl" | grep -oE '/d/[a-zA-Z0-9_-]+' | sed 's/\/d\///')

        if [[ -n "$doc_id" ]]; then
            # Determine the correct export URL based on file type
            if [[ "$gfile" == *.gdoc ]]; then
                export_url="https://docs.google.com/document/d/${doc_id}/export?format=pdf"
            elif [[ "$gfile" == *.gsheet ]]; then
                export_url="https://docs.google.com/spreadsheets/d/${doc_id}/export?format=pdf"
            elif [[ "$gfile" == *.gslides ]]; then
                export_url="https://docs.google.com/presentation/d/${doc_id}/export/pdf"
            fi

            # Download and save directly as PDF using curl
            curl -sL "$export_url" -o "$TARGET_DIR/${filename}.pdf"
        fi
    fi
done

echo "------------------------------------------------"
echo "🎉 Conversion batch complete!"
