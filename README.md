# Get 笔记批量导出到 Obsidian

**GetNote to Obsidian** 把得到大脑（Get 笔记）里的普通笔记和订阅博主的视频逐字稿导出为本地 Markdown。支持指定日期、按博主归档、自定义标题和断点续跑，每条原文都保留来源，并汇总到可点击的索引。

[WorkBuddy / Codex 安装包](https://github.com/yuanyuanleah/getnote-to-obsidian/releases/latest/download/getnote-obsidian.zip) · [豆包工作试装包](https://github.com/yuanyuanleah/getnote-to-obsidian/releases/latest/download/getnote-obsidian-doubao.zip) · [版本记录](CHANGELOG.md)

作者：元元 Leah。Export GetNote notes and subscribed creator transcripts to Obsidian-ready Markdown with date filters, source links, and resumable imports.

## 两句开始

| 你想做什么 | 发给 AI |
|---|---|
| 批量导出一段时间的普通笔记 | 把我 Get 笔记里 2026.10–2026.12 的笔记导入并整理。 |
| 导出已订阅博主的视频逐字稿 | 把我在 Get 笔记里订阅的博主导入到「对标资料」。 |

可以加「只导入知识库『我的对标』里的某个博主」「标题用原题」，或「标题用日期｜主题」。有明确指令时直接执行，脚本会自动分页、按来源 ID 去重、回读结果。单条缺原文会进索引的待补清单，其他条目继续。

## 怎么安装

| 客户端 | 从哪里开始 |
|---|---|
| **WorkBuddy** | 在技能管理页选择本地导入，上传 [标准 ZIP](https://github.com/yuanyuanleah/getnote-to-obsidian/releases/latest/download/getnote-obsidian.zip)。连接 Get 笔记官方连接器或准备官方 CLI。 |
| **Codex** | 下载 [标准 ZIP](https://github.com/yuanyuanleah/getnote-to-obsidian/releases/latest/download/getnote-obsidian.zip)，把解压后的 getnote-obsidian 文件夹添加到 Skills。 |
| **豆包工作** | 在有「上传技能」入口的客户端尝试 [豆包工作 ZIP](https://github.com/yuanyuanleah/getnote-to-obsidian/releases/latest/download/getnote-obsidian-doubao.zip)。先确认 Get 笔记读取能力、Python 和目标目录权限。见下方说明。 |
| **普通豆包聊天** | 上传你愿意交给豆包处理的 Markdown，再让它整理标题、分类和索引。自动读取 Get 笔记并写入本机 Vault 的流程目前没有在普通聊天端验证。 |

完整导入需要 Python 3.10 或以上版本，以及当前会话可读取 Get 笔记的 [官方 CLI](https://github.com/iswalle/getnote-cli#安装) 或 Get 连接器。首次在 Get 的官方浏览器页面完成授权。打开目标 Obsidian 库或工作文件夹后再发指令。长任务保持同一会话，让 AI 跟到索引写完。 [连接器说明](references/connector.md)

## 豆包工作能导入 Get 笔记吗？

豆包工作支持上传 Skill，也能通过连接器接入外部数据。试装包按豆包文档把 SKILL.md 放在 ZIP 根目录。完整导入仍需要当前任务能读取已授权的 Get 笔记、运行 Python，并能写入你的目标目录。建议先用一条普通笔记验收。豆包工作真实账号的导入和写盘目前尚未实测。 [豆包技能接入指南](https://open.doubao.com/document/doubao-developer-guide/skill-integration-guide) · [得到大脑连接器](https://www.biji.com/)

普通豆包聊天可以先上传已经导出的文件，再发：

> 把我上传的 Markdown 整理成一个索引。给每篇补一个「主题｜素材类型｜关键词」的显示标题。保留原题、原文和来源，标明缺失的内容。用 Markdown 表格交付。

## 导出的文件长什么样？

普通笔记按**创建时间**筛选，包含起止月份，按月保存。默认标题是 **主题｜素材类型｜关键词**。原题另存属性，原文保留。订阅博主的内容按**博主**分文件夹，从旧到新导出。逐字稿、转写待核对和 Get 摘要各有一节。省略知识库时，读取当前账号自有知识库里已订阅的博主。

指定目录就是目标目录。省略时，在当前 Obsidian Vault 或工作区创建：

    Get笔记导入/
    ├── 普通笔记/
    │   ├── 2026-10/
    │   └── 00-普通笔记导入索引.md
    └── 订阅博主/
        ├── 博主名称/
        └── 00-订阅博主导入索引.md

同一目标内重跑只补缺项。需要先看范围时，发送「先预览，不写文件」。目标 Vault 自己的批量入库规则优先。

## 给执行任务的 AI

从完整 Skill 文件夹执行。将工作区指向使用者正在处理的目录。

    python3 scripts/import_getnote.py notes --workspace "/你的工作区" --range "2026.10-2026.12"
    python3 scripts/import_getnote.py bloggers --workspace "/你的工作区" --output "对标资料"
    python3 scripts/import_getnote.py notes --workspace "/你的工作区" --range "2026-10-01 至 2026-12-31" --title "{日期}｜{主题}"

使用 --preview 只看候选。可用 --timezone 指定时区，省略时使用本机时区。批量连接器、暂存格式和退出码见 [运行参考](references/connector.md)。

## 测试、来源和许可

两个入口已使用合成数据验证，覆盖官方 CLI 1.3.0 与 1.10.1、日期筛选、分页、保留原文、去重和缺原文续跑。GitHub 安装包也经解包回验。WorkBuddy 和豆包工作的真实账号流程待实测。

普通笔记入口延续元元 Leah 的 getnote-obsidian-intake。博主导入参考 [唐宋的 Get 对标视频整理](https://github.com/akaososm-ui/tangsong-skills/tree/main/skills/tangsong-getnote-benchmark-video-transcriber)。读取服务由用户自己的官方 Get 授权提供。项目采用 [MIT 许可证](LICENSE)。
