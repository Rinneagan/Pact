# Icons

This directory should contain Tabler Icons as PNG assets.

## Required Icons

Download Tabler Icons from: https://tabler.io/icons

For each icon, download both light and dark variants (tinted to match theme colors):

| Icon Name | Tabler Icon | Light Color | Dark Color |
|-----------|-------------|-------------|------------|
| ti-books | books | #639922 | #97C459 |
| ti-refresh | refresh | #639922 | #97C459 |
| ti-book-2 | book-2 | #639922 | #97C459 |
| ti-external-link | external-link | #639922 | #97C459 |
| ti-download | download | #639922 | #97C459 |
| ti-x | x | gray | gray |
| ti-tag | tag | #639922 | #97C459 |
| ti-link | link | #639922 | #97C459 |
| ti-list | list | #639922 | #97C459 |
| ti-file-text | file-text | #639922 | #97C459 |
| ti-sun | sun | #639922 | #97C459 |
| ti-moon | moon | #97C459 | #639922 |
| ti-chevron-left | chevron-left | #639922 | #97C459 |
| ti-chevron-right | chevron-right | #639922 | #97C459 |
| ti-arrow-left | arrow-left | #639922 | #97C459 |
| ti-minus | minus | #639922 | #97C459 |
| ti-plus | plus | #639922 | #97C459 |

## File Naming Convention

Each icon should have two files:
- `{icon_name}_light.png` - Tinted for light theme
- `{icon_name}_dark.png` - Tinted for dark theme

Example: `ti-books_light.png`, `ti-books_dark.png`

## Size

- Source size: 48px (2x for retina)
- Rendered size: 20px (downscaled by ctk.CTkImage)

## License

Tabler Icons are licensed under the MIT License, which allows free use, modification, and distribution.

## Installation Instructions

1. Visit https://tabler.io/icons
2. For each icon in the table above:
   - Download the SVG
   - Convert to PNG at 48px size
   - Tint the PNG with the appropriate color (light or dark theme)
   - Save as `{icon_name}_{light|dark}.png`

Alternatively, you can use a script to batch download and tint the icons.

## Placeholder

Until the actual icons are downloaded, the application will use emoji as fallback.
