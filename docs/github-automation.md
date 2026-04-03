# GitHub 自动运行接入指南

这份文档说明如何把当前项目切换成真正的 GitHub 自动运行模式。

## `CODEX_API_KEY` 是干什么的

在当前工作流里，`CODEX_API_KEY` 是传给 `openai/codex-action` 的认证密钥。

注意：

- 这里的 GitHub secret 名字叫 `CODEX_API_KEY`
- 但工作流内部仍然把它作为 `openai-api-key` 这个 action 输入传递
- 这只是 action 的输入字段名，不代表你一定只能用 OpenAI 官方域名

它的本质作用是：

- 让 GitHub Actions 上运行的 Codex 自动化具备调用模型接口的权限
- 因为 GitHub runner 看不到你本机的 Codex 登录态和本地配置，所以必须单独提供认证

## 如果你用的是 OpenAI 官方接口

只需要配置一个 GitHub Secret：

- 名称：`CODEX_API_KEY`
- 值：你的 OpenAI API key

不需要再配置额外变量。

## 如果你用的不是 OpenAI 官方接口

只要你的服务兼容 OpenAI Responses API，并支持：

- Bearer token 认证
- 标准的 `/v1/responses` 或等价 Responses 端点

那么当前工作流也可以接。

你需要配置两样东西：

### 1. GitHub Secret

进入：

`Settings -> Secrets and variables -> Actions`

点击：

`New repository secret`

填写：

- 名称：`CODEX_API_KEY`
- 值：你的服务使用的 bearer token / API key

### 2. GitHub Variable

进入：

`Settings -> Secrets and variables -> Actions`

切到 `Variables`，点击：

`New repository variable`

填写：

- 名称：`CODEX_RESPONSES_API_ENDPOINT`
- 值：你的完整 Responses API 地址

例如：

```text
https://your-provider.example.com/v1/responses
```

## 当前工作流如何读取它们

工作流里已经写成：

```yaml
openai-api-key: ${{ secrets.CODEX_API_KEY }}
responses-api-endpoint: ${{ vars.CODEX_RESPONSES_API_ENDPOINT }}
```

也就是说：

- `CODEX_API_KEY` 必填
- `CODEX_RESPONSES_API_ENDPOINT` 可选
- 如果你不填 `CODEX_RESPONSES_API_ENDPOINT`，就按 action 默认端点走

## 什么时候这种方式不适用

下面这些情况，`openai/codex-action` 大概率不能直接用：

- 你的提供商不兼容 Responses API
- 你的提供商不是 Bearer token 鉴权
- 你的接口需要额外签名方式
- 你的接口虽然“兼容 OpenAI”，但和 Codex 所需字段不一致

如果是这种情况，建议改成：

1. 自托管 GitHub runner
2. 在 runner 上安装并配置好你自己的 `codex exec`
3. 工作流里不用 `openai/codex-action`，而是直接运行 shell 命令，例如：

```yaml
- name: Run local Codex CLI
  run: python -m factory.cli run-phase deliver
```

这样就能复用你本地那套 CLI 提供商配置。

## 第一步：把仓库推到 GitHub

如果你还没有推送，当前仓库地址是：

`https://github.com/bzs9582/ai_financial_intelligence.git`

本地执行：

```bash
git add .
git commit -m "init codex financial platform factory"
git push -u origin main
```

## 第二步：配置 GitHub Secrets / Variables

至少配置：

- Secret: `CODEX_API_KEY`

如果你用自定义 Responses 端点，再加：

- Variable: `CODEX_RESPONSES_API_ENDPOINT`

## 第三步：打开 Actions

到仓库的 `Actions` 页面，依次运行：

1. `Bootstrap MVP`
2. `Delivery Loop`
3. `Optimize Loop`

建议先手动跑一次 `Bootstrap MVP`，确认能成功创建草稿 PR，再观察定时循环。

## 当前调度

- `Delivery Loop`
  每小时第 7 分钟 UTC 运行一次

- `Optimize Loop`
  每 4 小时第 23 分钟 UTC 运行一次

## 当前工作流实际会做什么

### `Bootstrap MVP`

- 读取 `docs/` 和 `AGENTS.md`
- 调用 Codex 生成第一版 MVP
- 安装依赖
- 跑验证
- 创建草稿 PR

### `Delivery Loop`

- 读取 `docs/tasks.md`
- 实现最靠前的未完成任务
- 安装依赖
- 跑验证
- 失败时自动执行 `autofix`
- 创建或更新草稿 PR

### `Optimize Loop`

- 做缓存、测试、可靠性、性能等范围内优化
- 安装依赖
- 跑验证
- 失败时自动执行 `autofix`
- 创建或更新草稿 PR

## 推荐保护措施

- 开启 `main` 分支保护
- 只允许通过 PR 合并
- 初期只允许工作流创建草稿 PR
- 不要让自动化直接推送主分支
