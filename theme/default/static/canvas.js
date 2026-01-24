class ParticleBackground {
    constructor(options = {}) {
        this.config = Object.assign({
            zIndex: -1,
            opacity: 1,
            color: "255,0,0",
            count: 85
        }, options);

        this.particles = [];
        this.mouse = { x: null, y: null, max: 20000 };

        this.initCanvas();
        this.initParticles();
        this.bindEvents();
        this.animate();
    }

    // 创建 canvas
    initCanvas() {
        this.canvas = document.createElement("canvas");
        this.canvas.style.cssText = `position:fixed;top:0;left:0;z-index:${this.config.zIndex};opacity:${this.config.opacity};`;
        document.body.appendChild(this.canvas);
        this.ctx = this.canvas.getContext("2d");

        this.resizeCanvas();
        this.resizeObserver = new ResizeObserver(() => this.resizeCanvas());
        this.resizeObserver.observe(document.body);
    }

    // 调整 canvas 大小
    resizeCanvas() {
        this.width = this.canvas.width = window.innerWidth;
        this.height = this.canvas.height = window.innerHeight;
    }

    // 初始化粒子
    initParticles() {
        for (let i = 0; i < this.config.count; i++) {
            this.particles.push({
                x: Math.random() * this.width,
                y: Math.random() * this.height,
                xa: 2 * Math.random() - 1,
                ya: 2 * Math.random() - 1,
                max: 6000,
                color: this.randomColor()
            });
        }
        this.particles.push(this.mouse); // 添加鼠标粒子
    }

    // 生成随机颜色
    randomColor() {
        return `rgba(${Math.floor(Math.random() * 255)},${Math.floor(Math.random() * 255)},${Math.floor(Math.random() * 255)},1)`;
    }

    // 事件绑定
    bindEvents() {
        this.mouseMoveHandler = e => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;
        };

        this.mouseOutHandler = () => {
            this.mouse.x = null;
            this.mouse.y = null;
        };

        window.addEventListener("mousemove", this.mouseMoveHandler);
        window.addEventListener("mouseout", this.mouseOutHandler);
    }

    // 动画更新
    animate() {
        this.ctx.clearRect(0, 0, this.width, this.height);

        this.particles.forEach((particle, index) => {
            if (particle === this.mouse) return;

            // 更新位置
            particle.x += particle.xa;
            particle.y += particle.ya;

            // 边界反弹
            if (particle.x > this.width || particle.x < 0) particle.xa *= -1;
            if (particle.y > this.height || particle.y < 0) particle.ya *= -1;

            // 绘制粒子
            this.ctx.fillStyle = particle.color;
            this.ctx.fillRect(particle.x - 0.5, particle.y - 0.5, 1, 1);

            // 处理粒子之间的连接
            this.checkConnections(particle, index);
        });

        requestAnimationFrame(() => this.animate());
    }

    // 处理粒子连接
    checkConnections(particle, index) {
        for (let i = index + 1; i < this.particles.length; i++) {
            let other = this.particles[i];
            if (!other.x || !other.y) continue;

            let dx = particle.x - other.x;
            let dy = particle.y - other.y;
            let distanceSquared = dx * dx + dy * dy;

            if (distanceSquared < other.max) {
                this.handleMouseInteraction(particle, other, distanceSquared, dx, dy);

                let opacity = (other.max - distanceSquared) / other.max;
                this.ctx.beginPath();
                this.ctx.lineWidth = opacity / 2;
                this.ctx.strokeStyle = particle.color;
                this.ctx.moveTo(particle.x, particle.y);
                this.ctx.lineTo(other.x, other.y);
                this.ctx.stroke();
            }
        }
    }

    // 鼠标靠近时的粒子交互
    handleMouseInteraction(particle, other, distanceSquared, dx, dy) {
        if (other === this.mouse && distanceSquared >= other.max / 2) {
            particle.x -= 0.05 * dx;
            particle.y -= 0.03 * dy;
        }
    }

    // 销毁 canvas
    destroy() {
        window.removeEventListener("mousemove", this.mouseMoveHandler);
        window.removeEventListener("mouseout", this.mouseOutHandler);
        this.resizeObserver.disconnect();
        this.canvas.remove();
    }
}

// 启动粒子背景
const particleBg = new ParticleBackground({
    zIndex: -1,
    opacity: 0.8,
    color: "0,255,255",
    count: 80
});