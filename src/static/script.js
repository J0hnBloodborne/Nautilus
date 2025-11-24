const API_BASE = "";
var art = null;
var currentTmdbId = null, currentSeason = 1, currentEpisode = 1, currentType = 'movie';
let searchTimeout;

// --- INIT ---
document.addEventListener('DOMContentLoaded', () => {
    loadHome();
    
    const input = document.getElementById('search-input');
    const dropdown = document.getElementById('live-results');

    input.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();
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
    
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            dropdown.classList.add('hidden');
            runSearch();
        }
    });
    
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

// --- SEARCH ---
async function liveSearch(query) {
    const dropdown = document.getElementById('live-results');
    try {
        const res = await fetch(`/search?query=${encodeURIComponent(query)}`);
        const items = await res.json();
        dropdown.innerHTML = '';
        
        const validItems = items.filter(i => (i.title || i.name) && i.poster_path);

        if(validItems.length > 0) {
            validItems.slice(0, 6).forEach(item => {
                const div = document.createElement('div');
                div.className = 'live-item';
                const title = item.title || item.name;
                // Fallback for year
                const date = item.release_date || item.first_air_date || ''; 
                const year = date.split('-')[0] || 'N/A';
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
                    // When coming from search, item usually has 'media_type' or specific keys
                    // If not, we guess based on keys
                    const type = item.first_air_date || item.name ? 'tv' : 'movie';
                    openModal(item, type);
                };
                dropdown.appendChild(div);
            });
        } else {
            dropdown.innerHTML = '<div style="padding:15px;color:#888;text-align:center">No signals found.</div>';
        }
    } catch (e) { console.error(e); }
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
        createRow(`Results for "${query}"`, items, 'mixed');
    } catch (err) {
        container.innerHTML = `<div style="padding:40px;color:#f55">Error: ${err}</div>`;
    }
}

// --- LOAD HOME ---
async function loadHome() {
    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:40px; text-align:center;">Initializing...</div>';
    try {
        const [resMovies, resShows] = await Promise.all([
            fetch(`/movies?limit=15`),
            fetch(`/shows?limit=15`)
        ]);
        const movies = await resMovies.json();
        const shows = await resShows.json();
        container.innerHTML = '';
        
        // Explicitly pass type to createRow
        createRow('Popular Movies', movies, 'movie');
        createRow('Popular Series', shows, 'tv');
    } catch (err) {
        container.innerHTML = `<div style="padding:40px;color:#f55">Error: ${err}</div>`;
    }
}

function createRow(title, items, fixedType=null) {
    const container = document.getElementById('content-area');
    const section = document.createElement('section');
    section.className = 'row-wrapper';
    section.innerHTML = `<div class="row-title">${title}</div>`;
    const scroller = document.createElement('div');
    scroller.className = 'row-scroller';

    items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'card';
        
        // Determine type: 
        // 1. Use fixedType if provided (e.g. from loadHome)
        // 2. Else check for show-specific keys (first_air_date, name)
        let type = fixedType;
        if (!type) {
             type = (item.first_air_date || item.name) ? 'tv' : 'movie';
        }

        card.onclick = () => openModal(item, type);
        
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
function openModal(item, typeOverride=null) {
    const modal = document.getElementById('modal');
    const modalContent = document.getElementById('modal-content-wrapper');
    
    // Reset UI
    modalContent.style.display = 'grid'; 
    document.getElementById('player-wrapper').classList.add('hidden');

    // 1. Determine Type Robustly
    // Priority: Override -> media_type property -> Check keys
    let type = typeOverride;
    if (!type) {
        if (item.media_type) type = item.media_type;
        else if (item.first_air_date || item.name) type = 'tv';
        else type = 'movie';
    }
    
    const isMovie = (type === 'movie');
    
    // 2. Populate Data
    document.getElementById('m-title').textContent = item.title || item.name;
    document.getElementById('m-desc').textContent = item.overview || 'No description available.';
    document.getElementById('m-poster').src = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/360x540';
    
    let score = '';
    if (typeof item.popularity_score === 'number') {
        let val = item.popularity_score > 1 ? item.popularity_score : item.popularity_score * 100;
        score = `${Math.round(val)}% Match`;
    }
    document.getElementById('m-score').textContent = score;
    
    const date = item.release_date || item.first_air_date || '';
    document.getElementById('m-year').textContent = date.split('-')[0];

    // 3. Set State
    currentTmdbId = item.tmdb_id || item.id;
    currentType = type;
    currentSeason = 1;
    currentEpisode = 1;
    
    // 4. UI Logic
    const playBtn = document.querySelector('#play-btn');
    const epSection = document.getElementById('m-episodes');

    if (isMovie) {
        playBtn.style.display = 'block';
        playBtn.onclick = () => playVideo('movie', currentTmdbId);
        epSection.classList.add('hidden');
    } else {
        // Hide main play button for shows (force episode selection)
        playBtn.style.display = 'none';
        epSection.classList.remove('hidden');
        loadSeasons(item.id); // Use DB ID for lookup
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
    list.innerHTML = '<div style="padding:20px; text-align:center; color:#888">Accessing Archives...</div>';
    
    try {
        const res = await fetch(`/shows/${showId}/seasons`);
        const seasons = await res.json(); // Note: backend returns [] if fail, not error
        
        list.innerHTML = '';
        
        if (!seasons || seasons.length === 0) {
             list.innerHTML = '<div style="padding:20px; text-align:center; color:#f55">No episodes indexed. Run ingest.py again?</div>';
             return;
        }
        
        seasons.forEach(season => {
            const label = season.season_number === 0 ? "Specials" : `Season ${season.season_number}`;
            const div = document.createElement('div');
            div.innerHTML = `<div style="font-weight:bold; margin:20px 0 10px; color:#fff; border-bottom:1px solid #333; padding-bottom:5px;">${label}</div>`;
            
            if (season.episodes && season.episodes.length > 0) {
                season.episodes.forEach(ep => {
                    const row = document.createElement('div');
                    row.className = 'ep-item';
                    row.innerHTML = `
                        <div style="display:flex; gap:15px; align-items:center; width:100%">
                            <span style="color:var(--accent); font-weight:bold; width:30px">${ep.episode_number}</span>
                            <span style="flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${ep.title || 'Episode ' + ep.episode_number}</span>
                            <span style="font-size:1.2rem; opacity:0.7">▶</span>
                        </div>
                    `;
                    row.onclick = () => playVideo('tv', currentTmdbId, season.season_number, ep.episode_number);
                    div.appendChild(row);
                });
            } else {
                div.innerHTML += '<div style="padding:10px; color:#666; font-style:italic">Episodes missing.</div>';
            }
            list.appendChild(div);
        });
    } catch (err) {
        console.error(err);
        list.innerHTML = '<div style="padding:20px; color:#f55">Signal scrambled.</div>';
    }
}

// --- PLAYER LOGIC ---
async function playVideo(type, tmdbId, season=1, episode=1) {
    currentTmdbId = tmdbId;
    currentType = type;
    currentSeason = season;
    currentEpisode = episode;

    const btn = document.querySelector('#play-btn');
    if(btn) btn.innerText = "HUNTING..."; // Might be hidden for TV
    
    document.getElementById('modal-content-wrapper').style.display = 'none';
    document.getElementById('player-wrapper').classList.remove('hidden');

    loadSource('auto');
    if(btn) btn.innerText = "▶ PLAY";
}

function changeSource(provider) { loadSource(provider); }

async function loadSource(provider) {
    const artContainer = document.getElementById('artplayer-app');
    const iframe = document.getElementById('embed-frame');
    const select = document.getElementById('source-select');
    
    artContainer.style.display = 'none';
    iframe.classList.add('hidden');
    iframe.src = "about:blank";
    if(art) art.pause();

    // Reset dropdown text if needed
    const prevLabel = select.options[select.selectedIndex].text;
    select.options[select.selectedIndex].text = "Hunting...";

    try {
        const apiUrl = `/play/${currentType}/${currentTmdbId}?season=${currentSeason}&episode=${currentEpisode}&provider=${provider}`;
        const res = await fetch(apiUrl);
        const data = await res.json();

        select.options[select.selectedIndex].text = prevLabel;

        if (data.type === 'embed') {
            iframe.classList.remove('hidden');
            iframe.src = data.url;
        } else {
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