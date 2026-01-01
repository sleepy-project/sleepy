# 贡献指南

## 一般步骤

1. 首先要 Fork 本仓库 (否则无法推送更改哦)
2. Clone 你的仓库到本地
3. 进行功能修改 (包括写代码和测试)
4. 提交并推送更改
5. 创建 pr (Pull Request)
6. 等待我们合并即可

> [!TIP]
> 最好先自己测试没有问题了再创建 pull request <br/>
> 也可以创建一个 draft *(草稿)* pull request，等功能写好再转成普通的 pr <br/>
> *开发过程中遇到任何问题可以 [联系我们](https://siiway.top/about/contact)~*

## 一些重要的提示

1. 在 commit / release 时, 更新 `pyproject.toml` 中的版本号:

```toml
# in dev
version = "5.0-dev-20250621"
```

```toml
version = "5.0-release-20251230"
```

2. 在编写需要鉴权的接口时，一定要注意两个修饰器的顺序:

```py
@app.route('/route') # 路由定义在前
@u.require_secret # 鉴权在后
def function():
  # ...
```

即 **需要鉴权的修饰器紧跟函数定义**，如果顺序搞反会导致 `@u.require_secret` 修饰器被忽略，**从而绕过鉴权** *([History](https://github.com/sleepy-project/sleepy/commit/797e3441096a3644a58e1baf9988972b61a47def))*

<details>
<summary>关于这个 commit 是怎么来的</summary>

*sorry but 我们的 AList 挂了, 不想重新上传*

</details>

> [!IMPORTANT]
> **千万不要** 将以下文件 (夹) 包含在提交中:
> - `data/`
> - `config.yaml`
> - `config.toml`
> - `config.json`
> - `.env`
> - `*.db`
> - 总之就是你的配置和数据文件
