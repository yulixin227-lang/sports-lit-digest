# sports-lit-digest

`sports-lit-digest` 是一个每日运动科学一区/高质量期刊文献简报生成器 MVP。它会从 PubMed 检索运动科学、运动医学、运动生理、康复、神经肌肉、睡眠与运动干预相关的新文章，使用 Crossref 和 Semantic Scholar 尽量补全元数据，然后按配置化规则评分，生成中文 Markdown/HTML 简报，并可通过 WxPusher 推送一条微信风格短摘要。

当前版本不爬取全文，不绕过出版商限制。摘要是保守的中文解释型简报：如果摘要没有提供样本量、p 值、效应量等具体数据，输出会明确写“摘要中未提供”或“摘要中未提供具体数值”。

## 安装依赖

建议使用虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

代码对 `requests`、`PyYAML`、`Jinja2`、`python-dotenv` 做了基础降级处理，但正式运行仍建议安装依赖。

## 配置 .env

复制示例文件：

```bash
cp .env.example .env
```

常用配置：

```env
NCBI_EMAIL=your_email@example.com
NCBI_API_KEY=
CROSSREF_MAILTO=your_email@example.com
SEMANTIC_SCHOLAR_API_KEY=
ENABLE_CROSSREF=true
ENABLE_SEMANTIC_SCHOLAR=true
DIGEST_TIMEZONE=Asia/Taipei
PUBMED_RETMAX=100
DIGEST_MIN_SCORE=70
DIGEST_MAX_PAPERS=5
SKIP_EMPTY_PUSH=true

PUBLIC_DIGEST_BASE_URL=
WXPUSHER_SPT_ENABLED=false
WXPUSHER_SPT_URL=
WXPUSHER_ENABLED=false
WXPUSHER_APP_TOKEN=
WXPUSHER_UIDS=
WXPUSHER_TOPIC_IDS=

SERVERCHAN_ENABLED=false
SERVERCHAN_SENDKEY=
```

`NCBI_EMAIL` 建议填写真实邮箱，符合 NCBI E-utilities 的礼貌调用习惯。`SEMANTIC_SCHOLAR_API_KEY` 可选，没有 key 时会尝试使用公开限流接口。

`WXPUSHER_SPT_ENABLED=false` 和 `WXPUSHER_ENABLED=false` 是默认值，避免本地调试时误发微信。只有配置了可用的 SPT 或标准发送参数，并且命令行传入 `--send-wechat` 时，才会真实发送。若 SPT 和标准发送都配置，优先使用 SPT。

## 如何运行

日常推荐检索最近 3 天，这比只查当天更稳。PubMed 的入库、期刊在线发表日期和跨库元数据补全经常会有延迟；3 天窗口能减少“今天查不到、明天才出现”的漏检。

```bash
python -m src.main --days-back 3
```

只测试当天新增时，可以使用：

```bash
python -m src.main --date today
```

dry-run 预览，不更新去重文件：

```bash
python -m src.main --days-back 3 --dry-run
```

dry-run 仍会生成 `outputs/YYYY-MM-DD-digest.md` 和 `outputs/YYYY-MM-DD-digest.html`，方便检查排版和内容；区别是不会把文章写入 `data/seen_papers.json`。

dry-run 预览微信推送内容，不真实发送。默认使用 `smart` 智能模式：

```bash
python -m src.main --days-back 3 --dry-run --send-wechat --wechat-mode smart
```

正式生成并发送微信摘要：

```bash
python -m src.main --days-back 3 --send-wechat --wechat-mode smart
```

如果 `SKIP_EMPTY_PUSH=true`，当最终推荐为 0 篇时，程序仍会生成空简报文件，但不会发送空微信消息，并在命令行提示：

```text
No selected papers; skipped WeChat push.
```

`--dry-run --send-wechat` 仍可预览空简报对应的微信摘要，不会真实发送，也不会更新去重文件。

微信推送支持三种模式：

- `--wechat-mode smart`：默认模式。最终推荐 0 篇时不推送；1 篇时推完整正文；2 篇及以上时推短摘要，避免微信消息过长。
- `--wechat-mode short`：只推今日概览、每篇文章的一句话结论和完整简报链接，适合日常自动推送。
- `--wechat-mode full`：推送完整 Markdown digest 正文；内容过长时会按段落或文章边界自动分段，并在每段末尾标注“继续下一条”或“本期结束”。

旧参数 `--wechat-full` 仍可使用，等价于 `--wechat-mode full`。

测试云端或本地推送通路时，如果文章已经被 `data/seen_papers.json` 记录，可以临时加：

```bash
python -m src.main --days-back 3 --send-wechat --wechat-mode smart --force-send
```

`--force-send` 会在本次运行中忽略 seen 文件参与筛选，并且不会写回 `data/seen_papers.json`；它只适合测试重复推送，不建议用于日常定时任务。

预留 Server酱通道参数如下，但当前版本只实现 WxPusher，Server酱会返回 TODO warning：

```bash
python -m src.main --send-wechat --wechat-provider wxpusher
python -m src.main --send-wechat --wechat-provider serverchan
```

## 微信推送：WxPusher

本项目优先支持 [WxPusher](https://wxpusher.zjiecode.com/) 的极简推送 SPT。官方文档说明 SPT 既支持 GET 形式 `https://wxpusher.zjiecode.com/api/send/message/{SPT}/{内容}`，也支持 POST 到 `https://wxpusher.zjiecode.com/api/send/message/simple-push`，POST 请求可以传入 `content`、`summary`、`contentType` 和 `spt`。本项目使用 POST + Markdown 内容类型，因此 SPT 模式支持自定义 digest 摘要内容。

### 1. 使用极简推送 SPT

在 WxPusher 页面找到“极简推送 SPT”，复制它给出的完整 URL。这个 URL 通常包含你的 `SPT_xxx`，属于敏感信息，泄露后别人可以给你发消息，不要提交到 GitHub。

本地 `.env` 推荐这样配置：

```env
WXPUSHER_SPT_ENABLED=true
WXPUSHER_SPT_URL=https://wxpusher.zjiecode.com/api/send/message/SPT_xxx/Hello%20WxPusher
PUBLIC_DIGEST_BASE_URL=
```

如果页面给的是不同形式的完整链接，也可以直接粘贴；程序会从 URL 中提取 `SPT_xxx`，正式发送时改用官方 POST simple-push 接口发送自定义 Markdown 摘要。

SPT 适合个人测试和自己给自己推送：不需要创建应用、不需要 appToken、不需要 UID。它的缺点是管理能力弱，不适合多人订阅、用户管理、回调或长期产品化分发。

### 2. 标准发送：APP_TOKEN + UID

如果你以后能进入“应用管理”，或者要更稳定地长期使用，可以切换到标准发送模式。打开 [WxPusher 管理后台](https://wxpusher.zjiecode.com/admin/)，创建应用，拿到 `appToken`，再让自己的微信账号关注应用并获取 UID。

```env
WXPUSHER_SPT_ENABLED=false
WXPUSHER_ENABLED=true
WXPUSHER_APP_TOKEN=你的_app_token
WXPUSHER_UIDS=UID_xxx
```

获取 UID 的常见方式：

- 在 WxPusher 管理后台找到应用二维码或关注链接，用微信扫码关注。
- 关注公众号 `wxpusher`，在菜单里点击“我的”或“我的UID”查看自己的 UID。
- 如果未来有后端回调，也可以通过应用关注回调或参数二维码拿到 UID。

拿到 UID 后写入 `.env`：

```env
WXPUSHER_UIDS=UID_xxx
```

多个 UID 用英文逗号分隔：

```env
WXPUSHER_UIDS=UID_xxx,UID_yyy
```

如果你使用主题群发，也可以配置：

```env
WXPUSHER_TOPIC_IDS=123,456
```

不要把 SPT URL、appToken 或 UID 写进代码、README 或公开仓库；本地 `.env` 已被 `.gitignore` 忽略。

### 3. 配置完整简报链接

微信消息默认采用适合手机阅读的纯文本栏目排版，例如【今日概览】、【今日最值得读】、【文章 1】、【一句话结论】、【证据强度提醒】、【我的判断】和【术语小词典】。运行 warning 不会放在正文开头，只会在末尾“运行提示”里简要提醒。

微信消息默认只放短摘要和完整简报位置。

如果 `PUBLIC_DIGEST_BASE_URL` 为空，消息里会显示本地 HTML 路径，例如：

```text
C:\...\sports-lit-digest\outputs\2026-06-20-digest.html
```

注意：手机微信通常打不开你电脑上的 `file:///` 或本地 Windows 路径。因此正式使用时推荐用 GitHub Pages、Cloudflare Pages 或其他静态托管服务发布 `outputs/`，这样微信里才能直接点开完整 HTML 简报。托管后配置：

```env
PUBLIC_DIGEST_BASE_URL=https://your-name.github.io/sports-lit-digest
```

推送里会自动变成：

```text
https://your-name.github.io/sports-lit-digest/YYYY-MM-DD-digest.html
```

### 4. 手动测试微信推送

先 dry-run，不会真实发送：

```bash
python -m src.main --days-back 3 --dry-run --send-wechat
```

命令行会打印将要发送到微信的摘要内容。如果内容正常，再正式发送：

```bash
python -m src.main --days-back 3 --send-wechat --wechat-mode smart
```

如果 SPT 和标准发送都没有配置，程序会跳过推送并输出 warning，不会让 digest 生成失败。推送失败也不会影响 Markdown/HTML 简报生成。

## 修改期刊白名单

编辑 `config/journals.yaml`。每个期刊可配置：

- `name`：标准期刊名
- `aliases`：PubMed/Crossref/Semantic Scholar 可能返回的缩写或别名
- `priority`：期刊权重分，最高 30

示例：

```yaml
{
  "name": "British Journal of Sports Medicine",
  "aliases": ["Br J Sports Med", "BJSM"],
  "priority": 30
}
```

## 修改关键词

编辑 `config/keywords.yaml`。每个关键词可配置：

- `term`：英文关键词
- `zh`：中文显示名
- `aliases`：同义词、缩写、常见变体
- `weight`：关键词匹配权重

例如你想加强外骨骼方向，可以提高 `exoskeleton` 的 `weight`，或增加 `wearable robot` 等别名。

## 修改评分规则

编辑 `config/scoring.yaml`。当前总分 100 分：

- 期刊权重：30 分
- 文章类型：20 分
- 方法质量：20 分
- 关键词匹配：20 分
- 可读价值：10 分

`protocol`、`letter`、`editorial`、`corrigendum`、`commentary` 会被降权。RCT、systematic review、meta-analysis、clinical trial、controlled trial、human study、large sample study 会被优先加分。默认只保留 `score >= 70` 的文章，最多 5 篇。

## 查看输出结果

输出文件位于：

```text
outputs/YYYY-MM-DD-digest.md
outputs/YYYY-MM-DD-digest.html
```

`data/seen_papers.json` 会记录已经正式推送过的 DOI 或 PMID，避免重复推送。即使每天使用 `--days-back 3`，已经入选并在非 dry-run 运行中写入该文件的文章，也会在之后的 3 天窗口内被过滤掉。使用 `--dry-run` 时不会更新该文件，方便反复预览同一批候选文章。

## GitHub Actions 自动运行

workflow 位于 `.github/workflows/daily_digest.yml`。它保留了 `workflow_dispatch`，并配置每天 `Asia/Taipei` 早上 8 点运行。GitHub Actions 的 cron 使用 UTC，因此这里写成 UTC 00:00：

```yaml
schedule:
  - cron: "0 0 * * *"
```

运行时会安装依赖，并默认执行：

```bash
python -m src.main --days-back 3 --send-wechat --wechat-mode smart
```

如果手动触发时选择 dry-run，则执行：

```bash
python -m src.main --days-back 3 --dry-run --send-wechat --wechat-mode smart
```

workflow 会把 `outputs/` 作为 GitHub Pages artifact 上传并部署。部署成功后，完整 HTML 简报可以通过下面的格式访问：

```text
https://<你的GitHub用户名>.github.io/sports-lit-digest/YYYY-MM-DD-digest.html
```

如果你的仓库名不是 `sports-lit-digest`，最后一段路径要换成实际仓库名。`SKIP_EMPTY_PUSH=true` 是默认值：如果当天 3 天窗口内没有新的入选文章，会生成 empty digest，但不会推送空微信消息。去重文件 `data/seen_papers.json` 在 workflow 中通过 GitHub Actions cache 恢复和保存，避免每天查最近 3 天时重复推送同一篇文章。

### 发布到 GitHub Pages

1. 在 GitHub 新建一个 private repository，建议仓库名使用 `sports-lit-digest`。
2. 在本地项目根目录初始化并推送仓库，例如：

```bash
git init
git add .
git commit -m "init sports lit digest"
git branch -M main
git remote add origin https://github.com/<你的GitHub用户名>/sports-lit-digest.git
git push -u origin main
```

`.env` 已在 `.gitignore` 中，不要手动 `git add .env`。如果 GitHub Pages 对 private repository 的可见性有额外限制，请以你账号/组织的 Pages 设置为准；微信里要能打开，最终 Pages URL 必须对手机网络可访问。

3. 打开仓库 `Settings -> Pages`，在 `Build and deployment` 里把 `Source` 选择为 `GitHub Actions`。
4. 打开 `Settings -> Secrets and variables -> Actions -> New repository secret`，添加运行所需 Secrets。

需要在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions` 中配置：

```text
WXPUSHER_SPT_ENABLED
WXPUSHER_SPT_URL
PUBLIC_DIGEST_BASE_URL
```

推荐值：

```text
WXPUSHER_SPT_ENABLED=true
WXPUSHER_SPT_URL=你的完整 WxPusher SPT URL
PUBLIC_DIGEST_BASE_URL=https://<你的GitHub用户名>.github.io/sports-lit-digest
```

可选 Secrets：

```text
WXPUSHER_APP_TOKEN
WXPUSHER_UIDS
WXPUSHER_TOPIC_IDS
SEMANTIC_SCHOLAR_API_KEY
NCBI_EMAIL
NCBI_API_KEY
CROSSREF_MAILTO
```

`SKIP_EMPTY_PUSH` 默认在 workflow 中设为 `true`，通常不需要放进 Secret。

如果用 SPT，配置 `WXPUSHER_SPT_ENABLED=true` 和 `WXPUSHER_SPT_URL` 即可；如果用标准发送，配置 `WXPUSHER_APP_TOKEN` 和 `WXPUSHER_UIDS`。如果两套都配置，程序优先使用 SPT。

5. 手动测试：打开 GitHub 仓库的 `Actions -> Daily Sports Lit Digest -> Run workflow`，保持默认 `days_back=3`，可以先把 `dry_run` 设为 `true` 验证生成和 Pages 部署，再正式运行。
6. 如果要测试云端微信推送通路，并且最近 3 天的文章已经在 `seen_papers.json` 里导致 `Selected: 0`，可以手动运行 workflow 时把 `force_send` 设为 `true`。这会在本次运行中忽略 seen cache，允许重复推送符合条件的文章，但不会保存或破坏正式 seen cache。定时每日运行不会使用 `force_send`，仍然正常去重。
7. 验证部署：workflow 完成后，打开 `Actions` 运行详情，查看 `Deploy to GitHub Pages` 的 URL，或直接访问：

```text
https://<你的GitHub用户名>.github.io/sports-lit-digest/YYYY-MM-DD-digest.html
```

8. 微信推送里的完整简报链接来自 `PUBLIC_DIGEST_BASE_URL + /YYYY-MM-DD-digest.html`。如果 `PUBLIC_DIGEST_BASE_URL` 没有配置，程序会继续显示本地 HTML 路径，并提示“手机微信可能无法打开本地路径”。

## 后续接入分发渠道

当前默认分发通道是 WxPusher。后续可以继续扩展：

- 邮箱：可以保留为备用，但默认关闭；把 HTML 作为邮件正文，用 SMTP 或邮件服务商 API 发送。
- Server酱：`.env.example` 已预留 `SERVERCHAN_SENDKEY` 和 `SERVERCHAN_ENABLED`，当前是 TODO。
- Telegram：新增 bot token，用 `sendMessage` 或 `sendDocument` 推送 Markdown/HTML。
- 飞书：使用飞书机器人 webhook，推送摘要链接或 Markdown 卡片。
- Notion：用 Notion API 把每篇文章写入 database，字段包括 DOI、期刊、评分、关键词、推荐指数。
- 微信公众号正式图文：当前 WxPusher 是微信消息推送，不等同于公众号草稿箱发布。后续如要发正式公众号推文，建议先人工审稿，再考虑公众号草稿箱接口或第三方排版服务。

建议分发前保留人工复核，尤其是标题翻译、研究对象、主要结果和局限性字段。
