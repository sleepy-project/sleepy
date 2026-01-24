const sliderInput = document.getElementById('sliderRange');

// ================= 透明度系统 =================
// 应用保存的透明度
function applySavedOpacity() {
    const savedOpacity = localStorage.getItem('moonlight.cardOpacity');
    if (savedOpacity) {
        document.documentElement.style.setProperty('--card-alpha', savedOpacity);
        if (sliderInput) sliderInput.value = savedOpacity;
    }
}

// ================= 初始化 =================
document.addEventListener('DOMContentLoaded', () => {
    applySavedOpacity();
});

// ================= 滑块交互逻辑 =================
document.addEventListener('DOMContentLoaded', () => {
    const sliderInput = document.getElementById('sliderRange');
    let timeoutId = null, isDragging = false;

    if (sliderInput) {
        // 点击按钮显示 / 隐藏滑块
        document.getElementById('slider').addEventListener('click', (e) => {
            e.stopPropagation(); // 阻止冒泡，防止 `document` 误触发 `click`
            sliderInput.style.display = sliderInput.style.display === 'block' ? 'none' : 'block';

            if (sliderInput.style.display === 'block') {
                startHideTimer();
            }
        });

        // 用户开始拖动滑块
        ['mousedown', 'touchstart'].forEach(eventType => {
            sliderInput.addEventListener(eventType, function (e) {
                e.stopPropagation(); // 防止事件冒泡
                isDragging = true;
                clearTimeout(timeoutId); // 停止隐藏倒计时
            });
        });

        // 用户松手，滑块不会立即隐藏
        ['mouseup', 'touchend'].forEach(eventType => {
            sliderInput.addEventListener(eventType, function (e) {
                e.stopPropagation(); // 防止事件冒泡
                isDragging = false;

                // **松手后，延迟 3 秒再开始隐藏倒计时**
                setTimeout(() => {
                    if (!isDragging) startHideTimer();
                }, 3000);
            });
        });

        // 用户拖动滑块时更新透明度
        sliderInput.addEventListener('input', function (e) {
            e.stopPropagation();
            const alpha = e.target.value;
            document.documentElement.style.setProperty('--card-alpha', alpha);
            localStorage.setItem('moonlight.cardOpacity', alpha);

            if (!isDragging) resetHideTimer();
        });

        // **修正：点击滑块本身时，不隐藏**
        sliderInput.addEventListener('click', (e) => {
            e.stopPropagation(); // 阻止冒泡，防止 `document` 误触发 `click`
        });

        // **点击滑块外部时，5 秒后才隐藏滑块**
        document.addEventListener('click', (e) => {
            if (!sliderInput.contains(e.target)) {
                startHideTimer();
            }
        });
    }

    function startHideTimer() {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => {
            if (!isDragging) {
                sliderInput.style.display = 'none';
            }
        }, 5000);
    }

    function resetHideTimer() {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(startHideTimer, 500);
    }
});
