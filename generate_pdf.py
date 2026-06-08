#!/usr/bin/env python3
"""
Generate PDF-ready HTML from PROJECT_APE_EXECUTIVE_SUMMARY.md
Can be printed to PDF from any browser
"""

import markdown
from pathlib import Path

# Read markdown file
md_file = Path(__file__).parent / "PROJECT_APE_EXECUTIVE_SUMMARY.md"
md_content = md_file.read_text()

# Convert to HTML
html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])

# Create full HTML document with professional styling
html_document = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project APE - Executive Summary</title>
    <style>
        @page {{
            margin: 1in;
            size: letter;
        }}

        @media print {{
            .no-print {{ display: none; }}
            a {{ color: #000; text-decoration: none; }}
            h1, h2, h3 {{ page-break-after: avoid; }}
            table {{ page-break-inside: avoid; }}
            pre {{ page-break-inside: avoid; }}
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 8.5in;
            margin: 0 auto;
            padding: 20px;
            background: #fff;
        }}

        h1 {{
            color: #CC0000;  /* Red Hat Red */
            font-size: 32px;
            border-bottom: 3px solid #CC0000;
            padding-bottom: 10px;
            margin-top: 30px;
        }}

        h2 {{
            color: #000;
            font-size: 24px;
            border-bottom: 2px solid #ccc;
            padding-bottom: 8px;
            margin-top: 25px;
        }}

        h3 {{
            color: #333;
            font-size: 18px;
            margin-top: 20px;
        }}

        h4 {{
            color: #555;
            font-size: 16px;
            margin-top: 15px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }}

        table th {{
            background-color: #CC0000;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }}

        table td {{
            padding: 10px;
            border: 1px solid #ddd;
        }}

        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}

        pre {{
            background-color: #f4f4f4;
            border-left: 4px solid #CC0000;
            padding: 15px;
            overflow-x: auto;
            font-family: 'Courier New', Courier, monospace;
            font-size: 13px;
            line-height: 1.4;
        }}

        code {{
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', Courier, monospace;
            font-size: 13px;
        }}

        blockquote {{
            border-left: 4px solid #ccc;
            margin: 15px 0;
            padding: 10px 20px;
            background-color: #f9f9f9;
            font-style: italic;
        }}

        ul, ol {{
            margin: 10px 0;
            padding-left: 30px;
        }}

        li {{
            margin: 5px 0;
        }}

        .header {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 3px solid #CC0000;
        }}

        .header h1 {{
            margin-bottom: 10px;
            border: none;
        }}

        .header h2 {{
            color: #666;
            font-size: 20px;
            font-weight: normal;
            border: none;
            margin: 0;
        }}

        .metadata {{
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            font-size: 14px;
        }}

        .metadata strong {{
            color: #CC0000;
        }}

        .highlight {{
            background-color: #fff3cd;
            padding: 15px;
            border-left: 4px solid #ffc107;
            margin: 20px 0;
        }}

        .success {{
            background-color: #d4edda;
            padding: 15px;
            border-left: 4px solid #28a745;
            margin: 20px 0;
        }}

        .print-button {{
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 24px;
            background-color: #CC0000;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }}

        .print-button:hover {{
            background-color: #AA0000;
        }}

        hr {{
            border: none;
            border-top: 2px solid #ddd;
            margin: 30px 0;
        }}

        a {{
            color: #0066cc;
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <button class="print-button no-print" onclick="window.print()">🖨️ Print to PDF</button>

    <div class="header">
        <img src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0iI0NDMDAwMCIvPgogIDx0ZXh0IHg9IjUwIiB5PSI1NSIgZm9udC1mYW1pbHk9IkFyaWFsIiBmb250LXNpemU9IjQwIiBmaWxsPSJ3aGl0ZSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZm9udC13ZWlnaHQ9ImJvbGQiPkFQRTwvdGV4dD4KPC9zdmc+" alt="Project APE Logo" style="width: 100px; margin-bottom: 20px;">
    </div>

    {html_content}

    <hr>
    <footer style="text-align: center; color: #666; font-size: 12px; margin-top: 40px;">
        <p><strong>Project APE - Automated Account Planning Engine</strong></p>
        <p>© 2026 Red Hat, Inc. | Internal Use Only</p>
        <p>Document generated: {Path(__file__).stat().st_mtime}</p>
    </footer>

    <script>
        // Auto-print functionality
        window.addEventListener('load', function() {{
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('autoprint') === 'true') {{
                setTimeout(() => window.print(), 1000);
            }}
        }});
    </script>
</body>
</html>
"""

# Write HTML file
html_file = Path(__file__).parent / "PROJECT_APE_EXECUTIVE_SUMMARY.html"
html_file.write_text(html_document)

print(f"✅ HTML generated: {html_file}")
print(f"\nTo create PDF:")
print(f"1. Open: {html_file}")
print(f"2. Click 'Print to PDF' button (or Cmd+P / Ctrl+P)")
print(f"3. Save as PDF")
print(f"\nOr open in browser with auto-print:")
print(f"   file://{html_file}?autoprint=true")
