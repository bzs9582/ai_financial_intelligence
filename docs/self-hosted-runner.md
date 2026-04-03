# Self-Hosted Runner 模式

如果你的本地机器已经可以直接运行 `codex exec`，并且你希望 GitHub 定时任务复用这台机器上的本地 Codex 配置，那么推荐使用 self-hosted runner。

## 这个模式的好处

- 可以直接复用本机已配置好的 `codex exec`
- 不一定需要在 GitHub 上额外放模型提供商密钥
- 更适合使用非官方但本机已经接通的模型网关

## 什么时候适合

- 你的电脑或服务器会长期在线
- `python -m factory.cli run-phase deliver` 在本机已经可以成功运行
- 你使用的是自定义模型网关，或者不想把模型密钥再放进 GitHub

## 什么时候不适合

- 你的机器经常关机
- 你希望完全不依赖本地设备
- 你希望 GitHub 云端机器独立运行

## 工作流文件

- `.github/workflows/delivery-loop-self-hosted.yml`
- `.github/workflows/optimize-loop-self-hosted.yml`

这两个工作流会直接在 self-hosted runner 上执行：

- `python -m factory.cli run-phase deliver --skip-verify`
- `python -m factory.cli run-phase optimize --skip-verify`
- 失败时再跑 `autofix`

## 是否需要 GitHub 里的模型密钥

通常不需要，前提是：

- self-hosted runner 运行在你已经配置好 Codex 的那台机器上
- 运行 runner 的用户能访问这台机器上的 Codex 配置和认证状态

## 你仍然需要的

- GitHub 仓库访问权限
- `GITHUB_TOKEN` 默认由 Actions 提供，用于建 PR

## 你不需要的

- `CODEX_API_KEY`
- `CODEX_RESPONSES_API_ENDPOINT`

前提是你只使用 self-hosted 工作流，不跑 cloud-hosted 的 `openai/codex-action` 版本。

## 如何启用

1. 在 GitHub 仓库里添加 self-hosted runner
2. 确保 runner 运行在你当前这台已配置好 Codex 的机器上
3. 只启用：
   - `Delivery Loop (Self Hosted)`
   - `Optimize Loop (Self Hosted)`
4. 暂时不要启用 cloud-hosted 的 `Delivery Loop` 和 `Optimize Loop`

## 最重要的判断规则

- 机器一直开着，并且 runner 跑在这台机器上：通常不需要 GitHub 模型密钥
- 机器会关机，但你还要持续跑：需要换成云端运行，并提供 GitHub secret
