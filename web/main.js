/* Pact Frontend JS Controller */

// Global State
let appState = {
    currentTab: 'search-library',
    theme: 'dark',
    activeSearch: false,
    searchResults: [],
    searchHistory: [],
    
    // PDF Reader State
    readerActive: false,
    readerFilepath: '',
    readerTitle: '',
    readerPage: 0,
    readerTotalPages: 0,
    readerZoom: 2.0,
    readerSidePanel: true,
    readerTab: 'outline',
    
    // Modal state
    tagTargetFilepath: ''
};

// Initialize app when pywebview is ready
window.addEventListener('pywebviewready', () => {
    initApp();
});

function initApp() {
    // Load logos
    pywebview.api.get_logos().then(logos => {
        appState.logos = logos || {light: '', dark: ''};
        updateLogoUI();
    });

    // 1. Load theme
    pywebview.api.get_theme().then(theme => {
        setThemeMode(theme || 'dark');
    });

    // Load Wallpaper
    const savedWallpaper = localStorage.getItem('pact_wallpaper') || 'none';
    changeWallpaper(savedWallpaper);

    // 2. Load lists & stats
    refreshLibrary();
    refreshContinueReading();
    refreshSearchHistory();
    refreshStats();
    
    // 3. Start active downloads polling loop
    startDownloadsPolling();
}

/* THEME MANAGEMENT */
function setThemeMode(theme) {
    appState.theme = theme;
    const body = document.body;
    if (theme === 'light') {
        body.classList.remove('dark-theme');
        body.classList.add('light-theme');
    } else {
        body.classList.remove('light-theme');
        body.classList.add('dark-theme');
    }
    updateLogoUI();
}

function updateLogoUI() {
    const logoImg = document.getElementById('logo-img');
    if (!logoImg || !appState.logos) return;
    
    const logoData = appState.theme === 'light' ? appState.logos.light : appState.logos.dark;
    if (logoData) {
        const mime = logoData.startsWith('/9j/') ? 'image/jpeg' : 'image/png';
        logoImg.src = `data:${mime};base64,${logoData}`;
        logoImg.classList.remove('hidden');
    } else {
        logoImg.classList.add('hidden');
    }
}

function toggleTheme() {
    const nextTheme = appState.theme === 'dark' ? 'light' : 'dark';
    setThemeMode(nextTheme);
    pywebview.api.set_theme(nextTheme).then(() => {
        // If reader is active, refresh the page rendering to flip colors (inverted dark mode)
        if (appState.readerActive) {
            renderReaderPage();
        }
    });
}

/* TAB NAVIGATION */
function switchMainTab(tabId) {
    if (appState.readerActive) {
        closeReader();
    }
    
    appState.currentTab = tabId;
    
    // Toggle active class on nav buttons
    document.querySelectorAll('.sidebar-nav .nav-button').forEach(btn => {
        btn.classList.remove('active');
    });
    const activeBtn = document.getElementById(`nav-${tabId === 'search-library' ? 'search-library' : 'stats'}`);
    if (activeBtn) activeBtn.classList.add('active');

    // Toggle tab visibility
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });
    document.getElementById(`tab-${tabId}`).classList.remove('hidden');

    if (tabId === 'stats') {
        refreshStats();
    } else {
        refreshLibrary();
    }
}

/* TOAST NOTIFICATION */
function showToast(message, isError = false) {
    const toast = document.getElementById('status-toast');
    toast.textContent = message;
    toast.className = isError ? 'toast-visible error' : 'toast-visible';
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
        toast.className = 'toast-hidden';
    }, 4000);
}

/* SEARCH & SUGGESTIONS */
function handleSearchKey(event) {
    if (event.key === 'Enter') {
        performSearch();
    }
}

function performSearch() {
    const input = document.getElementById('search-input');
    const query = input.value.trim();
    if (!query) {
        showToast('Please enter a search term', true);
        return;
    }

    // Toggle view to search results split
    document.getElementById('library-section').classList.add('hidden');
    const resultsSection = document.getElementById('search-results-section');
    resultsSection.classList.remove('hidden');
    document.getElementById('search-results-list').classList.add('hidden');
    document.getElementById('skeleton-loader').classList.remove('hidden');
    document.getElementById('results-heading').textContent = `Search Results for "${query}"`;

    pywebview.api.search(query).then(results => {
        appState.searchResults = results || [];
        renderSearchResults();
        refreshSearchHistory();
    }).catch(err => {
        showToast(`Search failed: ${err}`, true);
        closeSearchResults();
    });
}

function closeSearchResults() {
    document.getElementById('search-results-section').classList.add('hidden');
    document.getElementById('library-section').classList.remove('hidden');
    document.getElementById('search-input').value = '';
}

function renderSearchResults() {
    document.getElementById('skeleton-loader').classList.add('hidden');
    const list = document.getElementById('search-results-list');
    list.innerHTML = '';
    list.classList.remove('hidden');

    if (appState.searchResults.length === 0) {
        list.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 40px;">No PDFs found.</div>';
        return;
    }

    appState.searchResults.forEach((url, idx) => {
        // Extract a clean name for display
        let displayName = 'document_' + (idx + 1) + '.pdf';
        try {
            const urlPath = new URL(url).pathname;
            const basename = urlPath.substring(urlPath.lastIndexOf('/') + 1);
            if (basename && basename.toLowerCase().endsWith('.pdf')) {
                displayName = decodeURIComponent(basename);
            }
        } catch(e) {}
        
        // Clean display name
        displayName = displayName.replace(/[\\/:*?"<>|]/g, '_');
        if (displayName.length > 50) displayName = displayName.substring(0, 47) + '...';

        const card = document.createElement('div');
        card.className = 'result-card';
        card.onclick = () => selectAndDownloadPdf(url, displayName);

        card.innerHTML = `
            <div class="result-main">
                <svg class="result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                    <polyline points="10 9 9 9 8 9"/>
                </svg>
                <div class="result-info">
                    <span class="result-title">${idx + 1}. ${displayName}</span>
                    <span class="result-url">${url}</span>
                </div>
            </div>
            <button class="result-download-btn" title="Download Document" onclick="event.stopPropagation(); triggerDownload('${url}', '${displayName}')">
                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                </svg>
            </button>
        `;
        list.appendChild(card);
    });
}

function refreshSearchHistory() {
    pywebview.api.get_recent_searches().then(history => {
        const container = document.getElementById('search-history');
        container.innerHTML = '';
        if (history) {
            history.forEach(term => {
                const chip = document.createElement('div');
                chip.className = 'chip';
                chip.textContent = term;
                chip.onclick = () => {
                    document.getElementById('search-input').value = term;
                    performSearch();
                };
                container.appendChild(chip);
            });
        }
    });
}

/* DOWNLOADS QUEUE & POLLING */
function triggerDownload(url, title) {
    pywebview.api.download(url, title).then(res => {
        if (res && res.error) {
            showToast(res.error, true);
        } else {
            showToast(`Started download: ${title}`);
            document.getElementById('downloads-shelf').classList.remove('hidden');
        }
    });
}

function selectAndDownloadPdf(url, title) {
    // Standard double action: select and download
    triggerDownload(url, title);
}
function cancelDownload(downloadId) {
    pywebview.api.cancel_download(downloadId).then(() => {
        showToast('Download cancelled');
        if (appState.downloads && appState.downloads[downloadId]) {
            delete appState.downloads[downloadId];
        }
    });
}

function startDownloadsPolling() {
    if (!appState.downloads) {
        appState.downloads = {};
    }
    
    setInterval(() => {
        pywebview.api.get_active_downloads().then(downloads => {
            const container = document.getElementById('downloads-list');
            const shelf = document.getElementById('downloads-shelf');
            
            // Merge response into appState.downloads
            if (downloads) {
                Object.keys(downloads).forEach(id => {
                    const item = downloads[id];
                    if (item.failed) {
                        showToast(`Download failed: ${item.error_msg}`, true);
                        delete appState.downloads[id];
                    } else if (!item.active && !item.complete) {
                        delete appState.downloads[id];
                    } else {
                        // If it just transitioned to complete, refresh the library grid
                        if (item.complete && (!appState.downloads[id] || !appState.downloads[id].complete)) {
                            refreshLibrary();
                        }
                        appState.downloads[id] = item;
                    }
                });
            }
            
            const keys = Object.keys(appState.downloads);
            if (keys.length === 0) {
                shelf.classList.add('hidden');
                container.innerHTML = '';
                return;
            }
            
            shelf.classList.remove('hidden');
            
            // Remove DOM cards that are no longer in appState.downloads
            const existingCards = container.querySelectorAll('.download-card');
            existingCards.forEach(card => {
                const cardId = card.getAttribute('data-download-id');
                if (!appState.downloads[cardId]) {
                    card.remove();
                }
            });

            // Add or update cards without rebuilding DOM structure unnecessarily
            keys.forEach(id => {
                const item = appState.downloads[id];
                let card = container.querySelector(`.download-card[data-download-id="${id}"]`);
                
                if (!card) {
                    card = document.createElement('div');
                    card.className = 'download-card';
                    card.setAttribute('data-download-id', id);
                    container.appendChild(card);
                }

                const currentStatus = card.getAttribute('data-status');
                const targetStatus = item.complete ? 'complete' : `downloading-${Math.round(item.progress || 0)}`;

                if (currentStatus !== targetStatus) {
                    card.setAttribute('data-status', targetStatus);
                    if (item.complete) {
                        card.innerHTML = `
                            <div class="download-info">
                                <div class="download-title">${item.filename}</div>
                                <div class="progress-bar-container">
                                    <div class="progress-bar-fill" style="width: 100%; background-color: #639922;"></div>
                                </div>
                            </div>
                            <div class="download-actions" style="display: flex; gap: 4px; align-items: center;">
                                <button class="read-btn" onclick="openReaderAndClearShelf('${id}', '${item.save_path.replace(/\\/g, '\\\\')}', '${item.filename.replace(/'/g, "\\'")}')">📖 Read</button>
                                <button class="cancel-btn" onclick="dismissCompletedDownload('${id}')" title="Dismiss">✕</button>
                            </div>
                        `;
                    } else {
                        const pct = Math.round(item.progress || 0);
                        card.innerHTML = `
                            <div class="download-info">
                                <div class="download-title">${item.filename} (${pct}%)</div>
                                <div class="progress-bar-container">
                                    <div class="progress-bar-fill" style="width: ${pct}%"></div>
                                </div>
                            </div>
                            <div class="download-actions">
                                <button class="cancel-btn" onclick="cancelDownload('${id}')" title="Cancel Download">✕</button>
                            </div>
                        `;
                    }
                }
            });
        });
    }, 500);
}

function openReaderAndClearShelf(id, filepath, filename) {
    dismissCompletedDownload(id);
    openReader(filepath, filename);
}

function dismissCompletedDownload(id) {
    if (appState.downloads && appState.downloads[id]) {
        delete appState.downloads[id];
    }
}


/* LIBRARY GRID */
function refreshLibrary() {
    pywebview.api.get_downloads().then(files => {
        const grid = document.getElementById('library-grid');
        grid.innerHTML = '';

        if (!files || files.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 40px; line-height: 1.6;">Your library is empty.<br>Search and download PDFs, or drag a PDF in, to get started.</div>';
            return;
        }

        // We fetch tags and bookmarks to group them
        pywebview.api.get_all_tags().then(tagsMap => {
            // Split files into tagged groups and buckets
            let taggedGroups = {};
            let untagged = [];

            files.forEach(f => {
                const fpath = f.filepath;
                const tags = tagsMap[fpath] || [];
                if (tags.length > 0) {
                    tags.forEach(t => {
                        if (!taggedGroups[t]) taggedGroups[t] = [];
                        taggedGroups[t].push(f);
                    });
                } else {
                    untagged.push(f);
                }
            });

            // 1. Render Tagged Groups
            Object.keys(taggedGroups).sort().forEach(tag => {
                renderLibrarySection(`🏷 ${tag}`, taggedGroups[tag], tagsMap);
            });

            // 2. Render Recency Buckets
            let buckets = {
                "Today": [],
                "Yesterday": [],
                "This Week": [],
                "This Month": [],
                "Earlier": []
            };

            const now = new Date();
            untagged.forEach(f => {
                const mtime = new Date(f.mtime * 1000);
                const diffTime = Math.abs(now - mtime);
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

                if (diffDays <= 1) buckets["Today"].push(f);
                else if (diffDays <= 2) buckets["Yesterday"].push(f);
                else if (diffDays <= 7) buckets["This Week"].push(f);
                else if (diffDays <= 30) buckets["This Month"].push(f);
                else buckets["Earlier"].push(f);
            });

            ["Today", "Yesterday", "This Week", "This Month", "Earlier"].forEach(bucket => {
                if (buckets[bucket].length > 0) {
                    renderLibrarySection(bucket, buckets[bucket], tagsMap);
                }
            });
        });
    });
}

function renderLibrarySection(header, items, tagsMap) {
    const grid = document.getElementById('library-grid');
    
    const wrapper = document.createElement('div');
    wrapper.className = 'library-bucket';
    wrapper.innerHTML = `<div class="bucket-title">${header}</div>`;
    
    const container = document.createElement('div');
    container.className = 'grid-container';
    
    items.forEach(f => {
        const card = document.createElement('div');
        card.className = 'library-card';
        card.onclick = () => openReader(f.filepath, f.filename);

        // Determine spine color based on tag hash
        const tags = tagsMap[f.filepath] || [];
        const spineColor = getSpineColor(tags[0] || '');
        
        let display = f.filename;
        if (display.length > 25) display = display.substring(0, 22) + '...';

        card.innerHTML = `
            <div class="card-spine" style="background-color: ${spineColor};"></div>
            <div class="card-body">
                <div class="card-thumbnail-container" id="thumb-${btoa(f.filepath).replace(/=/g, '')}">
                    <svg class="card-thumbnail-fallback" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                </div>
                <span class="card-title" title="${f.filename}">${display}</span>
                <div class="card-footer">
                    <span class="card-tags">${tags.slice(0, 2).map(t => `#${t}`).join(' ')}</span>
                    <button class="card-tag-btn" title="Add tag" onclick="event.stopPropagation(); promptAddTag('${f.filepath}')">
                        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
        container.appendChild(card);
        
        // Lazy load thumbnail
        loadThumbnail(f.filepath, btoa(f.filepath).replace(/=/g, ''));
    });

    wrapper.appendChild(container);
    grid.appendChild(wrapper);
}

function loadThumbnail(filepath, base64Id) {
    pywebview.api.get_thumbnail(filepath).then(imgBase64 => {
        if (imgBase64) {
            const container = document.getElementById(`thumb-${base64Id}`);
            if (container) {
                container.innerHTML = `<img src="data:image/jpeg;base64,${imgBase64}" alt="thumbnail">`;
            }
        }
    });
}

function getSpineColor(tag) {
    const colors = [
        '#00E5FF', // Neon Cyan
        '#9D00FF', // Neon Purple
        '#00E676', // Teal / Neon Green
        '#FF9100', // Terracotta / Neon Orange
        '#A8E6CF', // Moss / Green
        '#FF8A8A', // Red / Coral
        '#FFC38A', // Orange
        '#FFEAA7', // Yellow
        '#A2D5F2'  // Blue
    ];
    if (!tag) return 'var(--border)';
    let sum = 0;
    for (let i = 0; i < tag.length; i++) sum += tag.charCodeAt(i);
    return colors[sum % colors.length];
}

/* CONTINUE READING SHELF */
function refreshContinueReading() {
    pywebview.api.get_reading_progress().then(progressItems => {
        const container = document.getElementById('continue-list');
        const shelf = document.getElementById('continue-shelf');
        
        if (!progressItems || progressItems.length === 0) {
            shelf.classList.add('hidden');
            container.innerHTML = '';
            return;
        }

        shelf.classList.remove('hidden');
        container.innerHTML = '';

        progressItems.forEach(item => {
            const fpath = item[0];
            const info = item[1];
            const title = info.title || fpath.substring(fpath.lastIndexOf('\\') + 1);
            let display = title;
            if (display.length > 25) display = display.substring(0, 22) + '...';
            
            const total = Math.max(info.total_pages || 1, 1);
            const current = info.current_page || 0;
            const pct = Math.min(100, Math.round(((current + 1) / total) * 100));

            const card = document.createElement('div');
            card.className = 'continue-card';
            card.onclick = () => openReader(fpath, title);

            card.innerHTML = `
                <div class="continue-header">
                    <span class="continue-title" title="${title}">${display}</span>
                    <button class="continue-close" onclick="event.stopPropagation(); dismissContinueReading('${fpath}')">✕</button>
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar-fill" style="width: ${pct}%"></div>
                </div>
            `;
            container.appendChild(card);
        });
    });
}

function dismissContinueReading(filepath) {
    pywebview.api.remove_reading_progress(filepath).then(() => {
        refreshContinueReading();
    });
}

/* TAG PROMPT MODAL */
function promptAddTag(filepath) {
    appState.tagTargetFilepath = filepath;
    document.getElementById('tag-input').value = '';
    document.getElementById('tag-modal').classList.remove('hidden');
    document.getElementById('tag-input').focus();
}

function handleTagKey(event) {
    if (event.key === 'Enter') saveTagPrompt();
}

function saveTagPrompt() {
    const tag = document.getElementById('tag-input').value.trim();
    if (tag) {
        pywebview.api.add_tag(appState.tagTargetFilepath, tag).then(() => {
            closeTagModal();
            refreshLibrary();
            showToast(`Added tag #${tag}`);
        });
    } else {
        closeTagModal();
    }
}

function closeTagModal() {
    document.getElementById('tag-modal').classList.add('hidden');
}

/* STATS TAB */
function refreshStats() {
    pywebview.api.get_reading_stats().then(stats => {
        if (!stats) return;
        
        document.getElementById('stats-finished-month').textContent = stats.finished_this_month || 0;
        
        const longestReadTitle = document.getElementById('stats-longest-read-title');
        const longestReadPages = document.getElementById('stats-longest-read-pages');
        
        if (stats.longest_read) {
            longestReadPages.textContent = stats.longest_read[1];
            longestReadTitle.textContent = `Longest Read: ${stats.longest_read[0]}`;
        } else {
            longestReadPages.textContent = '—';
            longestReadTitle.textContent = 'Longest Read';
        }

        // Render bars
        const barsContainer = document.getElementById('stats-bars');
        barsContainer.innerHTML = '';
        
        if (stats.weekly_pages) {
            const maxVal = Math.max(...stats.weekly_pages, 1);
            const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            const todayIdx = new Date().getDay();
            
            stats.weekly_pages.forEach((val, i) => {
                const dayLabel = days[(todayIdx - (6 - i) + 7) % 7];
                const pct = Math.round((val / maxVal) * 100);
                
                const wrapper = document.createElement('div');
                wrapper.className = 'bar-wrapper';
                wrapper.innerHTML = `
                    <span class="bar-val">${val || ''}</span>
                    <div class="bar-pill-container">
                        <div class="bar-fill" style="height: ${pct}%"></div>
                    </div>
                    <span class="bar-label">${dayLabel}</span>
                `;
                barsContainer.appendChild(wrapper);
            });
        }
    });

    // Load contribution heatmap activity
    pywebview.api.get_heatmap_data().then(data => {
        renderHeatmap(data);
    });
}

/* PDF READER VIEW */
function openReader(filepath, title) {
    appState.readerActive = true;
    appState.readerFilepath = filepath;
    appState.readerTitle = title;
    appState.readerZoom = 2.0;
    
    // Switch to page 0 or load from progress store
    pywebview.api.get_document_progress(filepath).then(progress => {
        appState.readerPage = (progress && progress.current_page) ? progress.current_page : 0;
        
        document.getElementById('reader-document-title').textContent = title;
        document.getElementById('reader-view').classList.remove('hidden');
        
        // Load contents
        refreshReaderPage();
        loadReaderToc();
        loadReaderRelated();
        loadReaderNotes();
        loadReaderKeywords();
    });
}

function closeReader() {
    appState.readerActive = false;
    document.getElementById('reader-view').classList.add('hidden');
    
    // Reset focus mode if active
    const reader = document.getElementById('reader-view');
    if (reader && reader.classList.contains('focus-mode')) {
        reader.classList.remove('focus-mode');
        const btn = document.getElementById('focus-mode-btn');
        if (btn) {
            btn.classList.remove('active');
            btn.style.color = '';
        }
    }
    
    // Auto-fade-out and stop ambient audio if playing when reader is closed
    const audio = document.getElementById('zen-audio-element');
    if (audio && !audio.paused) {
        fadeAudio(audio, 0, 800, () => {
            audio.pause();
            zenAudioState.isPlaying = false;
            const playBtn = document.querySelector('.zen-play-btn .play-icon');
            const pauseBtn = document.querySelector('.zen-play-btn .pause-icon');
            if (playBtn) playBtn.classList.remove('hidden');
            if (pauseBtn) pauseBtn.classList.add('hidden');
        });
    }
    
    clearKeywordSearch();

    pywebview.api.close_document();
    
    // Refresh lists on exit
    refreshContinueReading();
    refreshLibrary();
}

function toggleReaderSidePanel() {
    appState.readerSidePanel = !appState.readerSidePanel;
    const panel = document.getElementById('reader-side-panel');
    const btn = document.getElementById('toggle-panel-btn');
    if (appState.readerSidePanel) {
        panel.classList.remove('collapsed');
        btn.classList.add('active');
    } else {
        panel.classList.add('collapsed');
        btn.classList.remove('active');
    }
}

function switchReaderTab(tabId) {
    appState.readerTab = tabId;
    document.querySelectorAll('.tabs-header .tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById(`tab-btn-${tabId}`).classList.add('active');

    document.querySelectorAll('.reader-tab-content').forEach(content => {
        content.classList.add('hidden');
    });
    document.getElementById(`reader-tab-${tabId}`).classList.remove('hidden');
}

function zoomReader(delta) {
    appState.readerZoom = Math.min(4.0, Math.max(1.0, appState.readerZoom + delta));
    document.getElementById('zoom-value').textContent = `${Math.round(appState.readerZoom * 50)}%`;
    renderReaderPage();
}

function navigateReaderPage(dir) {
    const nextPage = appState.readerPage + dir;
    if (nextPage >= 0 && nextPage < appState.readerTotalPages) {
        appState.readerPage = nextPage;
        refreshReaderPage();
    }
}

function refreshReaderPage() {
    // Resolve pages total from API first if unknown
    if (appState.readerTotalPages === 0) {
        pywebview.api.get_total_pages(appState.readerFilepath).then(total => {
            appState.readerTotalPages = total;
            document.getElementById('reader-page-indicator').textContent = `${appState.readerPage + 1} / ${total}`;
            renderReaderPage();
        });
    } else {
        document.getElementById('reader-page-indicator').textContent = `${appState.readerPage + 1} / ${appState.readerTotalPages}`;
        renderReaderPage();
    }
    
    // Update toolbar controls status
    updateReaderNavControls();
    updateBookmarkButtonUI();
}

function updateReaderNavControls() {
    const prevBtn = document.getElementById('reader-prev-btn');
    const nextBtn = document.getElementById('reader-next-btn');
    prevBtn.disabled = appState.readerPage === 0;
    nextBtn.disabled = appState.readerPage === appState.readerTotalPages - 1;
}

function renderReaderPage() {
    const imgEl = document.getElementById('pdf-page-img');
    pywebview.api.get_page_image(appState.readerFilepath, appState.readerPage, appState.readerZoom, appState.theme === 'dark').then(base64Data => {
        if (base64Data) {
            imgEl.src = `data:image/png;base64,${base64Data}`;
        }
    });
}

function loadReaderToc() {
    pywebview.api.get_toc(appState.readerFilepath).then(toc => {
        const container = document.getElementById('outline-container');
        container.innerHTML = '';
        if (!toc || toc.length === 0) {
            container.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); padding: 10px;">No outline available</div>';
            return;
        }

        toc.slice(0, 100).forEach(item => {
            const level = item[0];
            const title = item[1];
            const page = item[2];

            const btn = document.createElement('button');
            btn.className = `outline-item level-${level}`;
            btn.style.paddingLeft = `${Math.max(level - 1, 0) * 12 + 12}px`;
            btn.textContent = title;
            btn.onclick = () => {
                appState.readerPage = page - 1;
                refreshReaderPage();
            };
            container.appendChild(btn);
        });
    });
}

function loadReaderRelated() {
    pywebview.api.get_related(appState.readerFilepath).then(related => {
        const container = document.getElementById('related-container');
        container.innerHTML = '';
        if (!related || related.length === 0) {
            container.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); padding: 10px;">No related documents found</div>';
            return;
        }

        related.forEach(item => {
            const path = item[0];
            const name = item[1];

            const btn = document.createElement('button');
            btn.className = 'related-item';
            btn.innerHTML = `
                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3"/>
                </svg>
                ${name}
            `;
            btn.onclick = () => {
                // Open related document inside reader
                appState.readerTotalPages = 0; // reset page count
                openReader(path, name);
            };
            container.appendChild(btn);
        });
    });
}

/* BOOKMARKS & NOTES IN READER */
function updateBookmarkButtonUI() {
    pywebview.api.get_bookmarks(appState.readerFilepath).then(bookmarks => {
        const isBookmarked = bookmarks.some(b => b.page === appState.readerPage);
        const btn = document.getElementById('reader-bookmark-btn');
        if (isBookmarked) {
            btn.classList.add('active');
            btn.style.color = 'var(--accent-secondary)';
        } else {
            btn.classList.remove('active');
            btn.style.color = '';
        }
    });
}

function toggleCurrentPageBookmark() {
    pywebview.api.get_bookmarks(appState.readerFilepath).then(bookmarks => {
        const idx = bookmarks.findIndex(b => b.page === appState.readerPage);
        if (idx !== -1) {
            pywebview.api.remove_bookmark(appState.readerFilepath, appState.readerPage).then(() => {
                updateBookmarkButtonUI();
                loadReaderNotes();
            });
        } else {
            pywebview.api.add_bookmark(appState.readerFilepath, appState.readerPage, '').then(() => {
                updateBookmarkButtonUI();
                loadReaderNotes();
                switchReaderTab('notes');
            });
        }
    });
}

function loadReaderNotes() {
    pywebview.api.get_bookmarks(appState.readerFilepath).then(bookmarks => {
        const container = document.getElementById('notes-container');
        container.innerHTML = '';
        
        if (!bookmarks || bookmarks.length === 0) {
            container.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 20px;">No bookmarks or notes.<br>Click 🔖 or type above to add a note.</div>';
            return;
        }

        bookmarks.forEach(b => {
            const card = document.createElement('div');
            card.className = 'note-card';
            card.onclick = () => {
                appState.readerPage = b.page;
                refreshReaderPage();
            };

            card.innerHTML = `
                <div class="note-card-header">
                    <span class="note-card-title">Page ${b.page + 1}</span>
                    <button class="note-card-del" title="Delete note/bookmark" onclick="event.stopPropagation(); deleteBookmark(${b.page})">
                        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"/>
                            <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>
                </div>
                ${b.note ? `<div class="note-card-body">${b.note}</div>` : ''}
            `;
            container.appendChild(card);
        });
    });
}

function handleNoteKey(event) {
    if (event.key === 'Enter') saveCurrentNote();
}

function saveCurrentNote() {
    const input = document.getElementById('note-entry');
    const text = input.value.trim();
    if (!text) return;

    pywebview.api.add_bookmark(appState.readerFilepath, appState.readerPage, text).then(() => {
        input.value = '';
        loadReaderNotes();
        updateBookmarkButtonUI();
        showToast('Saved note');
    });
}

function deleteBookmark(pageIndex) {
    pywebview.api.remove_bookmark(appState.readerFilepath, pageIndex).then(() => {
        loadReaderNotes();
        updateBookmarkButtonUI();
    });
}

/* PREMIUM ADDITIONS IMPLEMENTATION */

function changeWallpaper(name) {
    const body = document.body;
    const bg = document.getElementById('app-bg');
    if (!bg) return;
    
    // Clear existing classes
    bg.className = '';
    body.classList.remove('has-wallpaper');
    
    if (name && name !== 'none') {
        bg.classList.add(name);
        body.classList.add('has-wallpaper');
        localStorage.setItem('pact_wallpaper', name);
    } else {
        localStorage.removeItem('pact_wallpaper');
    }
    
    // Sync selector value
    const select = document.getElementById('wallpaper-select');
    if (select) select.value = name || 'none';
}

function toggleFocusMode() {
    const reader = document.getElementById('reader-view');
    if (!reader) return;
    
    const isFocus = reader.classList.toggle('focus-mode');
    const btn = document.getElementById('focus-mode-btn');
    
    if (isFocus) {
        btn.classList.add('active');
        btn.style.color = 'var(--accent-primary)';
        showToast('Entering Deep Focus Mode. Hover near top to show toolbar. Press Esc to exit.');
        
        // Auto-show zen audio panel in Focus Mode
        const zenPanel = document.getElementById('zen-audio-panel');
        if (zenPanel) zenPanel.classList.remove('hidden');
    } else {
        btn.classList.remove('active');
        btn.style.color = '';
        showToast('Exited Focus Mode');
        
        // Auto-fade-out and stop ambient audio if playing
        const audio = document.getElementById('zen-audio-element');
        if (audio && !audio.paused) {
            fadeAudio(audio, 0, 800, () => {
                audio.pause();
                zenAudioState.isPlaying = false;
                const playBtn = document.querySelector('.zen-play-btn .play-icon');
                const pauseBtn = document.querySelector('.zen-play-btn .pause-icon');
                if (playBtn) playBtn.classList.remove('hidden');
                if (pauseBtn) pauseBtn.classList.add('hidden');
            });
        }
    }
}

// Global Esc key listener for exiting focus mode
window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        const reader = document.getElementById('reader-view');
        if (reader && reader.classList.contains('focus-mode')) {
            toggleFocusMode();
        }
    }
});

function renderHeatmap(data) {
    const container = document.getElementById('stats-heatmap');
    if (!container) return;
    container.innerHTML = '';
    
    if (!data || data.length === 0) {
        container.innerHTML = '<div style="font-size: 12px; color: var(--text-muted); padding: 20px; grid-column: 1/-1;">No activity data available</div>';
        return;
    }
    
    // Pad start of the grid to align days of week to rows (Sun-Sat)
    const firstDate = new Date(data[0].date);
    const padCount = firstDate.getDay(); // 0 is Sunday, 1 is Monday, etc.
    for (let p = 0; p < padCount; p++) {
        const padCell = document.createElement('div');
        padCell.className = 'heatmap-cell';
        padCell.style.visibility = 'hidden';
        container.appendChild(padCell);
    }
    
    data.forEach(item => {
        const cell = document.createElement('div');
        cell.className = 'heatmap-cell';
        
        let level = 0;
        if (item.count > 0 && item.count <= 2) {
            level = 1;
        } else if (item.count > 2 && item.count <= 5) {
            level = 2;
        } else if (item.count > 5 && item.count <= 10) {
            level = 3;
        } else if (item.count > 10) {
            level = 4;
        }
        
        cell.classList.add(`level-${level}`);
        
        let dateStr = item.date;
        try {
            const d = new Date(item.date);
            dateStr = d.toLocaleDateString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
        } catch (e) {}
        
        cell.title = `${dateStr}: ${item.count} page${item.count === 1 ? '' : 's'} read`;
        container.appendChild(cell);
    });
}

function loadReaderKeywords() {
    const container = document.getElementById('keywords-cloud');
    const matchesContainer = document.getElementById('keyword-matches');
    if (!container) return;
    
    container.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); padding: 10px;">Extracting keywords...</div>';
    matchesContainer.classList.add('hidden');
    
    pywebview.api.get_keywords(appState.readerFilepath).then(keywords => {
        container.innerHTML = '';
        
        if (!keywords || keywords.length === 0) {
            container.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); padding: 10px;">No keywords extracted</div>';
            return;
        }
        
        keywords.forEach(item => {
            const tag = document.createElement('span');
            tag.className = 'keyword-tag';
            
            // Weight scaling (weight is 0 to 10)
            const fontSize = 11 + (item.weight * 0.8);
            tag.style.fontSize = `${fontSize}px`;
            
            tag.textContent = item.word;
            tag.onclick = () => selectKeyword(item.word, tag);
            
            container.appendChild(tag);
        });
    });
}

function selectKeyword(word, tagElement) {
    document.querySelectorAll('#keywords-cloud .keyword-tag').forEach(t => t.classList.remove('active'));
    if (tagElement) {
        tagElement.classList.add('active');
    }
    
    const matchesContainer = document.getElementById('keyword-matches');
    const pagesList = document.getElementById('keyword-pages-list');
    const titleSpan = document.getElementById('keyword-matches-title');
    
    titleSpan.textContent = `Pages with "${word}"`;
    pagesList.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); grid-column: 1/-1; padding: 10px;">Searching...</div>';
    matchesContainer.classList.remove('hidden');
    
    pywebview.api.search_word_pages(appState.readerFilepath, word).then(pages => {
        pagesList.innerHTML = '';
        
        if (!pages || pages.length === 0) {
            pagesList.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); grid-column: 1/-1; padding: 10px;">No occurrences found</div>';
            return;
        }
        
        pages.forEach(pNum => {
            const btn = document.createElement('button');
            btn.className = 'keyword-page-btn';
            btn.textContent = `p. ${pNum}`;
            btn.onclick = () => {
                appState.readerPage = pNum - 1;
                refreshReaderPage();
            };
            pagesList.appendChild(btn);
        });
    });
}

function clearKeywordSearch() {
    document.querySelectorAll('#keywords-cloud .keyword-tag').forEach(t => t.classList.remove('active'));
    const matchesContainer = document.getElementById('keyword-matches');
    if (matchesContainer) matchesContainer.classList.add('hidden');
}

/* ZEN AUDIO EXPERIENCES SETUP */

let zenAudioState = {
    isPlaying: false,
    volume: 0.5,
    fadeInterval: null
};

function toggleZenAudio() {
    const audio = document.getElementById('zen-audio-element');
    const playBtn = document.querySelector('.zen-play-btn .play-icon');
    const pauseBtn = document.querySelector('.zen-play-btn .pause-icon');
    if (!audio) return;
    
    if (audio.paused) {
        if (!audio.src) {
            const select = document.getElementById('zen-sound-select');
            audio.src = select.value;
        }
        audio.volume = 0; // fade in from silent
        audio.play().then(() => {
            zenAudioState.isPlaying = true;
            if (playBtn) playBtn.classList.add('hidden');
            if (pauseBtn) pauseBtn.classList.remove('hidden');
            fadeAudio(audio, zenAudioState.volume, 1000); // fade to preset volume over 1s
        }).catch(err => {
            showToast('Unable to play ambient sound: Network error', true);
        });
    } else {
        fadeAudio(audio, 0, 800, () => {
            audio.pause();
            zenAudioState.isPlaying = false;
            if (playBtn) playBtn.classList.remove('hidden');
            if (pauseBtn) pauseBtn.classList.add('hidden');
        });
    }
}

function changeZenSound(url) {
    const audio = document.getElementById('zen-audio-element');
    if (!audio) return;
    
    const wasPlaying = !audio.paused;
    if (zenAudioState.fadeInterval) {
        clearInterval(zenAudioState.fadeInterval);
        zenAudioState.fadeInterval = null;
    }
    
    audio.src = url;
    if (wasPlaying) {
        audio.volume = zenAudioState.volume;
        audio.play().catch(() => {});
    }
}

function changeZenVolume(volume) {
    zenAudioState.volume = parseFloat(volume);
    const audio = document.getElementById('zen-audio-element');
    if (audio && !audio.paused && !zenAudioState.fadeInterval) {
        audio.volume = zenAudioState.volume;
    }
}

function fadeAudio(audio, targetVolume, duration, callback) {
    if (zenAudioState.fadeInterval) {
        clearInterval(zenAudioState.fadeInterval);
    }
    
    const steps = 20;
    const intervalTime = duration / steps;
    const initialVolume = audio.volume;
    const volumeDelta = (targetVolume - initialVolume) / steps;
    let step = 0;
    
    zenAudioState.fadeInterval = setInterval(() => {
        audio.volume = Math.max(0, Math.min(1, initialVolume + volumeDelta * step));
        step++;
        
        if (step > steps) {
            clearInterval(zenAudioState.fadeInterval);
            zenAudioState.fadeInterval = null;
            audio.volume = targetVolume;
            if (callback) callback();
        }
    }, intervalTime);
}
