const API_BASE = "";
var art = null;
var currentTmdbId = null, currentSeason = 1, currentEpisode = 1, currentType = 'movie';
let searchTimeout;

// --- INIT ---
document.addEventListener('DOMContentLoaded', () => {
    // Load initial content into the browse section
    loadHome();
    
    // Search Input Logic
    const input = document.getElementById('search-input');
    const dropdown = document.getElementById('live-results');

    // 1. Live Search Listener
    input.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();
        
        // Show/Hide "X" button if you implemented it, otherwise skip
        const clearBtn = document.getElementById('search-clear');
        if(clearBtn) clearBtn.style.display = query.length > 0 ? 'block' : 'none';

        if(query.length > 2) {
            dropdown.classList.remove('hidden');
            dropdown.innerHTML = '<div style="padding:15px;color:#888;text-align:center">Hunting...</div>';
            searchTimeout = setTimeout(() => liveSearch(query), 300);
        } else {
            dropdown.classList.add('hidden');
        }
    });
    
    // 2. Enter Key -> Browse Mode
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            dropdown.classList.add('hidden');
            // If we are in Hero Mode, switch to Browse Mode
            // If we are already in Browse Mode, just reload content
            // For now, assuming we want to just run search:
            runSearch();
        }
    });
    
    // 3. Close Dropdown on Click Outside
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.add('hidden');
        }
    });
});

function clearSearch() {
    const input = document.getElementById('search-input');
    input.value = '';
    document.getElementById('live-results').classList.add('hidden');
    if(document.getElementById('search-clear')) document.getElementById('search-clear').style.display = 'none';
}

// --- SEARCH FUNCTIONS ---
async function liveSearch(query) {
    const dropdown = document.getElementById('live-results');
    try {
        const res = await fetch(`/search?query=${encodeURIComponent(query)}`);
        const items = await res.json();
        
        dropdown.innerHTML = '';
        
        // Filter out bad data
        const validItems = items.filter(i => (i.title || i.name) && i.poster_path);

        if(validItems.length > 0) {
            validItems.slice(0, 6).forEach(item => {
                const div = document.createElement('div');
                div.className = 'live-item';
                const title = item.title || item.name;
                const year = (item.release_date || '').split('-')[0] || 'N/A';
                const img = `https://image.tmdb.org/t/p/w92${item.poster_path}`;
                
                div.innerHTML = `
                    <img src="${img}" class="live-poster">
                    <div class="live-info">
                        <span class="live-title">${title}</span>
                        <span class="live-year">${year}</span>
                    </div>
                `;
                div.onclick = () => {
                    dropdown.classList.add('hidden');
                    openModal(item);
                };
                dropdown.appendChild(div);
            });
        } else {
            dropdown.innerHTML = '<div style="padding:15px;color:#888;text-align:center">No signals found.</div>';
        }
    } catch (e) {
        console.error(e);
    }
}

async function runSearch() {
    const query = document.getElementById('search-input').value;
    if (!query) return;

    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:40px; text-align:center">Hunting...</div>';

    try {
        const res = await fetch(`/search?query=${encodeURIComponent(query)}`);
        const items = await res.json();
        
        container.innerHTML = '';
        
        if (items.length === 0) {
            container.innerHTML = '<div style="padding:40px; text-align:center">No signals found.</div>';
            return;
        }

        createRow(`Results for "${query}"`, items);
        
    } catch (err) {
        container.innerHTML = `<div style="padding:40px;color:#f55">Search failed: ${err}</div>`;
    }
}

// --- CONTENT LOADING ---
async function loadHome() {
    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:40px; text-align:center;">Initializing...</div>';
    
    try {
        // Fetch Top Movies & Shows
        const [resMovies, resShows] = await Promise.all([
            fetch(`/movies?limit=15`),
            fetch(`/shows?limit=15`)
        ]);
        
        const movies = await resMovies.json();
        const shows = await resShows.json();
        
        container.innerHTML = '';
        
        createRow('Popular Movies', movies);
        createRow('Popular Series', shows);
        
    } catch (err) {
        container.innerHTML = `<div style="padding:40px;color:#f55">Error: ${err}</div>`;
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
        
        const name = item.title || item.name;
        const imgSrc = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/300x450';
        
        card.innerHTML = `<img src="${imgSrc}" class="poster" loading="lazy" alt="${name}">`;
        scroller.appendChild(card);
    });

    // Arrows
    const prevBtn = document.createElement('button');
    prevBtn.className = 'row-arrow prev';
    prevBtn.innerHTML = '&#8249;';
    prevBtn.onclick = () => scroller.scrollBy({ left: -1000, behavior: 'smooth' });
    
    const nextBtn = document.createElement('button');
    nextBtn.className = 'row-arrow next';
    nextBtn.innerHTML = '&#8250;';
    nextBtn.onclick = () => scroller.scrollBy({ left: 1000, behavior: 'smooth' });

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

    // ROBUST TYPE DETECTION
    // TV Shows usually have 'name', Movies have 'title'.
    // Fallback: Check 'first_air_date' (TV) vs 'release_date' (Movie)
    let isMovie = true;
    if (item.name || item.first_air_date || (item.media_type === 'tv')) {
        isMovie = false;
    }

    const title = item.title || item.name;
    const date = item.release_date || item.first_air_date || '';
    const year = date.split('-')[0];

    document.getElementById('m-title').textContent = title;
    document.getElementById('m-desc').textContent = item.overview || 'No description available.';
    document.getElementById('m-poster').src = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/360x540';
    
    // Score Fix (Cap at 100%)
    let score = '';
    if (typeof item.popularity_score === 'number') {
        let val = item.popularity_score;
        // Normalize: If > 10, assume it's raw popularity, clip to 98-99% for "Hit" look
        if (val > 100) val = 98; 
        score = `${Math.round(val)}% Match`;
    }
    document.getElementById('m-score').textContent = score;
    document.getElementById('m-year').textContent = year;

    // Set State
    currentTmdbId = item.tmdb_id || item.id; // Fallback to ID if tmdb_id missing
    currentType = isMovie ? 'movie' : 'tv';
    
    // UI Logic: Movie vs Show
    const playBtn = document.querySelector('#play-btn');
    const epSection = document.getElementById('m-episodes');

    if (isMovie) {
        // MOVIE: Show Play Button, Hide Episodes
        playBtn.style.display = 'block';
        playBtn.onclick = () => playVideo('movie', currentTmdbId);
        epSection.classList.add('hidden');
    } else {
        // TV SHOW: Hide Main Play Button (Force Episode Select), Show Episodes
        playBtn.style.display = 'none'; 
        epSection.classList.remove('hidden');
        loadSeasons(currentTmdbId);
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
    list.innerHTML = '<div style="padding:20px;text-align:center">Accessing Archives...</div>';
    
    try {
        // We need to fetch details because the search result might not have seasons attached
        // We can hit your backend endpoint which fetches fresh details
        // Assuming you have a route /shows/{id}/seasons
        // OR we can hack it: If we don't have seasons in DB, we might need to trigger a fetch.
        
        // Better: Use the backend endpoint we made
        const res = await fetch(`/shows/${showId}/seasons`);
        if(!res.ok) throw new Error("No data");
        
        const seasons = await res.json();
        list.innerHTML = '';
        
        if (seasons.length === 0) {
             list.innerHTML = '<div style="padding:20px;text-align:center">No episodes indexed. Try re-ingesting.</div>';
             return;
        }
        
        seasons.forEach(season => {
            const div = document.createElement('div');
            div.innerHTML = `<div style="font-weight:bold; margin:20px 0 10px; color:#fff; border-bottom:1px solid #333; padding-bottom:5px;">Season ${season.season_number}</div>`;
            
            (season.episodes || []).forEach(ep => {
                const row = document.createElement('div');
                row.className = 'ep-item';
                // Add click handler for specific episode
                row.onclick = () => playVideo('tv', currentTmdbId, season.season_number, ep.episode_number);
                
                row.innerHTML = `
                    <div style="display:flex; gap:15px; align-items:center; width:100%">
                        <span style="color:var(--accent); font-weight:bold; width:30px">${ep.episode_number}</span>
                        <span style="flex:1">${ep.title || 'Episode ' + ep.episode_number}</span>
                        <span style="font-size:1.2rem">▶</span>
                    </div>
                `;
                div.appendChild(row);
            });
            list.appendChild(div);
        });
    } catch (err) {
        console.error(err);
        list.innerHTML = '<div style="padding:20px; color:#f55">Signal scrambled (No Seasons Found).</div>';
    }
}

// --- PLAYER LOGIC ---
async function playVideo(type, tmdbId, season=1, episode=1) {
    currentTmdbId = tmdbId;
    currentType = type;
    currentSeason = season;
    currentEpisode = episode;

    const btn = document.querySelector('#play-btn');
    const originalText = btn.innerText;
    btn.innerText = "HUNTING...";
    
    document.getElementById('modal-content-wrapper').style.display = 'none';
    document.getElementById('player-wrapper').classList.remove('hidden');

    // Default to Auto-Hunt
    loadSource('auto');
    btn.innerText = originalText;
}

function changeSource(provider) { loadSource(provider); }

async function loadSource(provider) {
    const artContainer = document.getElementById('artplayer-app');
    const iframe = document.getElementById('embed-frame');
    const select = document.getElementById('source-select');
    
    // RESET
    artContainer.style.display = 'none';
    iframe.classList.add('hidden');
    iframe.src = "about:blank";
    if(art) art.pause();

    // Loading state in dropdown
    const prevLabel = select.options[select.selectedIndex].text;
    select.options[select.selectedIndex].text = "Loading...";

    try {
        const apiUrl = `/play/${currentType}/${currentTmdbId}?season=${currentSeason}&episode=${currentEpisode}&provider=${provider}`;
        const res = await fetch(apiUrl);
        const data = await res.json();

        // Restore label
        select.options[select.selectedIndex].text = prevLabel;

        if (data.type === 'embed') {
            // EMBED MODE
            iframe.classList.remove('hidden');
            iframe.src = data.url;
        } else {
            // DIRECT MODE
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
        fullscreen: true,
        fullscreenWeb: true,
        miniProgressBar: true,
        mutex: true,
        backdrop: true,
        playsInline: true,
        autoPlayback: true,
        airplay: true,
        theme: '#23ade5',
        customType: {
            m3u8: function (video, url) {
                if (Hls.isSupported()) {
                    const hls = new Hls();
                    hls.loadSource(url);
                    hls.attachMedia(video);
                } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                    video.src = url;
                }
            }
        }
    });
}

function closePlayer() {
    if (art) art.pause();
    document.getElementById('embed-frame').src = "about:blank";
    document.getElementById('player-wrapper').classList.add('hidden');
    document.getElementById('modal-content-wrapper').style.display = 'grid';
}