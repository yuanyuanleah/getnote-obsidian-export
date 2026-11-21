# Get 笔记导入 Obsidian

把 Get 笔记里的普通笔记和订阅博主的视频逐字稿，整理成本地 Markdown。用在 WorkBuddy 或 Codex，打开工作文件夹，说一句就能开始。

作者：元元 Leah · [下载 WorkBuddy 安装包](https://github.com/yuanyuanleah/getnote-obsidian/releases/latest/download/getnote-obsidian.zip) · [版本记录](CHANGELOG.md)

## 新手从这两句开始

| 想做什么 | 复制这句话 |
|---|---|
| 导入一段时间的笔记 | 把我 Get 笔记里 2026.10–2026.12 的笔记导入并整理。 |
| 导入订阅博主 | 把我在 Get 笔记里订阅的博主导入到「对标资料」。 |

也可以加「只导入知识库『我的对标』里的某个博主」「标题用原题」或「标题用 日期｜主题」。

## 安装

1. **添加 Skill。** 在 WorkBuddy 的技能管理页选本地导入，添加 [安装 ZIP](https://github.com/yuanyuanleah/getnote-obsidian/releases/latest/download/getnote-obsidian.zip)。Codex 用户可以在本地解压，把整个 getnote-obsidian 文件夹添加到自己的 Skills。保留 SKILL.md、scripts 和 references 的相对位置。
2. **连接 Get 笔记。** 从当前 AI 会话确认 [官方 getnote CLI](https://github.com/iswalle/getnote-cli#安装) 可用。首次授权在 Get 官方浏览器页面完成。WorkBuddy 已连接官方 Get 连接器时，也可按 [连接器说明](references/connector.md) 读取。落盘脚本需要 Python 3.10 或以上版本。
3. **选工作文件夹。** 打开目标 Obsidian 库或其他本地工作文件夹，发送上面的任意一句。指定的新目录会自动创建。长任务可以继续同一会话，让 AI 跟到索引写完。

## 文件会放在哪里

普通笔记按创建时间筛选，包含起止月份，按月归档。默认标题是 **主题｜素材类型｜关键词**，来源原题放进属性。

订阅博主按博主分文件夹，从旧到新导入视频。默认使用原题。逐字稿、识别待核对提示和 Get 摘要各有位置。省略知识库时，读取账号自有知识库里已经订阅的博主。

省略保存目录时，使用当前 Vault 或工作区的 Get笔记导入 文件夹：

    Get笔记导入/
    ├── 普通笔记/
    │   ├── 2026-10/
    │   └── 00-普通笔记导入索引.md
    └── 订阅博主/
        ├── 博主名称/
        └── 00-订阅博主导入索引.md

同一目标下按来源 ID 去重。单条缺原文时，索引会记录待补项，后面的条目继续处理。同一指令重跑会跳过已完成的内容。目标 Vault 自己的批量导入规则优先。

## 常见问题

- **首次运行提示缺授权。** 在 Get 的官方页面授权后，继续执行原本的导入任务。凭证保存在自己的客户端。
- **输出数量比列表少。** 打开索引查看重复、缺原文或读取失败的记录。想重试时，用相同目录和指令继续。
- **想先看范围。** 说「先预览，不写文件」，确认计划后再说「按这个范围导入」。
- **需要换标题。** 可以指定原题，也能组合日期、原题、主题、类型、关键词、博主或 ID。已有原文文件按来源 ID 保留。

## 给执行任务的 AI

从 Skill 目录执行。将工作区指向使用者正在处理的目录。

    python3 scripts/import_getnote.py notes --workspace "/你的工作区" --range "2026.10-2026.12"
    python3 scripts/import_getnote.py bloggers --workspace "/你的工作区" --output "对标资料"
    python3 scripts/import_getnote.py notes --workspace "/你的工作区" --range "2026-10-01 至 2026-12-31" --title "{日期}｜{主题}"

加 --preview 只看范围与候选。可用 --timezone 指定时区，省略时使用本机时区。连接器和退出码见 [运行参考](references/connector.md)。

## 验证、来源与许可

已用合成数据验证官方 CLI 1.3.0 和 1.10.1 的两个入口、按期筛选、分页、原文保留、去重和缺原文续跑。也用解包后的文件复跑了数据导入测试。WorkBuddy 的真实账号验证仍待实测。

普通笔记工作流延续元元 Leah 的 getnote-obsidian-intake。博主工作流参考 [唐宋的 Get 对标视频整理](https://github.com/akaososm-ui/tangsong-skills/tree/main/skills/tangsong-getnote-benchmark-video-transcriber)。访问 Get 笔记使用用户自己的授权和 [官方 CLI](https://github.com/iswalle/getnote-cli) 或连接器。项目许可为 [MIT](LICENSE)。
