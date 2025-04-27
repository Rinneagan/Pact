# PDF Downloader

A Python application for searching and downloading PDF files with a modern GUI interface.

## Features

- Search for PDFs using Google Search API
- Preview PDFs before downloading
- Download PDFs with progress bar
- Dark/Light theme support
- Search history
- Download history
- Cancelable downloads
- Status bar for operation feedback

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory with your SerpApi key:
   ```
   SERPAPI_KEY=your_api_key_here
   ```

## Usage

1. Run the application:
   ```bash
   python crawler.py
   ```
2. Enter a search term in the search box
3. Select a PDF from the results
4. Use the Preview button to view the PDF
5. Click Download to save the PDF
6. Use the Theme button to switch between dark and light themes

## Requirements

- Python 3.7+
- Internet connection
- SerpApi API key

## Notes

- The application uses SerpApi for PDF searches
- Downloaded PDFs are saved to the selected directory (default: Downloads folder)
- Search history is maintained between sessions
- Downloads can be cancelled during the process 