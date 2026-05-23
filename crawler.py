import requests
import os
import re
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *

import logging
import PyPDF2
import io
from PIL import Image, ImageTk
import threading
import time
from config import SERPAPI_KEY, DEFAULT_DOWNLOAD_DIR, MAX_RETRIES, TIMEOUT

# Set up logging
logging.basicConfig(
    filename='app.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class DownloadThread(threading.Thread):
    def __init__(self, url, save_path, progress_bar, root, callback):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.progress_bar = progress_bar
        self.root = root
        self.callback = callback
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            response = requests.get(self.url, stream=True, timeout=TIMEOUT)
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded_size = 0

            with open(self.save_path, 'wb') as file:
                for data in response.iter_content(chunk_size=1024):
                    if self._stop_event.is_set():
                        os.remove(self.save_path)
                        self.callback(False, "Download cancelled")
                        return
                    file.write(data)
                    downloaded_size += len(data)
                    self.progress_bar['value'] = (downloaded_size / total_size) * 100
                    self.root.update_idletasks()

            self.callback(True, "Download completed successfully")
        except Exception as e:
            self.callback(False, f"Error downloading PDF: {str(e)}")

# Function to search for PDFs using SerpApi
def search_pdfs(query):
    try:
        params = {
            "q": f"{query} filetype:pdf",
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "tbs": "qdr:y",
            "output": "json"
        }
        response = requests.get("https://serpapi.com/search", params=params, timeout=TIMEOUT)
        response.raise_for_status()
        results = response.json()

        pdf_links = []
        for result in results.get("organic_results", []):
            link = result.get("link")
            if link and link.endswith(".pdf"):
                pdf_links.append(link)
        return pdf_links
    except Exception as e:
        logging.error(f"Error occurred while searching: {e}")
        print(f"Error occurred while searching: {e}")
        return []

# Function to clean and ensure a valid file name
def clean_filename(filename):
    """Ensure valid and clean file name."""
    return re.sub(r'[\/:*?"<>|]', '_', filename)

# Function to get PDF metadata (title, author)
def get_pdf_metadata(url):
    try:
        response = requests.get(url)
        pdf = PyPDF2.PdfFileReader(io.BytesIO(response.content))
        metadata = pdf.getDocumentInfo()
        title = metadata.title if metadata.title else "Unknown Title"
        author = metadata.author if metadata.author else "Unknown Author"
        return title, author
    except Exception as e:
        logging.error(f"Error retrieving metadata: {e}")
        print(f"Error retrieving metadata: {e}")
        return "Unknown Title", "Unknown Author"

# Function to preview the first page of the PDF (using PIL and pdf2image)
def preview_pdf(url):
    try:
        response = requests.get(url)
        pdf_file = io.BytesIO(response.content)

        # Use PIL and pdf2image to convert the first page to an image
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(pdf_file.read(), first_page=1, last_page=1)
        image = pages[0]

        # Convert image to Tkinter compatible format
        image_tk = ImageTk.PhotoImage(image)

        return image_tk
    except Exception as e:
        logging.error(f"Error previewing PDF: {e}")
        print(f"Error previewing PDF: {e}")
        return None

# Function to display metadata
def display_metadata(title, author):
    metadata_window = tk.Toplevel()
    metadata_window.title("PDF Metadata")
    metadata_label = ttk.Label(metadata_window, text=f"Title: {title}\nAuthor: {author}", font=("Helvetica", 12))
    metadata_label.pack(padx=10, pady=10)

# Main GUI Application Class
class PDFDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Downloader")
        self.root.geometry("1000x700")

        # Initialize theme state (dark by default)
        self.is_dark_theme = True
        self.download_thread = None

        # Apply initial dark theme
        self.apply_theme()

        # Folder selection
        self.selected_directory = DEFAULT_DOWNLOAD_DIR
        self.pdf_links = []

        # --- Sidebar Frame ---
        self.sidebar_frame = ttkb.Frame(root, padding=20, bootstyle="secondary")
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)

        # Sidebar: Folder selection button
        self.select_folder_button = ttkb.Button(self.sidebar_frame, text="Select Folder", command=self.select_directory, bootstyle="primary-outline")
        self.select_folder_button.pack(fill=tk.X, pady=(0, 20))

        # Sidebar: Search history
        self.search_history_label = ttkb.Label(self.sidebar_frame, text="Search History:", font=("Helvetica", 12, "bold"))
        self.search_history_label.pack(anchor=tk.W, pady=(0, 5))

        self.search_history_combobox = ttkb.Combobox(self.sidebar_frame, width=25, values=[], state="readonly", font=("Helvetica", 10))
        self.search_history_combobox.pack(fill=tk.X, pady=(0, 20))

        # Sidebar: Download history
        self.download_history_label = ttkb.Label(self.sidebar_frame, text="Download History:", font=("Helvetica", 12, "bold"))
        self.download_history_label.pack(anchor=tk.W, pady=(0, 5))

        self.download_history_listbox = tk.Listbox(self.sidebar_frame, height=10, font=("Helvetica", 10))
        self.download_history_listbox.pack(fill=tk.X, pady=(0, 20))

        # Spacer
        ttkb.Frame(self.sidebar_frame).pack(expand=True, fill=tk.BOTH)

        # Sidebar: Theme Switch Button
        self.theme_switch_button = ttkb.Button(self.sidebar_frame, text="Switch Theme", command=self.switch_theme, bootstyle="info")
        self.theme_switch_button.pack(fill=tk.X, pady=10)

        # --- Main Area Frame ---
        self.main_area_frame = ttkb.Frame(root, padding=20)
        self.main_area_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Main: Search term input field
        self.search_term_label = ttkb.Label(self.main_area_frame, text="Enter the name of the PDF:", font=("Helvetica", 14, "bold"))
        self.search_term_label.pack(anchor=tk.W, pady=(0, 10))

        search_frame = ttkb.Frame(self.main_area_frame)
        search_frame.pack(fill=tk.X, pady=(0, 20))

        self.search_term_entry = ttkb.Entry(search_frame, font=("Helvetica", 12))
        self.search_term_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.search_button = ttkb.Button(search_frame, text="Search PDFs", command=self.search_pdfs, bootstyle="success")
        self.search_button.pack(side=tk.LEFT, padx=(0, 10))

        self.clear_search_button = ttkb.Button(search_frame, text="Clear", command=self.clear_search, bootstyle="secondary-outline")
        self.clear_search_button.pack(side=tk.LEFT)

        # Main: Listbox for PDF results
        self.results_label = ttkb.Label(self.main_area_frame, text="Found PDFs:", font=("Helvetica", 12, "bold"))
        self.results_label.pack(anchor=tk.W, pady=(0, 5))

        self.results_listbox = tk.Listbox(self.main_area_frame, height=15, font=("Helvetica", 10))
        self.results_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 20))

        # Main: Action buttons frame
        action_frame = ttkb.Frame(self.main_area_frame)
        action_frame.pack(fill=tk.X, pady=(0, 20))

        self.preview_button = ttkb.Button(action_frame, text="Preview PDF", command=self.preview_selected_pdf, bootstyle="info")
        self.preview_button.pack(side=tk.LEFT, padx=(0, 10))

        self.download_button = ttkb.Button(action_frame, text="Download PDF", command=self.download_pdf, bootstyle="success")
        self.download_button.pack(side=tk.LEFT, padx=(0, 10))

        self.cancel_button = ttkb.Button(action_frame, text="Cancel Download", command=self.cancel_download, state=tk.DISABLED, bootstyle="danger")
        self.cancel_button.pack(side=tk.LEFT)

        # Main: Progress bar for downloading
        self.progress = ttkb.Progressbar(self.main_area_frame, mode='determinate', bootstyle="success-striped")
        self.progress.pack(fill=tk.X, pady=(0, 10))

        # Main: Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        self.status_bar = ttkb.Label(self.main_area_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, font=("Helvetica", 10))
        self.status_bar.pack(fill=tk.X)

    def apply_theme(self):
        """Apply the appropriate theme based on the state"""
        theme_name = "darkly" if self.is_dark_theme else "litera"
        if hasattr(self.root, 'style'):
            self.root.style.theme_use(theme_name)

    def switch_theme(self):
        """Switch between dark and light themes"""
        self.is_dark_theme = not self.is_dark_theme
        self.apply_theme()

    def select_directory(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.selected_directory = folder_selected
            print(f"Selected Directory: {self.selected_directory}")
        else:
            messagebox.showwarning("No Folder", "No folder selected.")

    def preview_selected_pdf(self):
        selected_index = self.results_listbox.curselection()
        if selected_index:
            selected_link = self.pdf_links[selected_index[0]]
            image = preview_pdf(selected_link)

            if image:
                preview_window = tk.Toplevel(self.root)
                preview_window.title("PDF Preview")
                preview_label = ttk.Label(preview_window, image=image)
                preview_label.pack(padx=10, pady=10)
                preview_window.mainloop()
            else:
                messagebox.showerror("Preview Error", "Failed to preview the PDF.")
        else:
            messagebox.showwarning("No Selection", "Please select a PDF to preview.")

    def clear_search(self):
        self.results_listbox.delete(0, tk.END)
        self.pdf_links = []
        self.status_var.set("Search results cleared")

    def cancel_download(self):
        if self.download_thread and self.download_thread.is_alive():
            self.download_thread.stop()
            self.cancel_button.config(state=tk.DISABLED)
            self.download_button.config(state=tk.NORMAL)
            self.status_var.set("Download cancelled")

    def download_callback(self, success, message):
        self.status_var.set(message)
        self.cancel_button.config(state=tk.DISABLED)
        self.download_button.config(state=tk.NORMAL)
        if success:
            messagebox.showinfo("Success", message)
        else:
            messagebox.showerror("Error", message)

    def download_pdf(self):
        selected_index = self.results_listbox.curselection()
        if selected_index:
            selected_link = self.pdf_links[selected_index[0]]
            file_name = os.path.basename(selected_link)
            save_path = os.path.join(self.selected_directory if self.selected_directory else ".", file_name)

            # Initialize the progress bar
            self.progress['value'] = 0
            self.download_button.config(state=tk.DISABLED)
            self.cancel_button.config(state=tk.NORMAL)
            self.status_var.set("Downloading...")

            # Start download in a separate thread
            self.download_thread = DownloadThread(
                selected_link,
                save_path,
                self.progress,
                self.root,
                self.download_callback
            )
            self.download_thread.start()

            # Add to download history
            self.download_history_listbox.insert(tk.END, file_name)
        else:
            messagebox.showwarning("No Selection", "Please select a PDF to download.")

    def search_pdfs(self):
        search_term = self.search_term_entry.get().strip()
        if not search_term:
            messagebox.showwarning("Empty Search", "Please enter a search term")
            return

        # Add search term to history
        self.add_to_search_history(search_term)

        # Clear previous search results
        self.results_listbox.delete(0, tk.END)
        self.status_var.set("Searching...")

        # Start search in a separate thread
        threading.Thread(target=self._perform_search, args=(search_term,), daemon=True).start()

    def _perform_search(self, search_term):
        try:
            pdf_links = search_pdfs(search_term)
            self.root.after(0, self._update_search_results, pdf_links)
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Search error: {str(e)}"))

    def _update_search_results(self, pdf_links):
        if pdf_links:
            self.pdf_links = pdf_links
            for idx, link in enumerate(pdf_links):
                self.results_listbox.insert(tk.END, f"{idx + 1}. {link}")
            self.status_var.set(f"Found {len(pdf_links)} PDFs")
        else:
            self.status_var.set("No PDFs found")
            messagebox.showinfo("No Results", "No PDFs found. Please try another search term.")

    def add_to_search_history(self, search_term):
        # Add search term to history list
        if search_term not in self.search_history_combobox['values']:
            self.search_history_combobox['values'] = list(self.search_history_combobox['values']) + [search_term]

# Create the main window and run the app
if __name__ == "__main__":
    root = ttkb.Window(themename="darkly")
    app = PDFDownloaderApp(root)
    root.mainloop()
