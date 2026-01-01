const SVG_ICONS = {
    chevronLeft: `<svg class="mplayer-btn-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path fill="currentColor" d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
    </svg>`,
    chevronRight: `<svg class="mplayer-btn-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path fill="currentColor" d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
    </svg>`,
    play: `<svg class="mplayer-btn-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path fill="currentColor" d="M8 5v14l11-7z"/>
    </svg>`,
    pause: `<svg class="mplayer-btn-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path fill="currentColor" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
    </svg>`
};
const API_URL = 'https://apis.netstart.cn/music/playlist/track/all';
let currentTrack = 0;
let playlist = [];
const audio = new Audio();

// 元素获取
const elements = {
    player: document.getElementById('mplayer_player'),
    playlistId: document.getElementById('mplayer_playlistId'),
    loadPlaylist: document.getElementById('mplayer_loadPlaylist'),
    main: document.querySelector('.mplayer-main'),
    cover: document.querySelector('.mplayer-cover'),
    title: document.querySelector('.mplayer-song-title'),
    artist: document.querySelector('.mplayer-artist'),
    progress: document.getElementById('mplayer_progress'),
    playPause: document.getElementById('mplayer_playPause'),
    prev: document.getElementById('mplayer_prev'),
    next: document.getElementById('mplayer_next'),
    loader: document.querySelector('.mplayer-loader'),
    playlistInput: document.querySelector('.mplayer-playlist-input'),
    toggleBtn: document.getElementById('mplayer_toggle-btn'),
    showList: document.getElementById('mplayer_showList'),
    songList: document.querySelector('.mplayer-song-list')
};

// 展开收起功能
elements.toggleBtn.addEventListener('pointerdown', () => {
    elements.player.classList.toggle('mplayer-active');
    elements.toggleBtn.innerHTML = elements.player.classList.contains('mplayer-active') ?
        SVG_ICONS.chevronLeft :
        SVG_ICONS.chevronRight;
});

// 歌曲列表功能
elements.showList?.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    elements.songList.classList.toggle('mplayer-show');
});

document.addEventListener('pointerdown', (e) => {
    if (!elements.songList.contains(e.target) && e.target !== elements.showList) {
        elements.songList.classList.remove('mplayer-show');
    }
});

// 新增滚动监听逻辑
let isScrolling;
window.addEventListener('scroll', () => {
    clearTimeout(isScrolling);

    if (elements.player.classList.contains('mplayer-active')) {
        elements.player.classList.remove('mplayer-active');
        elements.toggleBtn.innerHTML = SVG_ICONS.chevronRight;  // 修改这里
        elements.songList.classList.remove('mplayer-show');
    }

    isScrolling = setTimeout(() => { }, 66);
}, { passive: true });

// 修改歌曲列表点击事件
elements.songList.addEventListener('pointerdown', (e) => {
    const songItem = e.target.closest('.mplayer-song-item');
    if (songItem) {
        currentTrack = parseInt(songItem.dataset.index);
        loadTrack(currentTrack);
        document.querySelectorAll('.mplayer-song-item').forEach(item => {
            item.classList.remove('mplayer-active');
        });
        songItem.classList.add('mplayer-active');
    }
});

// 初始化时读取缓存
const STORAGE_KEY = 'netease_playlist_id';
window.addEventListener('DOMContentLoaded', () => {
    const cachedId = localStorage.getItem(STORAGE_KEY);
    if (cachedId) {
        elements.playlistId.value = cachedId;
        loadPlaylist(cachedId);
    }
});

// 加载歌单
async function loadPlaylist(id) {
    try {
        localStorage.setItem(STORAGE_KEY, id);
        elements.loader.style.display = 'block';
        const response = await fetch(`${API_URL}?id=${id}`);
        const data = await response.json();

        playlist = data.songs.map(track => ({
            title: track.name,
            artist: track.ar.map(artist => artist.name).join('/'),
            cover: track.al.picUrl.replace('http://', 'https://'),
            url: `https://music.163.com/song/media/outer/url?id=${track.id}.mp3`
        }));

        elements.songList.innerHTML = playlist.map((track, index) => `
                    <div class="mplayer-song-item" data-index="${index}">
                        <div class="mplayer-song-info">
                            <div class="mplayer-song-name">${track.title}</div>
                            <div class="mplayer-song-artist">${track.artist}</div>
                        </div>
                    </div>
                `).join('');

        elements.playlistInput.classList.add('mplayer-hidden');
        elements.main.style.display = 'block';
        loadTrack(currentTrack);
    } catch (error) {
        localStorage.removeItem(STORAGE_KEY);
        alert('加载歌单失败');
        throw error;
    } finally {
        elements.loader.style.display = 'none';
    }
}

// 返回输入功能
document.querySelector('.mplayer-return-input').addEventListener('pointerdown', () => {
    localStorage.removeItem(STORAGE_KEY);
    audio.pause();
    playlist = [];
    currentTrack = 0;

    elements.main.style.display = 'none';
    elements.playlistInput.classList.remove('mplayer-hidden');
    elements.playlistId.value = '';
});

// 歌曲点击处理（重复事件已合并）
elements.songList.addEventListener('pointerdown', (e) => {
    const songItem = e.target.closest('.mplayer-song-item');
    if (songItem) {
        currentTrack = parseInt(songItem.dataset.index);
        loadTrack(currentTrack);
        elements.songList.classList.remove('mplayer-show');
    }
});

// 加载歌曲
function loadTrack(index) {
    const track = playlist[index];
    elements.cover.src = track.cover;
    elements.title.textContent = track.title;
    elements.artist.textContent = track.artist;
    audio.src = track.url;
    audio.play();
    elements.player.classList.add('mplayer-playing');
    // elements.playPause.innerHTML = '<i class="fas fa-pause"></i>';
    document.querySelectorAll('.mplayer-song-item').forEach(item => {
        item.classList.remove('mplayer-active');
    });
    document.querySelector(`.mplayer-song-item[data-index="${index}"]`)?.classList.add('mplayer-active');
}

// 事件监听
elements.loadPlaylist.addEventListener('pointerdown', () => {
    const playlistId = elements.playlistId.value;
    if (playlistId) loadPlaylist(playlistId);
});

elements.playPause.addEventListener('pointerdown', () => {
    audio[audio.paused ? 'play' : 'pause']();
    elements.playPause.innerHTML = audio.paused ?
        SVG_ICONS.play :
        SVG_ICONS.pause;
    elements.player.classList.toggle('mplayer-playing', !audio.paused);
});

elements.prev.addEventListener('pointerdown', () => {
    currentTrack = (currentTrack - 1 + playlist.length) % playlist.length;
    loadTrack(currentTrack);
});

elements.next.addEventListener('pointerdown', () => {
    currentTrack = (currentTrack + 1) % playlist.length;
    loadTrack(currentTrack);
});

audio.addEventListener('timeupdate', () => {
    elements.progress.value = (audio.currentTime / audio.duration) * 100 || 0;
});

elements.progress.addEventListener('input', (e) => {
    audio.currentTime = (e.target.value / 100) * audio.duration;
});

audio.addEventListener('ended', () => elements.next.dispatchEvent(new Event('pointerdown')));