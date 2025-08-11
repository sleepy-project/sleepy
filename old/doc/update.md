# 更新

- [更新](#更新)
  - [手动部署](#手动部署)
  - [Huggingface 部署](#huggingface-部署)
  - [Vercel 部署](#vercel-部署)

## 手动部署

只需运行这两行命令:

```bash
git pull # 拉取最新代码
pip install -r requirements.txt # 安装依赖 (如果有新的, 也可用 uv sync 同步)
```

更新完成，重新启动即可.

## Huggingface 部署

1. `Settings` ==> `Variables and secrets` ==> **更改对应的新增配置项**
2. `Settings` ==> `Factory rebuild` ==> **完全重新部署**

![huggingface-1](https://ghimg.siiway.top/sleepy/update/huggingface-1.1.png)

## Vercel 部署

只需打开你 Fork 的仓库，点击右上角 `Sync fork` -> `Update branch` 同步上游仓库即可

![vercel-1](https://ghimg.siiway.top/sleepy/update/vercel-1.1.png)

> *图中使用我的另一个 Fork 仓库做演示，步骤相同*
> Vercel 检测到仓库更新后会自动重新部署
