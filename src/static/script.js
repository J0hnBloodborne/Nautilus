const API_BASE = "";
let currentTab = 'movies';
var videoPlayer = null;

function init() { loadContent(currentTab); }

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentTab = this.dataset.tab;
            loadContent(currentTab);
        });
    });
    loadContent(currentTab);
});

async function loadContent(type) {
    const container = document.getElementById('content-area');
    container.innerHTML = '<div style="padding:40px; text-align:center;">Loading catalog...</div>';
    try {
        const res = await fetch(`/${type}?limit=60`);
        const items = await res.json();
        container.innerHTML = '';
        
        createRow('Trending Now', items.slice(0, 15));
        createRow('New Releases', items.slice(15, 30));
        createRow('Top Rated', items.slice(30, 45));
        createRow('From The Vault', items.slice(45));
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
        const imgSrc = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/360x540';
        card.innerHTML = `<img src="${imgSrc}" class="poster" loading="lazy">`;
        scroller.appendChild(card);
    });

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
    
    // CRITICAL: Ensure Grid Layout is visible
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

    const playBtn = document.querySelector('#play-btn');
    playBtn.onclick = () => playVideo(currentTab === 'shows' ? 'tv' : 'movie', item.tmdb_id);

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

// --- PLAYER ---
async function playVideo(type, tmdbId, season=1, episode=1) {
    const btn = document.querySelector('#play-btn');
    btn.innerText = "CONNECTING...";
    
    try {
        const rawUrl = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4";
        const proxyUrl = `/proxy_stream?url=${encodeURIComponent(rawUrl)}`;

        // Toggle UI
        document.getElementById('modal-content-wrapper').style.display = 'none';
        document.getElementById('player-wrapper').classList.remove('hidden');

        if (!videoPlayer) videoPlayer = videojs('my-video');
        
        videoPlayer.src({ type: 'video/mp4', src: proxyUrl });
        videoPlayer.play();
        btn.innerText = "▶ PLAY";
    } catch (e) {
        btn.innerText = "ERROR";
    }
}

function closePlayer() {
    if (videoPlayer) videoPlayer.pause();
    document.getElementById('player-wrapper').classList.add('hidden');
    document.getElementById('modal-content-wrapper').style.display = 'grid';
}

document.addEventListener('DOMContentLoaded', init);