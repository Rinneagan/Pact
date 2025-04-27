import requests
import os
import re
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from serpapi import GoogleSearch
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
            "api_key": SERPAPI_KEY,  # Using the hardcoded API key
            "engine": "google",
            "tbs": "qdr:y"  # Filter results for the last year
        }

        search = GoogleSearch(params)
        results = search.get_dict()

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
        self.root.geometry("800x600")

        # Initialize theme state (dark by default)
        self.is_dark_theme = True
        self.download_thread = None

        # Apply initial dark theme
        self.apply_theme()

        # Folder selection
        self.selected_directory = DEFAULT_DOWNLOAD_DIR

        # Create main frame
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Search term input field
        self.search_term_label = ttk.Label(self.main_frame, text="Enter the name of the PDF:")
        self.search_term_label.pack(pady=5)
        self.search_term_entry = ttk.Entry(self.main_frame, width=50, font=("Helvetica", 12))
        self.search_term_entry.pack(pady=5)

        # Search Button
        self.search_button = ttk.Button(self.main_frame, text="Search PDFs", command=self.search_pdfs)
        self.search_button.pack(pady=10)

        # Clear Search Button
        self.clear_search_button = ttk.Button(self.main_frame, text="Clear Search", command=self.clear_search)
        self.clear_search_button.pack(pady=5)

        # Listbox for PDF results
        self.results_label = ttk.Label(self.main_frame, text="Found PDFs:")
        self.results_label.pack(pady=5)
        self.results_listbox = tk.Listbox(self.main_frame, width=80, height=10, font=("Helvetica", 10))
        self.results_listbox.pack(pady=5)

        # Preview PDF Button
        self.preview_button = ttk.Button(self.main_frame, text="Preview PDF", command=self.preview_selected_pdf)
        self.preview_button.pack(pady=5)

        # Download Button
        self.download_button = ttk.Button(self.main_frame, text="Download PDF", command=self.download_pdf)
        self.download_button.pack(pady=10)

        # Cancel Download Button
        self.cancel_button = ttk.Button(self.main_frame, text="Cancel Download", command=self.cancel_download, state=tk.DISABLED)
        self.cancel_button.pack(pady=5)

        # Progress bar for downloading
        self.progress = ttk.Progressbar(self.main_frame, length=200, mode='determinate')
        self.progress.pack(pady=10)

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        self.status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Folder selection button
        self.select_folder_button = ttk.Button(self.main_frame, text="Select Folder", command=self.select_directory)
        self.select_folder_button.pack(pady=10)

        # Search history label
        self.search_history_label = ttk.Label(self.main_frame, text="Search History:")
        self.search_history_label.pack(pady=5)

        # History combobox (dropdown) for previous search terms
        self.search_history_combobox = ttk.Combobox(self.main_frame, width=50, values=[], state="readonly", font=("Helvetica", 10))
        self.search_history_combobox.pack(pady=5)

        self.pdf_links = []

        # Download history listbox
        self.download_history_label = ttk.Label(self.main_frame, text="Download History:")
        self.download_history_label.pack(pady=5)

        self.download_history_listbox = tk.Listbox(self.main_frame, width=80, height=5, font=("Helvetica", 10))
        self.download_history_listbox.pack(pady=5)

        # Theme Switch Button
        self.theme_switch_button = ttk.Button(self.main_frame, text="Switch Theme", command=self.switch_theme)
        self.theme_switch_button.pack(pady=15)

    def apply_theme(self):
        """Apply the appropriate theme based on the state"""
        if self.is_dark_theme:
            self.style = ttk.Style()
            self.style.theme_use("clam")
            self.style.configure("TButton", background="#3e8e41", foreground="white", font=("Helvetica", 12))
            self.style.configure("TLabel", font=("Helvetica", 12), background="#2b2b2b", foreground="white")
            self.style.configure("TProgressbar", thickness=30, background="green")
        else:
            self.style = ttk.Style()
            self.style.theme_use("clam")
            self.style.configure("TButton", background="#f0f0f0", foreground="black", font=("Helvetica", 12))
            self.style.configure("TLabel", font=("Helvetica", 12), background="#ffffff", foreground="black")
            self.style.configure("TProgressbar", thickness=30, background="lightblue")

        # Reconfigure the widgets after applying the theme
        self.root.configure(bg="#2b2b2b" if self.is_dark_theme else "#ffffff")

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
    root = tk.Tk()
    app = PDFDownloaderApp(root)
    root.mainloop()
