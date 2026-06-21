# Assets

This directory contains bundled fonts and icons for the Pact application.

## Fonts

### Lora (Serif Display Font)

- **Source**: https://fonts.google.com/specimen/Lora
- **License**: SIL Open Font License (OFL) - Free to use, modify, and distribute
- **Files**: `Lora-Regular.ttf`, `Lora-Medium.ttf`, `Lora-SemiBold.ttf`
- **Usage**: Display/serif font for wordmark "Pact", section headers, and UI labels

Download the Lora font family from Google Fonts and place the .ttf files in the `fonts/` directory.

## Icons

### Tabler Icons

- **Source**: https://tabler.io/icons
- **License**: MIT License - Free to use, modify, and distribute
- **Style**: Outline icons, rendered as PNG assets at 48px (2x for retina)
- **Naming convention**: `{icon_name}_{light|dark}.png`
- **Size**: 20px rendered size (48px source downscaled)

### Required Icons

| Icon Name | Tabler Icon | Usage |
|-----------|-------------|-------|
| ti-books | books | Library button |
| ti-refresh | refresh | Refresh downloads button |
| ti-book-2 | book-2 | Open reader / Read button |
| ti-external-link | external-link | Open externally button |
| ti-download | download | Download button |
| ti-x | x | Dismiss / cancel button |
| ti-tag | tag | Add tag button |
| ti-link | link | Related documents header |
| ti-list | list | Outline header / toggle panel |
| ti-file-text | file-text | File icon (result item + library card placeholder) |
| ti-sun | sun | Light theme switch |
| ti-moon | moon | Dark theme switch |
| ti-chevron-left | chevron-left | Previous page navigation |
| ti-chevron-right | chevron-right | Next page navigation |
| ti-arrow-left | arrow-left | Back button |
| ti-minus | minus | Zoom out |
| ti-plus | plus | Zoom in |

### Icon Tinting

Icons are pre-rendered with two color variants:
- **Light theme**: Tinted to match light theme text color (#639922 for accent, gray for neutral)
- **Dark theme**: Tinted to match dark theme text color (#97C459 for accent, gray for neutral)

Use ctk.CTkImage to load the appropriate variant:
```python
ctk.CTkImage(light_image=Image.open("assets/icons/ti-books_light.png"),
            dark_image=Image.open("assets/icons/ti-books_dark.png"),
            size=(20, 20))
```

## Spine/Tag Colors

Library card spine colors are assigned deterministically by hashing the tag string:

| Color Name | Hex | Light Background | Dark Background | Light Text | Dark Text |
|------------|-----|------------------|------------------|------------|-----------|
| Teal | #0F6E56 | #E1F5EE | #0A3D2E | #04342C | #E1F5EE |
| Terracotta | #993C1D | #FAECE7 | #6A2A13 | #4A1B0C | #FAECE7 |
| Moss | #3B6D11 | #EAF3DE | #274A0C | #173404 | #EAF3DE |
| Amber | #854F0B | #FAEEDA | #5C3506 | #412402 | #FAEEDA |
| Gray (untagged) | #B4B2A9 | #E8E7E3 | #7A7870 | #5A5850 | #E8E7E3 |

The same tag always gets the same color across sessions.
