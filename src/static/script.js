// Base API path (relative since FastAPI serves at root)
const API_BASE = "";

// State
let currentTab = 'movies';

function init() {
    loadContent(currentTab);
}

// Tab switching logic for new layout
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
    container.innerHTML = '<div style="padding:40px">Loading catalog...</div>';

    try {
        const res = await fetch(`/${type}?limit=60`);
        const items = await res.json();
        container.innerHTML = '';

        // Simple categorization heuristics (can be replaced with real metadata later)
        const trending = items.slice(0, 15);
        const newReleases = items.slice(15, 30);
        const topRated = items.slice(30, 45);
        const vault = items.slice(45);

        createRow('Trending Now', trending);
        createRow('New Releases', newReleases);
        createRow('Top Rated', topRated);
        if (vault.length) createRow('From The Vault', vault);
    } catch (err) {
        container.innerHTML = `<div style="padding:40px;color:#f55">Failed to load: ${err}</div>`;
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
        const imgSrc = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/300x450?text=No+Image';
        card.innerHTML = `<img src="${imgSrc}" class="poster" loading="lazy" alt="${item.title}">`;
        scroller.appendChild(card);
    });

    // Navigation arrows (now further out)
    const prevBtn = document.createElement('button');
    prevBtn.className = 'row-arrow prev';
    prevBtn.innerHTML = '&#8249;';
    prevBtn.onclick = () => scroller.scrollBy({ left: - (getScrollAmount()), behavior: 'smooth' });

    const nextBtn = document.createElement('button');
    nextBtn.className = 'row-arrow next';
    nextBtn.innerHTML = '&#8250;';
    nextBtn.onclick = () => scroller.scrollBy({ left: getScrollAmount(), behavior: 'smooth' });

    section.appendChild(prevBtn);
    section.appendChild(nextBtn);
    section.appendChild(scroller);
    container.appendChild(section);
}

function getScrollAmount() {
    // Approx width of 6 cards including gaps
    const card = document.querySelector('.card');
    if (!card) return 1000;
    const style = getComputedStyle(card);
    const cardWidth = card.offsetWidth + parseInt(style.marginLeft || 0) + parseInt(style.marginRight || 0) + 32; // add gap fallback
    return cardWidth * 6;
}

// --- MODAL LOGIC ---
function openModal(item) {
    const modal = document.getElementById('modal');
    document.getElementById('m-title').textContent = item.title;
    document.getElementById('m-desc').textContent = item.overview || 'No description available.';
    document.getElementById('m-poster').src = item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : 'https://via.placeholder.com/350x500?text=No+Image';
    // Popularity/match formatting
    let score = '';
    if (typeof item.popularity_score === 'number') {
        let val = item.popularity_score;
        // If appears to be a 0-1 float, scale
        if (val <= 1) val = val * 100;
        val = Math.max(0, Math.min(100, Math.round(val)));
        score = `${val}% Match`;
    }
    document.getElementById('m-score').textContent = score;
    document.getElementById('m-year').textContent = (item.release_date || '').split('-')[0] || '';

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
}

function backdropClose(e) {
    if (e.target.id === 'modal') closeModal();
}

async function loadSeasons(showId) {
    const list = document.getElementById('ep-list');
    list.innerHTML = '<div style="padding:10px">Loading seasons...</div>';
    try {
        const res = await fetch(`/shows/${showId}/seasons`);
        if (!res.ok) throw new Error('Endpoint error');
        const data = await res.json();
        // Ensure seasons structure
        renderSeasons(Array.isArray(data.seasons) ? data.seasons : []);
    } catch (err) {
        list.innerHTML = `<div style="padding:10px;color:#f55">Failed to load seasons: ${err}</div>`;
    }
}

function renderSeasons(seasons) {
    const list = document.getElementById('ep-list');
    list.innerHTML = '';
    if (!seasons.length) {
        list.innerHTML = '<div style="padding:10px;color:#aaa">No seasons available.</div>';
        return;
    }
    seasons.forEach(season => {
        const header = document.createElement('div');
        header.style.padding = '10px';
        header.style.fontWeight = '600';
        header.style.color = '#fff';
        header.textContent = `Season ${season.season_number || ''}: ${season.name || ''}`;
        list.appendChild(header);
        (season.episodes || []).forEach(ep => {
            const epDiv = document.createElement('div');
            epDiv.className = 'ep-item';
            const duration = '45m'; // Placeholder; backend has no duration field
            epDiv.innerHTML = `<span>Ep ${ep.episode_number}: ${ep.title || 'Untitled'}</span><span style="color:#999">${duration}</span>`;
            list.appendChild(epDiv);
        });
    });
}

// Initialize after DOM load
document.addEventListener('DOMContentLoaded', init);