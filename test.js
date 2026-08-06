
        // Navbar Scroll Effect
        window.addEventListener('scroll', () => {
            const navbar = document.getElementById('navbar');
            if (window.scrollY > 50) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });

        // Populate Years in Filter
        const yearSelect = document.getElementById('filter-year');
        const currentYear = new Date().getFullYear();
        for(let y = currentYear; y >= 1888; y--) {
            const opt = document.createElement('option');
            opt.value = y;
            opt.innerText = y;
            yearSelect.appendChild(opt);
        }

        // Tab Switching
        function switchTab(tabId) {
            document.querySelectorAll('.nav-links div').forEach(el => el.classList.remove('active'));
            event.target.classList.add('active');
            
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + tabId).classList.add('active');
            window.scrollTo(0, 0);
        }

        // Fetch Data on Load
        window.onload = async () => {
            await loadTabInicio();
            await loadTabPeliculas();
            await loadTabSeries();
            await loadTabAnime();
            await loadTabStreaming();
        };

        async function fetchAPI(endpoint) {
            try {
                const res = await fetch(endpoint);
                const data = await res.json();
                return data.success ? data.results : [];
            } catch(e) {
                console.error(e);
                return [];
            }
        }

        function createCard(item, isTrailer = false) {
            const isTv = item.media_type === 'tv';
            const title = isTv ? item.name : item.title;
            const date = item.release_date || item.first_air_date || '';
            const year = date ? date.split('-')[0] : '';
            
            const poster = item.poster_path 
                ? `https://image.tmdb.org/t/p/w300${item.poster_path}` 
                : 'https://via.placeholder.com/300x450/1e293b/475569?text=No+Image';

            let badgeHtml = '';
            if(isTrailer) {
                badgeHtml = `<span class="badge" style="background:#e50914;color:white">PRÓXIMAMENTE</span>`;
            } else {
                badgeHtml = `<span class="badge">${isTv ? 'SERIE' : 'PELÍCULA'}</span>`;
            }

            const card = document.createElement('div');
            card.className = 'card';
            card.onclick = () => handleItemSelect(item, isTrailer);
            
            card.innerHTML = `
                <img src="${poster}" alt="${title}" loading="lazy">
                <div class="card-info">
                    <h3 class="card-title">${title}</h3>
                    <div class="card-meta">
                        ${year ? `<span>${year}</span>` : ''}
                        ${badgeHtml}
                        <span style="margin-left:auto">⭐ ${item.vote_average ? item.vote_average.toFixed(1) : 'NR'}</span>
                    </div>
                </div>
            `;
            return card;
        }

        function setHero(containerPrefix, item, isTrailer = false) {
            if(!item) return;
            const isTv = item.media_type === 'tv';
            const title = isTv ? item.name : item.title;
            const backdrop = item.backdrop_path 
                ? `https://image.tmdb.org/t/p/original${item.backdrop_path}` 
                : '';
            
            document.getElementById(`${containerPrefix}-bg`).src = backdrop;
            document.getElementById(`${containerPrefix}-title`).innerText = title;
            document.getElementById(`${containerPrefix}-overview`).innerText = item.overview || 'Sin descripción disponible.';
            
            const btns = document.getElementById(`${containerPrefix}-btns`);
            btns.innerHTML = '';
            
            const playBtn = document.createElement('button');
            playBtn.className = 'btn btn-play';
            playBtn.innerHTML = '▶ Reproducir';
            playBtn.onclick = () => handleItemSelect(item, isTrailer);
            
            const infoBtn = document.createElement('button');
            infoBtn.className = 'btn btn-info';
            infoBtn.innerHTML = 'ℹ Más información';
            infoBtn.onclick = () => showInfoModal(isTv ? 'tv' : 'movie', item.id);
            
            btns.appendChild(playBtn);
            btns.appendChild(infoBtn);
        }

        async function loadTabInicio() {
            // 1. En cartelera
            const cartelera = await fetchAPI('/api/tmdb/now_playing_theaters');
            if(cartelera.length > 0) {
                setHero('hero-inicio', cartelera[0]);
                const row = document.getElementById('row-cartelera');
                cartelera.forEach(i => row.appendChild(createCard(i)));
            }

            // 2. Últimamente nuevo (mixed recent discover)
            const recent = await fetchAPI('/api/tmdb/discover?type=movie&year=' + currentYear);
            const rowUlt = document.getElementById('row-ultimamente');
            recent.forEach(i => rowUlt.appendChild(createCard(i)));

            // 3. Estrenos
            const estrenos = await fetchAPI('/api/tmdb/upcoming');
            const rowEst = document.getElementById('row-estrenos');
            estrenos.forEach(i => rowEst.appendChild(createCard(i, true)));
        }

        async function loadTabPeliculas() {
            const popMovies = await fetchAPI('/api/tmdb/popular/movies');
            if(popMovies.length > 0) {
                setHero('hero-peliculas', popMovies[Math.floor(Math.random() * 5)]);
                const row = document.getElementById('row-populares-peliculas');
                popMovies.forEach(i => row.appendChild(createCard(i)));
            }
        }

        async function loadTabSeries() {
            const popSeries = await fetchAPI('/api/tmdb/popular/series');
            if(popSeries.length > 0) {
                setHero('hero-series', popSeries[Math.floor(Math.random() * 5)]);
                const row = document.getElementById('row-populares-series');
                popSeries.forEach(i => row.appendChild(createCard(i)));
            }
        }

        async function loadTabAnime() {
            const popAnime = await fetchAPI('/api/tmdb/popular/anime');
            if(popAnime.length > 0) {
                setHero('hero-anime', popAnime[Math.floor(Math.random() * 5)]);
                const row = document.getElementById('row-populares-anime');
                popAnime.forEach(i => row.appendChild(createCard(i)));
            }
        }

        async function loadTabStreaming() {
            const trending = await fetchAPI('/api/tmdb/trending');
            const rowTrend = document.getElementById('row-trending');
            trending.forEach(i => rowTrend.appendChild(createCard(i)));

            const onAir = await fetchAPI('/api/tmdb/on_the_air');
            const rowAir = document.getElementById('row-on-air');
            onAir.forEach(i => rowAir.appendChild(createCard(i)));
        }

        // --- Interaction Logic ---
        let currentItem = null;
        let isTrailerMode = false;
        let tvSeasonsData = [];

        function handleItemSelect(item, isTrailer = false) {
            currentItem = item;
            isTrailerMode = isTrailer;
            const isTv = item.media_type === 'tv';
            const title = isTv ? item.name : item.title;

            if(isTrailer) {
                // Play Trailer
                fetch(`/api/youtube/trailer?query=${encodeURIComponent(title + " trailer")}`)
                    .then(r => r.json())
                    .then(data => {
                        if(data.success && data.video) {
                            let url = data.video.url;
                            if(url.includes('youtube.com')) url += '&vq=hd1080&autoplay=1';
                            document.getElementById('enter-room-btn').style.display = 'block';
                            openPlayer(url);
                        } else {
                            alert("Tráiler no encontrado.");
                        }
                    });
                return;
            }

            if(isTv) {
                document.getElementById('modal-title').innerText = title;
                openTvModal(item.id);
            } else {
                const url = `https://unlimplay.com/f/embed/movie/${item.id}?autoplay=1`;
                openPlayer(url);
            }
        }

        function openTvModal(tmdbId) {
            const sSelect = document.getElementById('tv-season');
            const eSelect = document.getElementById('tv-episode');
            sSelect.innerHTML = '<option>Cargando...</option>';
            eSelect.innerHTML = '<option>Cargando...</option>';
            sSelect.disabled = true;
            eSelect.disabled = true;
            document.getElementById('tv-modal').style.display = 'flex';

            fetch(`/api/tmdb/tv/${tmdbId}`)
                .then(r => r.json())
                .then(data => {
                    if(data.success && data.details && data.details.seasons) {
                        tvSeasonsData = data.details.seasons.filter(s => s.season_number > 0);
                        populateSeasons();
                    } else {
                        alert("Error cargando serie.");
                        closeTvModal();
                    }
                });
        }

        function populateSeasons() {
            const sSelect = document.getElementById('tv-season');
            sSelect.innerHTML = '';
            sSelect.disabled = false;
            if (tvSeasonsData.length === 0) {
                sSelect.innerHTML = '<option value="1">Temporada 1</option>';
                populateEpisodes(1);
                return;
            }
            tvSeasonsData.forEach(season => {
                const opt = document.createElement('option');
                opt.value = season.season_number;
                opt.innerText = `Temporada ${season.season_number}`;
                sSelect.appendChild(opt);
            });
            sSelect.onchange = (e) => populateEpisodes(parseInt(e.target.value));
            populateEpisodes(tvSeasonsData[0].season_number);
        }

        function populateEpisodes(seasonNumber) {
            const eSelect = document.getElementById('tv-episode');
            eSelect.innerHTML = '';
            eSelect.disabled = false;
            const season = tvSeasonsData.find(s => s.season_number === seasonNumber);
            const count = season ? season.episode_count : 1;
            for(let i=1; i<=count; i++) {
                const opt = document.createElement('option');
                opt.value = i;
                opt.innerText = `Episodio ${i}`;
                eSelect.appendChild(opt);
            }
        }

        function closeTvModal() {
            document.getElementById('tv-modal').style.display = 'none';
        }

        function playTvShow() {
            const s = document.getElementById('tv-season').value;
            const e = document.getElementById('tv-episode').value;
            const url = `https://unlimplay.com/f/embed/tv/${currentItem.id}/${s}/${e}?autoplay=1`;
            closeTvModal();
            openPlayer(url);
        }

        function openPlayer(url) {
            document.getElementById('video-iframe').src = url;
            document.getElementById('player-container').style.display = 'block';
            document.body.style.overflow = 'hidden';
        }

        function closePlayer() {
            document.getElementById('video-iframe').src = '';
            document.getElementById('player-container').style.display = 'none';
            document.getElementById('enter-room-btn').style.display = 'none';
            document.body.style.overflow = 'auto';
        }

        function enterRoom() {
            // From trailer to actual movie
            closePlayer();
            handleItemSelect(currentItem, false);
        }

        // --- SEARCH & FILTERS ---
        let searchTimeout = null;

        function openSearch() {
            document.getElementById('search-panel').classList.add('active');
            document.body.style.overflow = 'hidden';
            document.getElementById('search-input').focus();
        }

        function closeSearch() {
            document.getElementById('search-panel').classList.remove('active');
            document.body.style.overflow = 'auto';
        }

        function openSearchWithFilter(type, param, value) {
            openSearch();
            document.getElementById('filter-type').value = type;
            if(param === 'primary_release_year') {
                document.getElementById('filter-year').value = value;
            }
            triggerSearch();
        }

        document.getElementById('search-input').addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                triggerSearch(e.target.value.trim());
            }, 500);
        });

        async function triggerSearch(query = null) {
            const inputVal = query !== null ? query : document.getElementById('search-input').value.trim();
            const type = document.getElementById('filter-type').value;
            const genre = document.getElementById('filter-genre').value;
            const year = document.getElementById('filter-year').value;
            const sort = document.getElementById('filter-sort').value;
            
            const grid = document.getElementById('search-results');
            grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:50px;">Buscando...</div>';

            let results = [];
            
            if(inputVal.length >= 2) {
                // Text Search
                results = await fetchAPI(`/api/tmdb/search?query=${encodeURIComponent(inputVal)}`);
                if(type !== 'multi') {
                    results = results.filter(r => r.media_type === type);
                }
            } else {
                // Filter Search (Discover)
                if(type === 'multi') {
                    // Discover doesn't support multi, fallback to trending or movie
                    const t = "movie";
                    results = await fetchAPI(`/api/tmdb/discover?type=${t}&genre=${genre}&year=${year}&sort_by=${sort}`);
                } else {
                    results = await fetchAPI(`/api/tmdb/discover?type=${type}&genre=${genre}&year=${year}&sort_by=${sort}`);
                }
            }

            grid.innerHTML = '';
            if(results.length === 0) {
                grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:50px;color:#94a3b8">No se encontraron resultados.</div>';
                return;
            }
            
            results.forEach(r => {
                if(!r.media_type) r.media_type = (type !== 'multi') ? type : 'movie';
                grid.appendChild(createCard(r));
            });
        }
    
        async function showInfoModal(media_type, tmdb_id) {
            document.getElementById('info-modal').style.display = 'flex';
            document.body.style.overflow = 'hidden';
            document.getElementById('info-modal-body').innerHTML = '<h3 style="text-align:center; padding: 50px;">Cargando información...</h3>';
            document.getElementById('info-modal-hero').style.backgroundImage = 'none';

            const data = await fetchAPI(`/api/tmdb/details/${media_type}/${tmdb_id}`);
            if(!data || (!data.id && data.length === 0)) {
                document.getElementById('info-modal-body').innerHTML = '<h3 style="text-align:center; padding: 50px;">Error al cargar los detalles.</h3>';
                return;
            }
            
            const isTv = media_type === 'tv';
            const title = isTv ? data.name : data.title;
            const date = data.release_date || data.first_air_date || '';
            const year = date ? date.split('-')[0] : '';
            const backdrop = data.backdrop_path ? `https://image.tmdb.org/t/p/original${data.backdrop_path}` : '';
            const runtime = data.runtime ? `${data.runtime} min` : (data.episode_run_time && data.episode_run_time.length > 0 ? `${data.episode_run_time[0]} min` : '');
            
            let genres = data.genres ? data.genres.map(g => g.name).join(', ') : '';
            let director = '';
            let cast = '';
            
            if(data.credits) {
                if(data.credits.crew) {
                    const dir = data.credits.crew.find(c => c.job === 'Director' || c.job === 'Producer');
                    if(dir) director = dir.name;
                }
                if(data.credits.cast) {
                    cast = data.credits.cast.slice(0, 10).map(c => c.name).join(', ');
                }
            }
            if(isTv && data.created_by && data.created_by.length > 0) {
                director = data.created_by.map(c => c.name).join(', ');
            }
            
            document.getElementById('info-modal-hero').style.backgroundImage = `url('${backdrop}')`;
            
            let html = `
                <h2 class="info-title">${title}</h2>
                <div class="info-meta">
                    ${year ? `<span>📅 ${year}</span>` : ''}
                    ${runtime ? `<span>⏱ ${runtime}</span>` : ''}
                    <span>⭐ ${data.vote_average ? data.vote_average.toFixed(1) : 'NR'}</span>
                    <span class="badge" style="position:static">${isTv ? 'Serie' : 'Película'}</span>
                    ${data.status ? `<span style="color:var(--primary)">${data.status}</span>` : ''}
                </div>
                <p class="info-overview">${data.overview || 'Sin descripción detallada disponible.'}</p>
                <div class="info-grid">
                    <div class="info-list">
                        <strong>🎭 Elenco Principal</strong>
                        <span>${cast || 'No disponible'}</span>
                    </div>
                    <div class="info-list">
                        <strong>🎬 ${isTv ? 'Creadores' : 'Director / Productor'}</strong>
                        <span>${director || 'No disponible'}</span><br><br>
                        <strong>🏷️ Géneros</strong>
                        <span>${genres || 'No disponible'}</span>
                        ${isTv && data.number_of_seasons ? `<br><br><strong>📺 Temporadas y Episodios</strong><span>${data.number_of_seasons} Temporadas (${data.number_of_episodes} Episodios)</span>` : ''}
                    </div>
                </div>
            `;
            
            document.getElementById('info-modal-body').innerHTML = html;
        }
        
        function closeInfoModal() {
            document.getElementById('info-modal').style.display = 'none';
            document.body.style.overflow = 'auto';
        }
