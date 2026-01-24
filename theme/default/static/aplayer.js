const toggleBtn = document.getElementById('toggle-btn');

const initialLeft = 10;
const initialTop = 10;

let isToggled = false;      // 记录按钮是否已切换
let toggleDisabled = false; // 一旦按钮被拖动，则禁用点击切换效果

let startX, startY, btnStartLeft, btnStartTop;
const dragThreshold = 5; // 拖动的判定阈值

toggleBtn.addEventListener('mousedown', (e) => {
    // 记录起始坐标及按钮当前的位置
    startX = e.clientX;
    startY = e.clientY;
    const rect = toggleBtn.getBoundingClientRect();
    btnStartLeft = rect.left;
    btnStartTop = rect.top;

    // 标记当前操作为未拖动
    let isDragging = false;

    function onMouseMove(e) {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        if (!isDragging && (Math.abs(dx) > dragThreshold || Math.abs(dy) > dragThreshold)) {
            isDragging = true;
            // 一旦拖动，禁用点击切换特效
            toggleDisabled = true;
        }
        if (isDragging) {
            // 根据拖动距离更新按钮位置
            toggleBtn.style.left = (btnStartLeft + dx) + 'px';
            toggleBtn.style.top = (btnStartTop + dy) + 'px';
        }
    }

    function onMouseUp(e) {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        // 如果未发生拖动，判定为点击
        if (!isDragging && !toggleDisabled) {
            // 判断按钮是否处于初始状态
            if (!isToggled) {
                // 向上移动150px
                toggleBtn.style.bottom = (initialTop + 200) + 'px';
                isToggled = true;
            } else {
                // 恢复初始位置
                toggleBtn.style.bottom = initialTop + 'px';
                isToggled = false;
            }
        }
        // 若已拖动，则点击切换功能不再生效
    }

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
});

// 禁用默认拖拽行为
toggleBtn.ondragstart = () => false;