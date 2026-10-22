# 新增生成素材的请求记录

两条成功任务都使用 `MiniMax-H3`，通过中国区接口 `https://api.minimaxi.com/v2/video_generation` 提交，然后查询 `GET /v2/query/video_generation/{task_id}`，成功后下载返回的视频。

本页与 JSON 是脱敏后的请求模板：认证信息与图片 Base64 不存入仓库；两张参考图保留在 [references](../assets/references/README.md)。渲染脚本直接使用已经生成的视频，不需要再次提交任务。

| 任务 | 输入 | 请求规格 | 实际用途 |
|---|---|---|---|
| 使用近景 | [完整提示词](bridge_prompt.txt) + 两张独立参考图 | 4 秒 / 768P / 16:9 | 取其中 2 秒放入成片 |
| 配乐载体 | [完整提示词](score_prompt.txt)，纯文字 | 15 秒 / 768P / 16:9 | 提取和重组音轨，画面不进广告 |

参数结构见 [h3_request_templates.json](h3_request_templates.json)。任务 ID、成功状态和服务返回的用量见 [generation.json](../manifests/generation.json)。

这些模板不会自行发起调用；重新生成会产生新的任务和可能的费用，结果也可能不同。
