const API_URL = 'https://apis.netstart.cn/music/playlist/track/all';
let currentTrack = 0;
let playlist = [];
const audio = new Audio();

// 元素获取
const elements = {
    player: document.getElementById('player'),
    playlistId: document.getElementById('playlistId'),
    loadPlaylist: document.getElementById('loadPlaylist'),
    main: document.querySelector('.main'),
    cover: document.querySelector('.cover'),
    title: document.querySelector('.song-title'),
    artist: document.querySelector('.artist'),
    progress: document.getElementById('progress'),
    playPause: document.getElementById('playPause'),
    prev: document.getElementById('prev'),
    next: document.getElementById('next'),
    loader: document.querySelector('.loader'),
    playlistInput: document.querySelector('.playlist-input'),
    toggleBtn: document.getElementById('toggle-btn'),
    showList: document.getElementById('showList'),
    songList: document.querySelector('.song-list')
};

// 展开收起功能
elements.toggleBtn.addEventListener('pointerdown', () => {
    elements.player.classList.toggle('active');
    elements.toggleBtn.innerHTML = elements.player.classList.contains('active') ?
        '<i class="fas fa-chevron-left"></i>' :
        '<i class="fas fa-chevron-right"></i>';
});

// 歌曲列表功能
elements.showList?.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    elements.songList.classList.toggle('show');
});

document.addEventListener('pointerdown', (e) => {
    if (!elements.songList.contains(e.target) && e.target !== elements.showList) {
        elements.songList.classList.remove('show');
    }
});

// 新增滚动监听逻辑
let isScrolling;
window.addEventListener('scroll', () => {
    // 清除之前的定时器
    clearTimeout(isScrolling);

    // 检测播放器展开状态
    if (elements.player.classList.contains('active')) {
        // 收起播放器
        elements.player.classList.remove('active');
        elements.toggleBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';

        // 同时关闭歌曲列表
        elements.songList.classList.remove('show');
    }

    // 设置新的定时器
    isScrolling = setTimeout(() => {
        // 滚动结束后的操作（可选）
    }, 66);
}, { passive: true });

// 修改歌曲列表点击事件
elements.songList.addEventListener('pointerdown', (e) => {
    const songItem = e.target.closest('.song-item');
    if (songItem) {
        currentTrack = parseInt(songItem.dataset.index);
        loadTrack(currentTrack);
        // 更新列表激活状态
        document.querySelectorAll('.song-item').forEach(item => {
            item.classList.remove('active');
        });
        songItem.classList.add('active');
    }
});

// 新增缓存相关功能
const STORAGE_KEY = 'netease_playlist_id';

// 初始化时读取缓存
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
        // 存储到本地
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

        // 生成歌曲列表
        elements.songList.innerHTML = playlist.map((track, index) => `
                    <div class="song-item" data-index="${index}">
                        <div class="song-info">
                            <div class="song-name">${track.title}</div>
                            <div class="song-artist">${track.artist}</div>
                        </div>
                    </div>
                `).join('');

        elements.playlistInput.classList.add('hidden');
        elements.main.style.display = 'block';
        loadTrack(currentTrack);
    } catch (error) {
        // 加载失败时清除缓存
        localStorage.removeItem(STORAGE_KEY);
        alert('加载歌单失败');throw error;
    } finally {
        elements.loader.style.display = 'none';
    }
}

// 新增返回输入功能
document.querySelector('.return-input').addEventListener('pointerdown', () => {
    // 清除缓存和状态
    localStorage.removeItem(STORAGE_KEY);
    audio.pause();
    playlist = [];
    currentTrack = 0;

    // 切换界面显示
    elements.main.style.display = 'none';
    elements.playlistInput.classList.remove('hidden');
    elements.playlistId.value = '';
});

// 歌曲点击处理
elements.songList.addEventListener('pointerdown', (e) => {
    const songItem = e.target.closest('.song-item');
    if (songItem) {
        currentTrack = parseInt(songItem.dataset.index);
        loadTrack(currentTrack);
        elements.songList.classList.remove('show');
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
    elements.player.classList.add('playing');
    elements.playPause.innerHTML = '<i class="fas fa-pause"></i>';
    // 更新列表激活状态
    document.querySelectorAll('.song-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`.song-item[data-index="${index}"]`)?.classList.add('active');
}

// 事件监听
elements.loadPlaylist.addEventListener('pointerdown', () => {
    const playlistId = elements.playlistId.value;
    if (playlistId) loadPlaylist(playlistId);
});

elements.playPause.addEventListener('pointerdown', () => {
    audio[audio.paused ? 'play' : 'pause']();
    elements.playPause.innerHTML = audio.paused ?
        '<i class="fas fa-play"></i>' :
        '<i class="fas fa-pause"></i>';
    elements.player.classList.toggle('playing', !audio.paused);
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

audio.addEventListener('ended', () => elements.next.pointerdown());