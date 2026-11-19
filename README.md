# 📚 BuaaGetPPt

> 🎓 智学北航课堂回放 PPT 一键提取 —— 自动下载全部幻灯片，合成一个 PDF，按课程自动归档

## 📥 安装版（推荐）

到 GitHub [**Releases**](https://github.com/Chemauto/Buaa-GetPPT-From-ibeihang/releases) 下载 `BuaaGetPPt-Setup-x.x.x.exe`，双击进入安装向导：

- 🧙 可自选安装位置（默认装到个人程序目录，**无需管理员权限**）
- 📌 自动创建开始菜单快捷方式，可选创建桌面图标；可在系统里直接卸载
- 🚀 安装完成后从开始菜单（或桌面图标）启动，自动打开操作页面
- 💻 需已安装 Chrome 或 Edge；两者都没有时软件会**自动下载 Chromium 内核**（约 150MB，仅首次）

### 🎒 便携版

不想安装的话，下载 `BuaaGetPPt-portable-x.x.x.exe` 单文件直接双击使用；PDF 输出与登录状态保存在 exe 旁边。

> ⚠️ 两种版本都未做代码签名，首次运行如遇 Windows SmartScreen 提示，点「更多信息 → 仍要运行」即可。

## ✨ 功能特性

- 🖥️ **网页操作界面**：粘贴回放链接，实时显示进度和日志，完成后一键打开 PDF
- 🔍 **高清增强**：自动裁掉教室画面黑边与工具栏，让 PPT 内容铺满页面，并 2× 放大锐化（可关闭）
- 🗣️ **语音转写**：自动提取回放页「语音识别」面板的全部转写文字（含时间点），保存为 `transcript.md`
- 📄 **自动合成 PDF**：幻灯片原图无损嵌入，最终输出只保留一个 PDF 文件
- 🗂️ **按课程自动归档**：输出目录为 `课程名/周次节次/`，重复提取自动加序号、绝不覆盖
- 🔐 **登录一次长期有效**：首次运行弹出浏览器登录北航账号（支持扫码），之后全自动
- 🧩 **双通道提取**：优先走回放页 PPT 列表接口（完整不漏页），接口异常自动回退页面扫描

## 📦 一键安装

```bash
bash install.sh
```

脚本会自动创建虚拟环境并安装全部依赖（需要 Python 3.10+ 和本机的 Chrome 或 Edge）。

## 🚀 使用

### 🖥️ 网页界面（推荐）

```bash
.venv/Scripts/python webui.py      # Windows
.venv/bin/python webui.py          # macOS / Linux
```

运行后自动打开浏览器页面（http://127.0.0.1:8765）：

1. 📋 粘贴回放页链接（地址栏整段复制）
2. ▶️ 点击「开始提取」，实时查看进度
3. ✅ 完成后直接「查看 PDF」或「打开文件夹」

> 💡 需要登录时会自动弹出浏览器窗口，完成一次登录后长期有效；扫码登录通常最快。

### ⌨️ 命令行

```bash
.venv/Scripts/python main.py "https://classroom.msa.buaa.edu.cn/livingroom?course_id=xxxx&sub_id=xxxx&tenant_code=21"
```

| 参数 | 说明 |
| --- | --- |
| `--out 目录` | 指定输出根目录（默认 `output/`） |
| `--no-hd` | 关闭高清增强（默认开启：裁掉黑边并 2× 放大锐化，关闭后文件更小） |
| `--keep-duplicates` | 不合并重复的幻灯片（老师重复讲解同一页时保留多页） |
| `--headless` | 无头模式运行浏览器（首次登录时不要使用） |
| `--login-timeout 秒` | 等待登录的最长时间，默认 600 |

## 📁 输出结构

按「课程名 / 周次节次」自动组织（取自回放页标题），PDF 合成后逐页图片自动清理，最终只保留 PDF：

```
output/
└── 📘 科学写作与报告/
    └── 第3周星期2第3,4节/
        ├── 科学写作与报告第3周星期2第3,4节.pdf
        └── transcript.md                # 语音识别转写原文（含时间点）
```

## 🗣️ 语音转写整理成笔记（ZCode skill）

转写原文是口语化的识别结果（有错别字、无标点），直接阅读体验一般。配合 ZCode 的
**lecture-summary** 技能可以整理成顺畅的讲义笔记：

1. 提取完成后，输出目录里会有 `transcript.md`；
2. 在 ZCode 对话里说：`/lecture-summary 整理 output/科学写作与报告/第3周星期2第3,4节 的课堂转写`；
3. 生成 `讲稿整理.md`：按主题分段重排的顺畅讲稿（保留回放时间点）+ 核心要点 + 关键术语表。

> 💡 整理由 ZCode 内置的大模型完成，无需任何 API key；工具本身只负责抓取原始转写。
> 该技能已安装在本机 `~/.zcode/skills/lecture-summary/`，也可把该文件夹复制给其他
> ZCode 用户使用。

## 🛡️ 隐私说明

- 所有提取均在本地完成，仅使用你自己的登录账号访问你已选修课程的内容；
- 登录状态只保存在本地 `.browser_profile/` 目录（已在 `.gitignore` 中排除），不会随代码上传；
- 仓库中不含任何个人信息，请勿手动把 `.browser_profile/`、`output/` 加入版本控制。

## ❓ 常见问题

**首次运行提示登录后没有反应？** 登录完成、页面跳回回放页后工具会自动继续，耐心等待即可；扫码登录通常最快。

**图片清晰度？** 平台提供的幻灯片原图为 1280×720，这是可获取的最高源分辨率。默认开启的高清增强会自动裁掉黑边与工具栏（内容铺满整页）并做 2× 放大锐化，翻页和缩放阅读明显更清晰，但无法凭空增加源画面里不存在的细节；对文件大小敏感时可用 `--no-hd` 或取消页面里的勾选。

**提取页数和回放页侧边栏对不上？** 属正常现象：侧边栏缩略图按需懒加载，工具通过接口一次性获取全部页面，通常比侧边栏看到的更完整。

**某次提取报错或页数为 0？** 检查回放链接是否完整（地址栏整段复制），确认该课程回放对你可见；命令行模式下失败时输出目录里会留有 `debug_no_thumbs.png` 调试截图，便于排查。

## 🔨 自行打包（可选）

```bash
# 1) 构建程序本体（dist/BuaaGetPPt.exe）
pip install pyinstaller
pyinstaller --onefile --name BuaaGetPPt --collect-all playwright \
  --add-data "buaa_ppt/webapp.html;buaa_ppt" webui.py

# 2) 编译安装包（需安装 Inno Setup，https://jrsoftware.org/isdl.php）
ISCC.exe installer/BuaaGetPPt.iss
```

产物在 `dist/`：`BuaaGetPPt-Setup-x.x.x.exe`（安装包）与 `BuaaGetPPt.exe`（便携版单文件，首次启动需解压几秒）。
