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

// Mobile menu toggle handler
document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('mobile-menu-toggle');
    const nav = document.getElementById('mobile-nav');
    if (toggle && nav) {
        toggle.addEventListener('click', (e) => {
            const open = nav.getAttribute('aria-hidden') === 'false';
            nav.setAttribute('aria-hidden', open ? 'true' : 'false');
            nav.style.display = open ? 'none' : 'block';
            toggle.innerHTML = open ? '<i class="fa-solid fa-bars"></i>' : '<i class="fa-solid fa-xmark"></i>';
        });
    }
});

// --- GUEST ID LOGIC ---
function getGuestId() {
    let gid = localStorage.getItem('nautilus_guest_id');
    if (!gid) {
        gid = crypto.randomUUID();
        localStorage.setItem('nautilus_guest_id', gid);
    }
    return gid;
}

// --- USER PREFERENCES (localStorage) ---
function setUserPrefs(prefs) {
    try {
        localStorage.setItem('nautilus_user_prefs', JSON.stringify(prefs));
    } catch (e) {
        console.error('Failed to save prefs', e);
    }
}

function getUserPrefs() {
    try {
        const raw = localStorage.getItem('nautilus_user_prefs');
        if (!raw) return null;
        return JSON.parse(raw);
    } catch (e) {
        return null;
    }
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
        btn.innerHTML = '<i class="fa-solid fa-sun"></i><span class="btn-text"> Light Mode</span>';
    } else {
        btn.innerHTML = '<i class="fa-solid fa-moon"></i><span class="btn-text"> Dark Mode</span>';
    }
}

// Init Theme
const savedTheme = localStorage.getItem('nautilus_theme') || 'light';
document.body.setAttribute('data-theme', savedTheme);
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.querySelector('.theme-toggle');
    if(btn) {
            if(savedTheme === 'dark') {
                btn.innerHTML = '<i class="fa-solid fa-sun"></i><span class="btn-text"> Light Mode</span>';
            } else {
                btn.innerHTML = '<i class="fa-solid fa-moon"></i><span class="btn-text"> Dark Mode</span>';
            }
    }
    
    // Show disclaimer modal on first visit
    showDisclaimerIfFirstTime();
});

// Adjust main padding dynamically so content isn't hidden under the fixed header
function adjustMainPadding() {
    try {
        const header = document.querySelector('header');
        const main = document.querySelector('main');
        if (!header || !main) return;
        const rect = header.getBoundingClientRect();
        const extra = 20; // margin below header
        main.style.paddingTop = `${Math.ceil(rect.height + extra)}px`;
    } catch (e) { /* ignore */ }
}

// Run on load and resize
document.addEventListener('DOMContentLoaded', () => {
    adjustMainPadding();
    let resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(adjustMainPadding, 120);
    });
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

// Helper: Fisher-Yates Shuffle
function shuffle(array) {
    if (!Array.isArray(array)) return [];
    let currentIndex = array.length, randomIndex;
    while (currentIndex != 0) {
        randomIndex = Math.floor(Math.random() * currentIndex);
        currentIndex--;
        [array[currentIndex], array[randomIndex]] = [array[randomIndex], array[currentIndex]];
    }
    return array;
}

// --- NAVIGATION & SIDEBAR ---
function setActiveNav(title) {
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.remove('active');
        if(el.getAttribute('title') === title) el.classList.add('active');
    });
}

function focusSearch() {
    const input = document.getElementById('search-input');
    if(input) {
        input.focus();
        setActiveNav('Search');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

async function loadCollection(type, page=1) {
    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:40px; text-align:center;">Navigating Charts...</div>';
    window.scrollTo(0,0);
    
    let title = '';
    let endpoint = '';
    const PAGE_SIZE = 100;
    
    if (type === 'watchlist') {
         title = 'Watchlist';
         endpoint = `/collections/watchlist/${getGuestId()}`;
         setActiveNav('Watchlist');
    } else if (type === 'movies') {
        title = 'All Movies';
        endpoint = `/movies?limit=${PAGE_SIZE}&skip=${(page-1)*PAGE_SIZE}`;
        setActiveNav('Movies');
    } else if (type === 'tv') {
        title = 'All TV Shows';
        endpoint = `/shows?limit=${PAGE_SIZE}&skip=${(page-1)*PAGE_SIZE}`;
        setActiveNav('TV Shows');
    }

    try {
        const res = await fetch(endpoint);
        let items = await res.json();
        
        // Reverse watchlist to show newest first
        if (type === 'watchlist' && Array.isArray(items)) items = items.reverse();

        container.innerHTML = '';
        if (Array.isArray(items) && items.length > 0) {
            // Full Grid Layout for Collections
            const wrapper = document.createElement('div');
            wrapper.className = 'row-wrapper';
            
            // Helper: build pagination bar
            function makePaginationBar() {
                const bar = document.createElement('div');
                bar.style.cssText = "display:flex; justify-content:space-between; align-items:center; margin:1rem 0;";
                const btnCss = "padding:8px 20px; border:2px solid var(--gold); background:rgba(0,0,0,0.3); color:var(--ink); cursor:pointer; font-family:var(--font-pixel); font-size:0.9rem; border-radius:4px;";
                
                const prev = document.createElement('button');
                prev.innerText = "\u00AB Prev Page";
                prev.style.cssText = btnCss;
                prev.onclick = () => loadCollection(type, page - 1);
                if (page <= 1) prev.style.visibility = 'hidden';

                const label = document.createElement('span');
                label.style.cssText = "font-family:var(--font-header); font-size:1.3rem; color:var(--ink);";
                label.textContent = `Page ${page}`;

                const next = document.createElement('button');
                next.innerText = "Next Page \u00BB";
                next.style.cssText = btnCss;
                next.onclick = () => loadCollection(type, page + 1);
                if (items.length < PAGE_SIZE) next.style.visibility = 'hidden';

                bar.appendChild(prev);
                bar.appendChild(label);
                bar.appendChild(next);
                return bar;
            }

            wrapper.innerHTML = `<div class="row-title">${title}</div>`;
            wrapper.appendChild(makePaginationBar());
            
            const grid = document.createElement('div');
            grid.style.cssText = "display:flex; flex-wrap:wrap; gap:20px; padding:20px 0; justify-content:center;";
            
            items.forEach(item => {
                // Filter out items without posters or names
                if (!item.poster_path || (!item.title && !item.name)) return;

                const card = document.createElement('div');
                card.className = 'card';
                let mType = item.media_type;
                if (!mType) mType = (type === 'tv') ? 'tv' : 'movie';
                
                card.onclick = () => openModal(item, mType);
                const name = item.title || item.name;
                const imgSrc = `https://image.tmdb.org/t/p/w500${item.poster_path}`;
                card.innerHTML = `<img src="${imgSrc}" class="poster" loading="lazy" alt="${name}">`;
                grid.appendChild(card);
            });
            
            wrapper.appendChild(grid);
            wrapper.appendChild(makePaginationBar());

            container.appendChild(wrapper);
        } else {
            container.innerHTML = `<div style="padding:50px; text-align:center; font-size:1.5rem; color:#888;">No charts found for ${title}. <button onclick="loadCollection('${type}', ${page-1})">Go Back</button></div>`;
        }
    } catch (e) {
        console.error(e);
        container.innerHTML = '<div style="padding:40px; color:#f55">Navigation Error.</div>';
    }
}

// --- HOME LOADING (Data-Driven) ---
async function loadHome() {
    setActiveNav('Home');
    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:40px; text-align:center;">Initializing...</div>';
    
    try {
        // Parallel fetch
        const [resTrending, resTopMovies, resNewMovies, resTopShows, resNewShows, resRecs, resCollections, resAnimated, resRandom] = await Promise.all([
            fetch(`/trending?days=7&limit=30`),
            fetch(`/movies/top_rated_alltime?limit=200`),
            fetch(`/movies/new_releases?days=90&limit=80`),
            fetch(`/shows/top_rated_alltime?limit=200`),
            fetch(`/shows/new_releases?days=90&limit=80`),
            (function(){
                const prefs = localStorage.getItem('nautilus_user_prefs');
                const headers = prefs ? { 'X-User-Prefs': prefs } : {};
                return fetch(`/recommend/guest/${getGuestId()}`, { headers });
            })(),
            fetch(`/collections/ai`),
            fetch(`/movies/genre/16?limit=20`), // animated spotlight
            fetch(`/movies/random?limit=18`)
        ]);

        const trending = await resTrending.json();
        const moviesTop = await resTopMovies.json();
        const moviesNew = await resNewMovies.json();
        const showsTop = await resTopShows.json();
        const showsNew = await resNewShows.json();
        const recs = await resRecs.json();
        const collections = await resCollections.json();
        const animated = await resAnimated.json();
        const random = await resRandom.json();
        
        const trendingMovies = (trending && trending.movies) ? trending.movies : [];
        const trendingShows = (trending && trending.shows) ? trending.shows : [];
        const curated1 = collections && collections.cluster_1 ? shuffle(collections.cluster_1) : null;
        const curated2 = collections && collections.cluster_2 ? shuffle(collections.cluster_2) : null;
        const curated3 = collections && collections.cluster_3 ? shuffle(collections.cluster_3) : null;

        container.innerHTML = '';

        // 1. RecSys Row (only if user has real interactions — endpoint returns {source:'none'} when no interactions)
        if(Array.isArray(recs) && recs.length > 0) createRow('For You', recs, 'mixed');

        // 2. Trending
        if(trendingMovies.length > 0) createRow('Based on Your Interests (Movies)', trendingMovies, 'movie');
        if(trendingShows.length > 0) createRow('Based on Your Interests (Series)', trendingShows, 'tv');

        // 3. Top Rated then New
        if (moviesTop && moviesTop.length > 0) createRow('Top Rated', moviesTop, 'movie');
        if (moviesNew && moviesNew.length > 0) createRow('New Releases', moviesNew, 'movie');
        if (showsTop && showsTop.length > 0) createRow('Top Rated (Series)', showsTop, 'tv');
        if (showsNew && showsNew.length > 0) createRow('New Releases (Series)', showsNew, 'tv');
        
        // 4. Curated Collections
        if(curated2 && curated2.items && curated2.items.length > 0) createRow(curated2.name || 'Critics\' Picks', curated2.items, 'movie');
        if(curated3 && curated3.items && curated3.items.length > 0) createRow(curated3.name || 'Hidden Gems', curated3.items, 'movie');
        if(curated1 && curated1.items && curated1.items.length > 0 && trendingMovies.length === 0) createRow(curated1.name || 'Trending Now', curated1.items, 'movie');

        // 5. Spotlight Genres
        if(animated.length > 0) createRow('Animated Worlds', shuffle(animated), 'movie');

        // 6. Random Row with Regen
        if(random.length > 0) createRow('Random Picks', shuffle(random), 'movie', true);

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

    // Filter out obviously-empty or malformed items (no title/name or missing/invalid poster)
    const filtered = items.filter(item => {
        const hasTitle = !!(item && (item.title || item.name));
        let poster = item && item.poster_path;
        // Treat literal strings 'undefined'/'null' and empty as missing
        const badPoster = poster === undefined || poster === null || String(poster).trim() === '' || String(poster).toLowerCase() === 'undefined' || String(poster).toLowerCase() === 'null';
        const hasPoster = !badPoster;
        return hasTitle && hasPoster;
    });

    if (filtered.length === 0) {
        // Nothing valid to show in this row; skip rendering it
        return;
    }

    filtered.forEach(item => {
        const card = document.createElement('div');
        card.className = 'card';
        
        // LOGIC FIX: If fixedType is passed (e.g. 'tv'), use it. 
        // Otherwise try to guess from item properties.
        let type = fixedType;
        if (!type || type === 'mixed') {
             // Check explicit media_type first (from recommend endpoint)
             if (item.media_type === 'tv' || item.media_type === 'movie') {
                 type = item.media_type;
             } else {
                 type = (item.name || item.first_air_date) ? 'tv' : 'movie';
             }
        }

        // Pass the determined type to openModal
        card.onclick = () => openModal(item, type);
        
    const name = item.title || item.name;
    const imgSrc = item.poster_path && String(item.poster_path).toLowerCase() !== 'undefined' ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/300x450';
        
        card.innerHTML = `<img src="${imgSrc}" class="poster" loading="lazy" alt="${name}">`;
        scroller.appendChild(card);
    });

    // Arrows (scroll-aware visibility)
    const prevBtn = document.createElement('button');
    prevBtn.className = 'row-arrow prev';
    prevBtn.innerHTML = '&#8249;';
    prevBtn.onclick = () => { SoundManager.play('wood'); scroller.scrollBy({ left: -1000, behavior: 'smooth' }); };
    
    const nextBtn = document.createElement('button');
    nextBtn.className = 'row-arrow next';
    nextBtn.innerHTML = '&#8250;';
    nextBtn.onclick = () => { SoundManager.play('wood'); scroller.scrollBy({ left: 1000, behavior: 'smooth' }); };

    // Hide arrows when at start/end of scroll
    function updateArrowVisibility() {
        const atStart = scroller.scrollLeft <= 5;
        const atEnd = scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 5;
        prevBtn.style.opacity = atStart ? '0' : '1';
        prevBtn.style.pointerEvents = atStart ? 'none' : 'auto';
        nextBtn.style.opacity = atEnd ? '0' : '1';
        nextBtn.style.pointerEvents = atEnd ? 'none' : 'auto';
    }
    scroller.addEventListener('scroll', updateArrowVisibility);
    // Also check after images load
    setTimeout(updateArrowVisibility, 100);
    setTimeout(updateArrowVisibility, 500);

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
                            const text = `Genres: ${names.join(', ')}`;
                            addBadgeToRow(text);
                        }
                    } else if (d && d.genre) {
                        // Legacy single-genre response
                        addBadgeToRow(`Genre: ${d.genre}`);
                    }
                } catch (err) {
                    console.error('Error rendering genre badges', err);
                }
            })
            .catch(err => console.error('Genre prediction failed', err));
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
    
    // --- Interaction Buttons (Like & Watchlist) ---
    const btnGroup = document.createElement('div');
    btnGroup.style.display = 'inline-flex';
    btnGroup.style.gap = '10px';
    btnGroup.style.marginLeft = '10px';
    btnGroup.id = 'modal-actions';

    // Helper: Create Button
    const createActionBtn = (iconClass, action) => {
        const btn = document.createElement('button');
        btn.className = 'pixel-btn';
        btn.innerHTML = `<i class="${iconClass}"></i>`;
        btn.dataset.action = action;
        btn.style.cssText = "font-size:1.6rem; padding: 12px 18px;";
        return btn;
    };

    const likeBtn = createActionBtn('fa-regular fa-heart', 'like'); // empty heart
    const listBtn = createActionBtn('fa-solid fa-plus', 'watchlist'); // plus

    likeBtn.onclick = () => toggleInteraction('like', item, likeBtn);
    listBtn.onclick = () => toggleInteraction('watchlist', item, listBtn);

    btnGroup.appendChild(likeBtn);
    btnGroup.appendChild(listBtn);
    
    const playBtn = document.querySelector('#play-btn');
    if (playBtn) {
        // Cleanup old buttons/groups
        const oldGroup = document.getElementById('modal-actions');
        if(oldGroup) oldGroup.remove();
        // Remove legacy like button if exists
        const oldLike = playBtn.parentNode.querySelector('.pixel-btn:not(#play-btn)');
        if(oldLike) oldLike.remove();
        
        playBtn.parentNode.insertBefore(btnGroup, playBtn.nextSibling);
    }

    // Check Status
    checkInteractionStatus(item, likeBtn, listBtn);

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
        // Prefer tmdb_id when available (some rows come from ML cache with only tmdb_id)
        const seasonTarget = item.tmdb_id || item.id;
        loadSeasons(seasonTarget);
    }

    // Lazy-fill missing overview/year without blocking modal open
    (function(){
        const tmdbId = item.tmdb_id || item.id;
        if (!tmdbId) return;
        const descEl = document.getElementById('m-desc');
        const yearEl = document.getElementById('m-year');
        const missingOverview = !(item.overview && item.overview.trim());
        const missingYear = !(item.release_date || item.first_air_date);
        if (!missingOverview && !missingYear) return;
        // Fetch lightweight media details; don't block UI
        fetch(`/media/${tmdbId}`).then(r => r.json()).then(d => {
            try {
                if (d && d.overview && missingOverview) descEl.textContent = d.overview;
                const date = d.release_date || d.first_air_date || '';
                if (date && missingYear) yearEl.textContent = date.split('-')[0];
            } catch (e) { /* ignore */ }
        }).catch(() => {});
    })();
    
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
/* demo video commit */
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
    document.getElementById('player-wrapper').classList.remove('hidden');

    // Mark modal as player-open so CSS can expand the player area
    const modal = document.getElementById('modal');
    if (modal) modal.classList.add('player-open');

    const defaultSource = localStorage.getItem('nautilus_default_source') || 'VidSrc.to';
    loadSource(defaultSource);
    // Sync dropdown to reflect the chosen source
    const srcSel = document.getElementById('source-select');
    if (srcSel) srcSel.value = defaultSource;
    if(btn) btn.innerText = "▶ PLAY";
    
    // Start progress tracking (saves every 3s)
    startProgressTracking();
    // Resume from saved progress
    const saved = getStoredProgress(type, tmdbId);
    if (saved && saved.time > 10) {
        setTimeout(() => {
            if (art && art.duration) {
                art.currentTime = saved.time;
                art.notice.show = `Resumed at ${formatTime(saved.time)}`;
            }
        }, 2500);
    }
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
        select.options[select.selectedIndex].text = prevLabel;
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
    const modal = document.getElementById('modal');
    if (modal) modal.classList.remove('player-open');
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
            card.onclick = () => openModal(item, type);
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
async function checkInteractionStatus(item, likeBtn, listBtn) {
    const tmdbId = item.tmdb_id || item.id;
    let type = item.media_type;
    if (!type) type = (item.first_air_date || item.name) ? 'tv' : 'movie';
    const gid = getGuestId();

    const updateBtn = (btn, active, iconActive, iconInactive, color) => {
        if(active) {
            btn.innerHTML = `<i class="${iconActive}" style="color:${color}"></i>`;
            btn.dataset.active = "true";
        } else {
            btn.innerHTML = `<i class="${iconInactive}"></i>`;
            btn.dataset.active = "false";
        }
    };

    // Check Like
    fetch(`/interactions/status?guest_id=${gid}&tmdb_id=${tmdbId}&media_type=${type}&action=like`)
        .then(r=>r.json())
        .then(d => updateBtn(likeBtn, d.active, 'fa-solid fa-heart', 'fa-regular fa-heart', '#ff0055'))
        .catch(()=>{});

    // Check Watchlist
    fetch(`/interactions/status?guest_id=${gid}&tmdb_id=${tmdbId}&media_type=${type}&action=watchlist`)
        .then(r=>r.json())
        .then(d => updateBtn(listBtn, d.active, 'fa-solid fa-check', 'fa-solid fa-plus', '#00ffaa'))
        .catch(()=>{});
}

async function toggleInteraction(actionType, item, btn) {
    SoundManager.play('coin');
    const tmdbId = item.tmdb_id || item.id;
    let type = item.media_type;
    if (!type) type = (item.first_air_date || item.name) ? 'tv' : 'movie';
    const isActive = btn.dataset.active === "true";

    let apiAction = actionType;
    if (actionType === 'like' && isActive) apiAction = 'dislike';
    if (actionType === 'watchlist' && isActive) apiAction = 'remove_watchlist';
    
    // Optimistic
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    
    await sendInteraction(apiAction, tmdbId, type);
    
    // Re-render based on toggled state
    if (actionType === 'like') {
        if (apiAction === 'like') {
            btn.innerHTML = '<i class="fa-solid fa-heart" style="color:#ff0055"></i>';
            btn.dataset.active = "true";
        } else {
            btn.innerHTML = '<i class="fa-regular fa-heart"></i>';
            btn.dataset.active = "false";
        }
    } else if (actionType === 'watchlist') {
        if (apiAction === 'watchlist') {
             btn.innerHTML = '<i class="fa-solid fa-check" style="color:#00ffaa"></i>';
             btn.dataset.active = "true";
        } else {
             btn.innerHTML = '<i class="fa-solid fa-plus"></i>';
             btn.dataset.active = "false";
        }
    }
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

// --- RANDOM MOVIE (Header Button) ---
async function playRandomMovie() {
    try {
        const res = await fetch('/movies/random?limit=1');
        const items = await res.json();
        if (items.length > 0 && items[0].poster_path) {
            openModal(items[0], 'movie');
        } else {
            // Try again
            const res2 = await fetch('/movies/random?limit=5');
            const items2 = await res2.json();
            const valid = items2.find(i => i.poster_path);
            if (valid) openModal(valid, 'movie');
        }
    } catch(e) {
        console.error('Random movie failed', e);
    }
}

// --- KEYBOARD SHORTCUTS (Sudoflix-Inspired) ---
document.addEventListener('keydown', (e) => {
    // Don't trigger shortcuts when typing in search
    if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) return;
    
    const modal = document.getElementById('modal');
    const playerWrapper = document.getElementById('player-wrapper');
    const isPlayerOpen = modal && !modal.classList.contains('hidden') && playerWrapper && !playerWrapper.classList.contains('hidden');
    
    // Player-specific shortcuts (only when player is visible)
    if (isPlayerOpen && art) {
        switch(e.key) {
            case ' ':
            case 'k':
            case 'K':
                e.preventDefault();
                art.playing ? art.pause() : art.play();
                break;
            case 'f':
            case 'F':
                e.preventDefault();
                art.fullscreen = !art.fullscreen;
                break;
            case 'm':
            case 'M':
                e.preventDefault();
                art.muted = !art.muted;
                break;
            case 'ArrowLeft':
                e.preventDefault();
                art.currentTime = Math.max(0, art.currentTime - 5);
                break;
            case 'ArrowRight':
                e.preventDefault();
                art.currentTime = Math.min(art.duration, art.currentTime + 5);
                break;
            case 'ArrowUp':
                e.preventDefault();
                art.volume = Math.min(1, art.volume + 0.1);
                break;
            case 'ArrowDown':
                e.preventDefault();
                art.volume = Math.max(0, art.volume - 0.1);
                break;
            case 'j':
            case 'J':
                e.preventDefault();
                art.currentTime = Math.max(0, art.currentTime - 10);
                break;
            case 'l':
            case 'L':
                e.preventDefault();
                art.currentTime = Math.min(art.duration, art.currentTime + 10);
                break;
        }
        return;
    }
    
    // Global shortcuts
    switch(e.key) {
        case '/':
            e.preventDefault();
            document.getElementById('search-input').focus();
            break;
        case 'Escape':
            if (modal && !modal.classList.contains('hidden')) {
                closeModal();
            }
            break;
    }
});

// --- WATCH PROGRESS PERSISTENCE (Sudoflix-Inspired) ---
let progressSaveInterval = null;

function startProgressTracking() {
    if (progressSaveInterval) clearInterval(progressSaveInterval);
    progressSaveInterval = setInterval(() => {
        if (!art || !art.playing || !currentTmdbId) return;
        const progress = {
            time: art.currentTime,
            duration: art.duration,
            percentage: art.duration ? (art.currentTime / art.duration * 100) : 0,
            updatedAt: Date.now()
        };
        const key = `nautilus_progress_${currentType}_${currentTmdbId}`;
        if (currentType === 'tv') {
            progress.season = currentSeason;
            progress.episode = currentEpisode;
        }
        try { localStorage.setItem(key, JSON.stringify(progress)); } catch(e) {}
    }, 3000); // Save every 3 seconds like sudoflix
}

function getStoredProgress(type, tmdbId) {
    try {
        const key = `nautilus_progress_${type}_${tmdbId}`;
        const data = localStorage.getItem(key);
        if (!data) return null;
        const p = JSON.parse(data);
        // Only resume if not near end (>95% = finished)
        if (p.percentage && p.percentage > 95) return null;
        return p;
    } catch(e) { return null; }
}

function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

// --- SETTINGS PANEL ---
function openSettings() {
    const overlay = document.getElementById('settings-overlay');
    overlay.classList.remove('hidden');
    // Populate current values
    const defaultSrc = localStorage.getItem('nautilus_default_source') || 'VidSrc.to';
    const sel = document.getElementById('settings-default-source');
    if (sel) sel.value = defaultSrc;
    const gidEl = document.getElementById('settings-guest-id');
    if (gidEl) gidEl.textContent = getGuestId();
    // Save on change
    sel.onchange = () => {
        localStorage.setItem('nautilus_default_source', sel.value);
    };
}

function closeSettings() {
    document.getElementById('settings-overlay').classList.add('hidden');
}

function clearWatchProgress() {
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith('nautilus_progress_')) keys.push(key);
    }
    keys.forEach(k => localStorage.removeItem(k));
    alert(`Cleared ${keys.length} watch progress entries.`);
}

function resetPreferences() {
    if (!confirm('This will clear all your likes, watchlist, and viewing preferences. Continue?')) return;
    // Clear local prefs
    localStorage.removeItem('nautilus_user_prefs');
    // Clear server-side interactions
    fetch(`/interactions/reset/${getGuestId()}`, { method: 'POST' }).catch(() => {});
    alert('Preferences reset. Reload to see changes.');
    location.reload();
}