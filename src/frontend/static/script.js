const API_BASE = "";
var art = null;
var currentTmdbId = null, currentSeason = 1, currentEpisode = 1, currentType = 'movie';
let searchTimeout;

// --- SOUND MANAGER ---
const SoundManager = {
    sounds: {},
    init() {
        // Preload sounds to reduce latency
        ['paper', 'coin', 'wood', 'click'].forEach(name => {
            const audio = new Audio(`/static/sounds/${name}.mp3`);
            audio.volume = 0.6;
            audio['coin'].volume = 1.0;
            this.sounds[name] = audio;
        });
    },
    play(name) {
        try {
            const audio = this.sounds[name];
            if (audio) {
                audio.currentTime = 0.05; // Skip first 50ms to reduce silence delay
                audio.play().catch(() => {}); // Ignore autoplay errors
            } else {
                // Fallback if not preloaded
                new Audio(`/static/sounds/${name}.mp3`).play().catch(() => {});
            }
        } catch (e) {
            // Ignore audio system errors
        }
    }
};

// Initialize sounds on load
document.addEventListener('DOMContentLoaded', () => SoundManager.init());

// --- GUEST ID LOGIC ---
function getGuestId() {
    let gid = localStorage.getItem('nautilus_guest_id');
    if (!gid) {
        gid = crypto.randomUUID();
        localStorage.setItem('nautilus_guest_id', gid);
    }
    return gid;
}

// --- INIT ---
document.addEventListener('DOMContentLoaded', () => {
    loadHome();
    
    const input = document.getElementById('search-input');
    const dropdown = document.getElementById('live-results');

    // Search Input Logic
    input.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();
        
        // Toggle Clear Button
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
    
    // Close dropdown on click outside
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
    // Do NOT reload home, just clear results
    // loadHome(); 
}

// --- THEME TOGGLE ---
function toggleTheme() {
    const body = document.body;
    const current = body.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    body.setAttribute('data-theme', next);
    localStorage.setItem('nautilus_theme', next);
    
    // Update Icon Text
    const btn = document.querySelector('.theme-toggle');
    if(next === 'dark') {
        btn.innerHTML = '<i class="fa-solid fa-sun"></i> Light Mode';
    } else {
        btn.innerHTML = '<i class="fa-solid fa-moon"></i> Dark Mode';
    }
}

// Init Theme
const savedTheme = localStorage.getItem('nautilus_theme') || 'light';
document.body.setAttribute('data-theme', savedTheme);
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.querySelector('.theme-toggle');
    if(btn) {
        if(savedTheme === 'dark') {
            btn.innerHTML = '<i class="fa-solid fa-sun"></i> Light Mode';
        } else {
            btn.innerHTML = '<i class="fa-solid fa-moon"></i> Dark Mode';
        }
    }
    
    // Show disclaimer modal on first visit
    showDisclaimerIfFirstTime();
});

// --- DISCLAIMER POPUP (First Visit) ---
function showDisclaimerIfFirstTime() {
    const hasSeenDisclaimer = localStorage.getItem('nautilus_disclaimer_seen');
    if (hasSeenDisclaimer) return;
    
    const modal = document.getElementById('disclaimer-modal');
    const closeBtn = document.getElementById('disclaimer-close');
    const timerText = document.getElementById('timer-text');
    const closeText = document.getElementById('close-text');
    const timerCount = document.getElementById('timer-count');
    
    modal.classList.remove('hidden');
    
    let countdown = 15;
    const interval = setInterval(() => {
        countdown--;
        timerCount.textContent = countdown;
        
        if (countdown <= 0) {
            clearInterval(interval);
            closeBtn.disabled = false;
            closeBtn.style.opacity = '1';
            closeBtn.style.cursor = 'pointer';
            timerText.style.display = 'none';
            closeText.style.display = 'inline';
        }
    }, 1000);
    
    closeBtn.onclick = () => {
        localStorage.setItem('nautilus_disclaimer_seen', 'true');
        modal.classList.add('hidden');
        SoundManager.play('paper');
    };
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
                const date = item.release_date || item.first_air_date || '';
                const year = date.split('-')[0] || 'N/A';
                const img = `https://image.tmdb.org/t/p/w92${item.poster_path}`;
                
                div.innerHTML = `
                    <img src="${img}" class="live-poster" style="width:40px;height:60px;object-fit:cover;border:1px solid #2b1d16;">
                    <div class="live-info">
                        <span class="live-title">${title}</span>
                        <span class="live-year">${year}</span>
                    </div>
                `;
                div.onclick = () => {
                    dropdown.classList.add('hidden');
                    // Preserve media type so TV results open with episodes instead of PLAY
                    let type = item.media_type;
                    if (!type) {
                        type = (item.first_air_date || item.name) ? 'tv' : 'movie';
                    }
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
        // Use a temporary row-like rendering that preserves per-item media type
        const title = `Results for "${query}"`;
        const section = document.createElement('section');
        section.className = 'row-wrapper';
        section.innerHTML = `<div class="row-title">${title}</div>`;
        const scroller = document.createElement('div');
        scroller.className = 'row-scroller';

        items.forEach(item => {
            const card = document.createElement('div');
            card.className = 'card';

            let type = item.media_type;
            if (!type) {
                type = (item.first_air_date || item.name) ? 'tv' : 'movie';
            }

            card.onclick = () => openModal(item, type);

            const name = item.title || item.name;
            const imgSrc = item.poster_path
                ? `https://image.tmdb.org/t/p/w500${item.poster_path}`
                : 'https://via.placeholder.com/300x450';

            card.innerHTML = `<img src="${imgSrc}" class="poster" loading="lazy" alt="${name}">`;
            scroller.appendChild(card);
        });

        section.appendChild(scroller);
        container.appendChild(section);
    } catch (err) {
        container.innerHTML = `<div style="padding:40px;color:#f55">Error: ${err}</div>`;
    }
}

// --- HOME LOADING (With ML) ---
async function loadHome() {
    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:40px; text-align:center;">Initializing...</div>';
    
    try {
        // Parallel Fetch: New Releases & Top Rated (movies & shows), Recs, Clusters, Desi, Animated, Random
        const [resNewMovies, resTopMovies, resNewShows, resTopShows, resRecs, resClusters, resDesi, resAnimated, resRandom] = await Promise.all([
            fetch(`/movies/new_releases?days=60&limit=50`),
            fetch(`/movies/top_rated_alltime?limit=50`),
            fetch(`/shows/new_releases?days=60&limit=50`),
            fetch(`/shows/top_rated_alltime?limit=50`),
            fetch(`/recommend/guest/${getGuestId()}`),
            fetch(`/collections/ai`),
            fetch(`/movies/desi?limit=15`),
            fetch(`/movies/genre/16?limit=15`),
            fetch(`/movies/random?limit=15`)
        ]);

        const moviesNew = await resNewMovies.json();
        const moviesTop = await resTopMovies.json();
        const showsNew = await resNewShows.json();
        const showsTop = await resTopShows.json();
        const recs = await resRecs.json();
        const clusters = await resClusters.json();
        const desi = await resDesi.json();
        const animated = await resAnimated.json();
        const random = await resRandom.json();
        
        container.innerHTML = '';
        
        // 1. RecSys Row
        if(recs.length > 0) createRow('Picked for You (AI RecSys)', recs, 'movie');

        // 2. New Releases & Top Rated rows using server-provided data (full rows)
        if (moviesNew && moviesNew.length > 0) createRow('New Releases', moviesNew, 'movie');
        if (moviesTop && moviesTop.length > 0) createRow('Top Rated', moviesTop, 'movie');

        if (showsNew && showsNew.length > 0) createRow('New Releases (Series)', showsNew, 'tv');
        if (showsTop && showsTop.length > 0) createRow('Top Rated (Series)', showsTop, 'tv');
        
        // 3. New Genre Rows
        if(desi.length > 0) createRow('Desi Hits', desi, 'movie');
        if(animated.length > 0) createRow('Animated Worlds', animated, 'movie');
        
        // 4. Random Row with Regen
        if(random.length > 0) createRow('Random Picks', random, 'movie', true);

        // 5. Clustering Rows
        if(clusters.cluster_1 && clusters.cluster_1.items.length > 0) 
            createRow(clusters.cluster_1.name, clusters.cluster_1.items, 'movie');
        if(clusters.cluster_2 && clusters.cluster_2.items.length > 0) 
            createRow(clusters.cluster_2.name, clusters.cluster_2.items, 'movie');

    } catch (err) {
        console.error(err);
        container.innerHTML = `<div style="padding:40px;color:#f55">System Error. Check console.</div>`;
    }
}

function createRow(title, items, fixedType=null, hasRegen=false) {
    const container = document.getElementById('content-area');
    const section = document.createElement('section');
    section.className = 'row-wrapper';
    
    let titleHtml = `<div class="row-title">${title}`;
    if (hasRegen) {
        titleHtml += ` <button onclick="refreshRandom(this)" class="regen-btn">Regenerate</button>`;
    }
    titleHtml += `</div>`;
    
    section.innerHTML = titleHtml;
    const scroller = document.createElement('div');
    scroller.className = 'row-scroller';
    if (hasRegen) scroller.id = 'random-scroller';

    items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'card';
        
        // LOGIC FIX: If fixedType is passed (e.g. 'tv'), use it. 
        // Otherwise try to guess from item properties.
        let type = fixedType;
        if (!type) {
             type = (item.name || item.first_air_date) ? 'tv' : 'movie';
        }

        // Pass the determined type to openModal
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
    prevBtn.onclick = () => { SoundManager.play('wood'); scroller.scrollBy({ left: -1000, behavior: 'smooth' }); };
    
    const nextBtn = document.createElement('button');
    nextBtn.className = 'row-arrow next';
    nextBtn.innerHTML = '&#8250;';
    nextBtn.onclick = () => { SoundManager.play('wood'); scroller.scrollBy({ left: 1000, behavior: 'smooth' }); };

    section.appendChild(prevBtn);
    section.appendChild(nextBtn);
    section.appendChild(scroller);
    container.appendChild(section);
}

// --- MODAL ---
function openModal(item, typeOverride=null) {
    SoundManager.play('paper');
    const modal = document.getElementById('modal');
    const modalContent = document.getElementById('modal-content-wrapper');
    
    // Reset UI
    document.querySelector('.modal-header').classList.remove('hidden');
    document.getElementById('player-wrapper').classList.add('hidden');
    
    // Force show modal immediately
    modal.classList.remove('hidden');

    // Smart Type Detection
    let type = typeOverride;
    if (!type) {
        if (item.media_type) type = item.media_type;
        else if (item.first_air_date || item.name) type = 'tv';
        else type = 'movie';
    }
    const isMovie = (type === 'movie');

    // Populate Info
    document.getElementById('m-title').textContent = item.title || item.name;
    document.getElementById('m-desc').textContent = item.overview || 'No description available.';
    document.getElementById('m-poster').src = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/360x540';
    
    const date = item.release_date || item.first_air_date || '';
    document.getElementById('m-year').textContent = date.split('-')[0];


    // Score Normalization (UI Bug Fix)
    let score = '';
    if (typeof item.popularity_score === 'number') {
        let val = item.popularity_score;
        if (val > 100) val = 98; // Cap raw scores
        else if (val <= 1) val = val * 100;
        score = `${Math.round(val)}% Loot Value`; // Changed from "Match" to "Loot Value"
    }
    document.getElementById('m-score').textContent = score;

    // AI Badges (Regression & Classification)
    const badgeRow = document.getElementById('ai-badges-row');
    badgeRow.innerHTML = ''; // Clear previous badges
    
    if (isMovie) {
        const tmdbId = item.tmdb_id || item.id;
        // 1. Genre (multi-label aware, comma-separated)
        fetch(`/predict/genre/${tmdbId}`)
            .then(r => r.json())
            .then(d => {
                try {
                    if (d && Array.isArray(d.genres) && d.genres.length > 0) {
                        const sorted = [...d.genres].sort((a, b) => (b.score || 0) - (a.score || 0));
                        const names = sorted.map(g => g.name).filter(Boolean);
                        if (names.length > 0) {
                            const text = `AI Genres: ${names.join(', ')}`;
                            addBadgeToRow(text);
                        }
                    } else if (d && d.genre) {
                        // Legacy single-genre response
                        addBadgeToRow(`AI Genre: ${d.genre}`);
                    }
                } catch (err) {
                    console.error('Error rendering genre badges', err);
                }
            })
            .catch(err => console.error('Genre prediction failed', err));

        // 2. Revenue
        fetch(`/movie/${tmdbId}/prediction`)
            .then(r => r.json())
            .then(d => {
                if (d && d.label) addBadgeToRow(`Forecast: ${d.label}`);
            })
            .catch(err => console.error('Revenue prediction failed', err));
    }

    // Related (Association + fallback) for both movies and TV
    const tmdbIdForRelated = item.tmdb_id || item.id;
    fetch(`/related/${tmdbIdForRelated}`)
        .then(r => r.json())
        .then(list => {
            try {
                const relatedContainerId = 'related-strip';
                let existing = document.getElementById(relatedContainerId);
                if (existing) existing.remove();

                if (!Array.isArray(list) || list.length === 0) return;

                const panel = document.createElement('div');
                panel.id = relatedContainerId;
                // More breathing room under the main info
                panel.style.marginTop = '40px';

                const heading = document.createElement('div');
                heading.textContent = 'More like this';
                heading.style.cssText = 'font-family:var(--font-header); font-size:2rem; margin-bottom:14px; color:var(--ink); border-bottom:1px solid var(--gold); display:inline-block;';
                panel.appendChild(heading);

                const row = document.createElement('div');
                // No horizontal scroll: a simple inline row of up to 5 cards
                row.style.cssText = 'display:flex;gap:14px;flex-wrap:nowrap;';

                list.slice(0, 5).forEach(rel => {
                    const card = document.createElement('div');
                    card.style.cssText = 'width:90px;cursor:pointer;flex-shrink:0;';

                    // Prefer explicit media_type from backend; fall back to heuristic.
                    const rType = rel.media_type || ((rel.first_air_date || rel.name) ? 'tv' : 'movie');
                    card.onclick = () => openModal(rel, rType);

                    const rName = rel.title || rel.name;
                    const rImg = rel.poster_path
                        ? `https://image.tmdb.org/t/p/w185${rel.poster_path}`
                        : 'https://via.placeholder.com/180x270';

                    card.innerHTML = `
                        <img src="${rImg}" style="width:100%;border-radius:6px;display:block;" loading="lazy" alt="${rName}">
                        <div style="margin-top:6px;font-size:0.75rem;color:var(--ink);opacity:0.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${rName}</div>
                    `;
                    row.appendChild(card);
                });

                panel.appendChild(row);
                // Append to main modal text column
                const descBlock = document.querySelector('#m-desc').parentElement;
                if (descBlock) descBlock.appendChild(panel);
            } catch (err) {
                console.error('Error rendering related strip', err);
            }
        })
        .catch(err => console.error('Related fetch failed', err));

    // State & Buttons
    currentTmdbId = item.tmdb_id || item.id;
    currentType = type;
    currentSeason = 1;
    currentEpisode = 1;
    
    // Like Button
    const likeBtn = document.createElement('button');
    likeBtn.className = 'pixel-btn'; // Use standard pixel button class
    likeBtn.innerHTML = '<i class="fa-regular fa-heart"></i>'; // Empty heart by default
    likeBtn.style.cssText = "margin-left:10px; font-size:1.6rem; padding: 12px 18px;"; // Match play button height
    likeBtn.onclick = () => toggleLike(item, likeBtn);
    
    const playBtn = document.querySelector('#play-btn');
    if (playBtn) {
        // Remove old like button if exists (to prevent duplicates on re-open)
        const oldLike = playBtn.parentNode.querySelector('.pixel-btn:not(#play-btn)');
        if(oldLike) oldLike.remove();
        
        playBtn.parentNode.insertBefore(likeBtn, playBtn.nextSibling);
    }

    if (playBtn) {
        playBtn.style.display = isMovie ? 'block' : 'none';
        playBtn.onclick = () => playVideo(currentType, currentTmdbId);
        playBtn.innerText = '▶ PLAY';
    }

    const epSection = document.getElementById('m-episodes');
    if (isMovie) {
        epSection.classList.add('hidden');
    } else {
        epSection.classList.remove('hidden');
        // For TV, show seasons/episodes list and hook clicks into playVideo
        loadSeasons(item.id);
    }
    
    modal.classList.add('active');
}

function addBadge(text) {
    const metaDiv = document.querySelector('.m-meta');
    const badge = document.createElement('span');
    badge.className = 'ai-badge';
    badge.style.cssText = "margin-left:10px; color:#ff0055; font-weight:700; border:1px solid #ff0055; padding:2px 6px; border-radius:4px; font-size:0.75rem;";
    badge.textContent = text;
    metaDiv.appendChild(badge);
}

function addBadgeToRow(text) {
    const badgeRow = document.getElementById('ai-badges-row');
    const span = document.createElement('span');
    span.className = 'ai-badge';
    span.textContent = text;
    badgeRow.appendChild(span);
}

function closeModal() { 
    document.getElementById('modal').classList.add('hidden'); 
    closePlayer(); 
}
function backdropClose(e) { if (e.target.id === 'modal') closeModal(); }

async function loadSeasons(showId) {
    const list = document.getElementById('ep-list');
    list.innerHTML = '<div style="padding:20px;text-align:center;color:#888">Accessing Archives...</div>';
    
    try {
        const res = await fetch(`/shows/${showId}/seasons`);
        const seasons = await res.json();
        list.innerHTML = '';
        
        if (!seasons || seasons.length === 0) {
             list.innerHTML = '<div style="padding:20px;text-align:center;color:#f55">No episodes indexed.</div>';
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
                    // FIX: Use runtime_minutes if available
                    const runtime = ep.runtime_minutes ? `${ep.runtime_minutes}m` : '45m';
                    
                    row.innerHTML = `
                        <div style="display:flex; gap:15px; align-items:center; width:100%">
                            <span style="color:var(--accent); font-weight:bold; width:30px">${ep.episode_number}</span>
                            <span style="flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${ep.title || 'Episode ' + ep.episode_number}</span>
                            <span style="color:#666; font-size:0.8rem; margin-right:10px;">${runtime}</span>
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
    SoundManager.play('click'); // Play click sound
    currentTmdbId = tmdbId; currentType = type; currentSeason = season; currentEpisode = episode;
    
    // Record Watch History
    sendInteraction('watch', tmdbId, type);

    const btn = document.querySelector('#play-btn');
    if(btn) btn.innerText = "HUNTING...";
    
    // Hide Info, Show Player
    document.querySelector('.modal-header').classList.add('hidden');
    document.querySelector('.close-btn').classList.add('hidden'); // Hide main close button
    document.getElementById('player-wrapper').classList.remove('hidden');

    loadSource('auto');
    if(btn) btn.innerText = "▶ PLAY";
}

function changeSource(provider) { loadSource(provider); }

async function loadSource(provider) {
    const artContainer = document.getElementById('artplayer-app');
    const iframe = document.getElementById('embed-frame');
    const select = document.getElementById('source-select');
    
    artContainer.style.display = 'none'; iframe.classList.add('hidden'); iframe.src = "about:blank";
    if(art) art.pause();
    
    const prevLabel = select.options[select.selectedIndex].text;
    select.options[select.selectedIndex].text = "Hunting...";

    try {
        if (provider === 'nautilus') {
            // Call MAIN FastAPI backend (relative path)
            const scraperUrl = `/scrape?tmdbId=${currentTmdbId}&type=${currentType}&season=${currentSeason}&episode=${currentEpisode}`;
            const res = await fetch(scraperUrl);
            const data = await res.json();
            
            if (data.streamUrl) {
                artContainer.style.display = 'block';
                if (!art) initArtPlayer();
                // Use the playlist URL directly (HLS)
                art.switchUrl(data.streamUrl);
                art.notice.show = 'Playing from Nautilus Scraper';
            } else {
                throw new Error("No stream found from scraper");
            }
        } else {
            const apiUrl = `/play/${currentType}/${currentTmdbId}?season=${currentSeason}&episode=${currentEpisode}&provider=${provider}`;
            const res = await fetch(apiUrl);
            const data = await res.json();

            if (data.type === 'embed') {
                iframe.classList.remove('hidden');
                iframe.src = data.url;
            } else {
                artContainer.style.display = 'block';
                if (!art) initArtPlayer();
                const proxyUrl = `/proxy_stream?url=${encodeURIComponent(data.url)}`;
                art.switchUrl(proxyUrl);
            }
        }
        select.options[select.selectedIndex].text = prevLabel;
    } catch (e) {
        console.error(e);
        select.options[select.selectedIndex].text = "Failed";
        setTimeout(() => select.options[select.selectedIndex].text = prevLabel, 2000);
        
        // Fallback to Auto if Nautilus fails
        if (provider === 'nautilus') {
             alert("Nautilus scraper failed. Falling back to AutoEmbed.");
             select.value = 'auto';
             changeSource('auto');
        }
    }
}

function initArtPlayer() {
    art = new Artplayer({
        container: '#artplayer-app',
        url: '',
        theme: '#0CAADC',
        volume: 1.0,
        autoplay: true,
        setting: true,
        fullscreen: true,
        fullscreenWeb: true,
        autoSize: true,
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
    
    // Exit Fullscreen if active
    if (document.fullscreenElement) {
        document.exitFullscreen().catch(err => console.log(err));
    }

    document.getElementById('embed-frame').src = "about:blank";
    document.getElementById('player-wrapper').classList.add('hidden');
    // Show Info Again
    document.querySelector('.modal-header').classList.remove('hidden');
    document.querySelector('.close-btn').classList.remove('hidden'); // Show main close button
}

async function refreshRandom(btn) {
    btn.disabled = true;
    btn.innerText = "Loading...";
    try {
        const res = await fetch(`/movies/random?limit=15`);
        const items = await res.json();
        const scroller = document.getElementById('random-scroller');
        scroller.innerHTML = '';
        
        items.forEach(item => {
            const card = document.createElement('div');
            card.className = 'card';
            let type = 'movie';
            
            const poster = item.poster_path 
                ? `https://image.tmdb.org/t/p/w500${item.poster_path}`
                : 'https://via.placeholder.com/200x300?text=No+Image';
                
            card.innerHTML = `
                <img src="${poster}" alt="${item.title || item.name}" loading="lazy" class="poster">
            `;
            card.onclick = () => openModal(item.tmdb_id, type);
            scroller.appendChild(card);
        });
    } catch (e) {
        console.error("Regen failed", e);
    } finally {
        btn.disabled = false;
        btn.innerText = "Regenerate";
    }
}

// --- INTERACTIONS ---
async function toggleLike(item, btn) {
    SoundManager.play('coin');
    const tmdbId = item.tmdb_id || item.id;
    const type = (item.first_air_date || item.name) ? 'tv' : 'movie';
    
    // Optimistic UI
    const isLiked = btn.classList.contains('liked');
    const action = isLiked ? 'dislike' : 'like'; // Toggle
    
    if (action === 'like') {
        btn.classList.add('liked');
        btn.innerHTML = '<i class="fa-solid fa-heart"></i>'; // Full heart
        btn.style.color = '#e50914';
        btn.style.borderColor = '#e50914';
    } else {
        btn.classList.remove('liked');
        btn.innerHTML = '<i class="fa-regular fa-heart"></i>'; // Empty heart
        btn.style.color = 'var(--ink)';
        btn.style.borderColor = 'var(--ink)';
    }
    
    await sendInteraction(action, tmdbId, type);
}

async function sendInteraction(action, tmdbId, type) {
    const guestId = getGuestId();
    try {
        await fetch('/interact', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                guest_id: guestId,
                item_id: tmdbId,
                media_type: type,
                action: action
            })
        });
    } catch (e) {
        console.error("Interaction failed", e);
    }
}