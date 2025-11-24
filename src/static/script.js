const API_BASE = "";
let currentTab = 'movies';
var art = null; // ArtPlayer instance
var currentTmdbId = null;
var currentSeason = 1;
var currentEpisode = 1;
var currentType = 'movie';
// Track whether we're showing search results
let isSearchActive = false;

// --- INIT ---
function init() { loadContent(currentTab); }

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentTab = this.dataset.tab;
            // leaving search clears back to normal content
            isSearchActive = false;
            document.getElementById('search-input').value = '';
            toggleSearchClear(false);
            loadContent(currentTab);
        });
    });
    
    // Search Listener
    document.getElementById('search-input').addEventListener('keypress', function (e) {
        if (e.key === 'Enter') runSearch();
    });

    // Optional: live show clear button visibility on input
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            toggleSearchClear(!!searchInput.value.trim());
        });
    }

    // Search clear (×) button
    const searchClearBtn = document.getElementById('search-clear');
    if (searchClearBtn) {
        searchClearBtn.addEventListener('click', () => {
            const input = document.getElementById('search-input');
            if (input) input.value = '';
            isSearchActive = false;
            toggleSearchClear(false);
            // restore normal rows
            loadContent(currentTab);
        });
    }
    
    loadContent(currentTab);
});

// Toggle visibility of the clear button
function toggleSearchClear(show) {
    const btn = document.getElementById('search-clear');
    if (!btn) return;
    btn.style.display = show ? 'flex' : 'none';
}

async function runSearch() {
    const query = document.getElementById('search-input').value;
    if (!query) return;
    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:4vh 0; text-align:center">Hunting...</div>';
    try {
        const res = await fetch(`/search?query=${encodeURIComponent(query)}`);
        const items = await res.json();
        container.innerHTML = '';
        isSearchActive = true;
        toggleSearchClear(true);

        if (items.length === 0) {
            container.innerHTML = '<div style="padding:4vh 0; text-align:center">No signals found.</div>';
            return;
        }
        // Single row of results
        createRow(`Results for "${query}"`, items);
    } catch (err) {
        container.innerHTML = `<div style="padding:4vh 0;color:#f55">Error: ${err}</div>`;
    }
}

async function loadContent(type) {
    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:4vh 0; text-align:center;">Loading catalog...</div>';
    try {
        const res = await fetch(`/${type}?limit=60`);
        const items = await res.json();
        container.innerHTML = '';

        // Only one row per tab, top 10 items
        const topItems = items.slice(0, 10);
        const rowTitle = type === 'movies' ? 'Top Movies' : 'Top Shows';
        createRow(rowTitle, topItems);
    } catch (err) {
        container.innerHTML = `<div style="padding:4vh 0;color:#f55">Error: ${err}</div>`;
    }
}

function createRow(title, items) {
    const container = document.getElementById('content-area');
    const section = document.createElement('section');
    section.className = 'row-wrapper';
    section.innerHTML = `<div class="row-title">${title}</div>`;
    const scroller = document.createElement('div');
    scroller.className = 'row-scroller';

    items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'card';
        card.onclick = () => openModal(item);
        const imgSrc = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/300x450';
        card.innerHTML = `<img src="${imgSrc}" class="poster" loading="lazy">`;
        scroller.appendChild(card);
    });

    const prevBtn = document.createElement('button');
    prevBtn.className = 'row-arrow prev';
    prevBtn.innerHTML = '&#8249;';
    prevBtn.onclick = () => scroller.scrollBy({ left: -0.8 * scroller.clientWidth, behavior: 'smooth' });
    const nextBtn = document.createElement('button');
    nextBtn.className = 'row-arrow next';
    nextBtn.innerHTML = '&#8250;';
    nextBtn.onclick = () => scroller.scrollBy({ left: 0.8 * scroller.clientWidth, behavior: 'smooth' });

    section.appendChild(prevBtn);
    section.appendChild(nextBtn);
    section.appendChild(scroller);
    container.appendChild(section);
}

// --- MODAL ---
function openModal(item) {
    const modal = document.getElementById('modal');
    const modalContent = document.getElementById('modal-content-wrapper');
    
    modalContent.style.display = 'grid'; 
    document.getElementById('player-wrapper').classList.add('hidden');

    document.getElementById('m-title').textContent = item.title;
    document.getElementById('m-desc').textContent = item.overview || 'No description available.';
    document.getElementById('m-poster').src = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/360x540';
    
    let score = '';
    if (typeof item.popularity_score === 'number') {
        let val = item.popularity_score > 1 ? item.popularity_score : item.popularity_score * 100;
        score = `${Math.round(val)}% Match`;
    }
    document.getElementById('m-score').textContent = score;
    document.getElementById('m-year').textContent = (item.release_date || '').split('-')[0];

    // SAVE STATE
    currentTmdbId = item.tmdb_id;
    currentType = currentTab === 'shows' ? 'tv' : 'movie';
    currentSeason = 1;
    currentEpisode = 1;

    const playBtn = document.querySelector('#play-btn');
    playBtn.onclick = () => playVideo(currentType, currentTmdbId);

    const epSection = document.getElementById('m-episodes');
    if (currentTab === 'shows') {
        epSection.classList.remove('hidden');
        loadSeasons(item.id);
    } else {
        epSection.classList.add('hidden');
    }
    modal.classList.add('active');
}

function closeModal() {
    document.getElementById('modal').classList.remove('active');
    closePlayer();
}

function backdropClose(e) {
    if (e.target.id === 'modal') closeModal();
}

async function loadSeasons(showId) {
    const list = document.getElementById('ep-list');
    list.innerHTML = 'Loading...';
    try {
        const res = await fetch(`/shows/${showId}/seasons`);
        const data = await res.json();
        list.innerHTML = '';
        const seasons = data.seasons || [];
        
        seasons.forEach(season => {
            const div = document.createElement('div');
            div.innerHTML = `<div style="font-weight:bold; margin:15px 0 5px; color:#fff">Season ${season.season_number}</div>`;
            (season.episodes || []).forEach(ep => {
                const row = document.createElement('div');
                row.className = 'ep-item';
                row.innerHTML = `<span>${ep.episode_number}. ${ep.title}</span> <span>▶</span>`;
                row.onclick = () => playVideo('tv', currentTmdbId, season.season_number, ep.episode_number);
                div.appendChild(row);
            });
            list.appendChild(div);
        });
    } catch (err) {
        list.innerHTML = 'Error loading episodes';
    }
}

// --- PLAYER LOGIC ---
// --- PLAYER LOGIC ---
async function playVideo(type, tmdbId, season=1, episode=1) {
    currentTmdbId = tmdbId;
    currentType = type;
    currentSeason = season;
    currentEpisode = episode;

    const btn = document.querySelector('#play-btn');
    const originalText = btn.innerText;
    btn.innerText = "HUNTING...";
    
    // Switch UI to Player Mode
    document.getElementById('modal-content-wrapper').style.display = 'none';
    document.getElementById('player-wrapper').classList.remove('hidden');

    // Default to Auto-Hunt
    await loadSource('auto');
    
    btn.innerText = originalText;
}

function changeSource(provider) {
    loadSource(provider);
}

async function loadSource(provider) {
    const artContainer = document.getElementById('artplayer-app');
    const iframe = document.getElementById('embed-frame');
    const select = document.getElementById('source-select');
    
    // 1. HARD RESET
    artContainer.style.display = 'none';
    iframe.classList.add('hidden');
    iframe.src = "about:blank"; // Clear previous video audio/state
    if(art) art.pause();

    // Show loading state in selector
    const prevLabel = select.options[select.selectedIndex].text;
    select.options[select.selectedIndex].text = "Hunting...";

    try {
        // Pass 'auto' or specific provider name
        const apiUrl = `/play/${currentType}/${currentTmdbId}?season=${currentSeason}&episode=${currentEpisode}&provider=${provider}`;
        const res = await fetch(apiUrl);
        const data = await res.json();

        // Restore label
        select.options[select.selectedIndex].text = prevLabel;

        if (data.type === 'embed') {
            // --- EMBED MODE ---
            console.log("Playing Embed:", data.source);
            iframe.classList.remove('hidden');
            iframe.src = data.url;
            
            // Alert user what source won
            if(provider === 'auto') {
               // Update dropdown to show what we found? Optional.
               console.log(`Auto-Hunt found: ${data.source}`);
            }
        } else {
            // --- DIRECT MODE ---
            artContainer.style.display = 'block';
            if (!art) initArtPlayer();
            
            const proxyUrl = `/proxy_stream?url=${encodeURIComponent(data.url)}`;
            art.switchUrl(proxyUrl);
        }
    } catch (e) {
        console.error(e);
        select.options[select.selectedIndex].text = "Failed";
        setTimeout(() => select.options[select.selectedIndex].text = prevLabel, 2000);
    }
}

function initArtPlayer() {
    art = new Artplayer({
        container: '#artplayer-app',
        url: '',
        theme: '#0CAADC',
        volume: 1.0,
        isLive: false,
        muted: false,
        autoplay: true,
        pip: true,
        autoSize: true,
        autoMini: true,
        screenshot: true,
        setting: true,
        loop: false,
        flip: true,
        playbackRate: true,
        aspectRatio: true,
        
        // FULLSCREEN FIX: Target the wrapper, not the window
        fullscreen: true,
        fullscreenWeb: true,
        
        miniProgressBar: true,
        mutex: true,
        backdrop: true,
        playsInline: true,
        autoPlayback: true,
        airplay: true,
        theme: '#23ade5',
    });
}

function closePlayer() {
    if (art) art.pause();
    document.getElementById('embed-frame').src = "about:blank"; // Stop audio
    document.getElementById('player-wrapper').classList.add('hidden');
    document.getElementById('modal-content-wrapper').style.display = 'grid';
}

// ... (Keep your existing init and loadContent logic) ...

let searchTimeout;

document.addEventListener('DOMContentLoaded', () => {
    init(); // Load initial browse content hidden in background
    
    // Live Search Listener
    const input = document.getElementById('search-input');
    input.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        if(e.target.value.length > 2) {
            searchTimeout = setTimeout(() => liveSearch(e.target.value), 300);
        } else {
            document.getElementById('live-results').classList.add('hidden');
        }
    });
    
    // Enter key triggers full browse mode with search
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            enterBrowseMode(e.target.value);
            document.getElementById('live-results').classList.add('hidden');
        }
    });
});

async function liveSearch(query) {
    const dropdown = document.getElementById('live-results');
    try {
        const res = await fetch(`/search?query=${encodeURIComponent(query)}`);
        const items = await res.json();
        
        dropdown.innerHTML = '';
        if(items.length > 0) {
            items.slice(0, 5).forEach(item => {
                const div = document.createElement('div');
                div.className = 'live-item';
                const img = item.poster_path ? `https://image.tmdb.org/t/p/w92${item.poster_path}` : '';
                const year = (item.release_date || '').split('-')[0];
                
                div.innerHTML = `
                    <img src="${img}" class="live-poster">
                    <div class="live-info">
                        <div class="live-title">${item.title || item.name}</div>
                        <div class="live-year">${year}</div>
                    </div>
                `;
                div.onclick = () => {
                    openModal(item); // Open details directly
                    // Optionally switch to browse mode too
                    // enterBrowseMode(); 
                };
                dropdown.appendChild(div);
            });
            dropdown.classList.remove('hidden');
        } else {
            dropdown.classList.add('hidden');
        }
    } catch (e) {
        console.error(e);
    }
}

function enterBrowseMode(searchQuery = null) {
    document.getElementById('hero-section').style.opacity = '0';
    setTimeout(() => {
        document.getElementById('hero-section').style.display = 'none';
        document.getElementById('browse-section').classList.remove('hidden');
        
        if(searchQuery) {
            // If entered with a search term, clear existing rows and show results
            const container = document.getElementById('content-area');
            container.innerHTML = '';
            // Re-run search in browse context
            fetch(`/search?query=${encodeURIComponent(searchQuery)}`)
                .then(r => r.json())
                .then(items => createRow(`Results for "${searchQuery}"`, items));
        }
    }, 500);
}

function goHome() {
    document.getElementById('browse-section').classList.add('hidden');
    document.getElementById('hero-section').style.display = 'flex';
    setTimeout(() => document.getElementById('hero-section').style.opacity = '1', 50);
    document.getElementById('search-input').value = '';
    document.getElementById('live-results').classList.add('hidden');
}

// ... (Keep your createRow, openModal, playVideo, loadSource functions) ...