# MZZB Score - 动画评分相关数据提取工具

## 项目介绍

MZZB Score 是一个面向新番评分统计的自动化聚合工具，能够并发从四大动画评分平台（**Bangumi**、**AniList**、**MyAnimeList**、**Filmarks**）获取动画作品的评分、评分人数、开播年月及条目链接，可选采集官方 X（Twitter）账号及粉丝数，并按统一口径自动写入 Excel 统计模板中。

## 安装与运行

### 方法一：从源码运行

1. 克隆或下载本仓库
2. 安装依赖项（建议 Python 3.9+）：
   ```bash
   pip install -r requirements.txt
   ```
3. 填写好同目录下的 `mzzb.xlsx` 表格文件（也可将 `X月新番首月评分.xlsx` 或 `X月新番完结评分.xlsx` 复制重命名为 `mzzb.xlsx` 使用）
4. 运行主程序：
   ```bash
   python main.py
   ```

### 方法二：使用打包的可执行文件

1. 前往 Releases 页面下载最新的 `mzzb_score.exe` 与配套 Excel 模板
2. 将 `mzzb_score.exe` 与填写好的 `mzzb.xlsx` 放在同一目录下
3. 双击运行 `mzzb_score.exe`

### 运行单元测试

```bash
python -m pytest unit_test -v
```

## 使用方法

1. 准备 Excel 文件（默认读取同目录下的 `mzzb.xlsx`）：
   - **第 1 行表头（`A1` 单元格）**：填写目标年份或完整新番表头（如 `"2026年10月新番首月评分"`，**务必修改为实际统计年份**；包含月份时还会自动用于同季度候选择优加权）
   - **模板版本校验**：程序自动兼容仓库三套官方模板的版本号位置（`mzzb.xlsx` [`M1`]、`X月新番首月评分.xlsx` [`L1`]、`X月新番完结评分.xlsx` [`R1`]）
   - **第 2 行列名与数据填写**（从第 3 行开始填数据）：
     - `原名`（必填）：填入待查询动画的日文原名
     - `译名`（可选）：**仅在该单元格为空时**，程序会自动填入 Bangumi 中文译名；若用户已填写内容，绝不覆盖
     - 平台链接列（可选）：预填 `Bangumi_url`、`Anilist_url`、`Myanilist_url`、`Filmarks_url`（支持超链接或纯文本 URL），有链接的平台将直接按 ID/URL 精准提取，无链接的平台自动走搜索与跨站协同匹配
2. 运行程序后会自动完成代理检测、四站并发抓取、跨站补位、评分转换与 Excel 写回。

## 运行流程

1. **程序启动与编码初始化**：初始化幂等日志系统（输出至控制台与 `mzzb_score.log`），检查版本更新。
2. **网络代理检测与配置**：
   - 自动检测 Windows 系统代理并通过访问 X/Twitter 验证连通性
   - 降级策略：代理可用 → 全局走代理；代理不可用但直连可用 → 全局走直连；均不可达 → 自动跳过 Twitter 粉丝数采集，继续执行四站评分抓取
3. **API 与可选功能配置**：
   - **MyAnimeList API**：默认使用内置 Client ID（可通过环境变量 `MAL_CLIENT_ID` 或 `MAL_ACCESS_TOKEN` 覆盖）
   - **Twitter 粉丝配置**：当 Twitter 网络可达时提供交互式配置（支持多账号轮换，也可直接跳过）
4. **模板加载与校验**：校验 Excel 模板版本 `FORMAT_VERSION`，从 `A1` 提取目标年份（允许目标年及前一年跨年番）与可选目标季度。
5. **逐行并发提取与协同兜底**：
   - **链接检查**：识别当前行各平台已填写的超链接或纯文本 URL
   - **四站并发提取**：通过 `ThreadPoolExecutor` 同时抓取 Bangumi、AniList、MyAnimeList、Filmarks
   - **四站跨平台协同兜底**：
     - 若 AniList 已带回官方关联 `idMal` 且 MAL 未命中，直接通过 `idMal` 请求 MAL 详情并经无冲突校验后精准落库
     - 对任一仍未命中的平台，自动汇总其他已命中平台返回的日文原名、罗马音标题、英文标题及异体字形（去重后）重新搜索补位
   - **Twitter 粉丝采集**：从 AniList 外部链接提取官方 X/Twitter 账号，在已启用配置时获取粉丝数
   - **标准化写回与日期校验**：转换各站分制、处理低样本 `NaN`、写入带标题超链接，并在 `Notes` 列记录缺站/缺月或跨站开播月份差异
6. **退出清理**：保存 Excel 工作簿，输出日期差异汇总，安全释放 `Scweet` 数据库与所有工作线程的 HTTP 连接池。

## 核心特性与技术细节

### 1. 高召回多候选排序与窄黑名单引擎（`src/data_process/matcher.py`）
- **多候选综合打分择优**：取代“撞见第一个年份合规候选即停止”的旧逻辑，综合结构化标题相似度、目标年份/同季度/精确首播日时间梯度、`idMal` 交叉命中及搜索原始顺位择优。
- **复杂番名归一化与变体回退**：
  - 自动清洗会触发 Bangumi 布尔排除（NOT）语法的前导/成对连字符（如 `戦車椅子-TANK CHAIR-`、`-Second Season-`），同时保留 `U-17`、`2.5` 等词内符号
  - 初搜零结果时自动尝试剥离冗余 `（第1クール）`、转换中日异体字（`冰`→`氷`）与罗马数字字形（`II`↔`Ⅱ`）等搜索变体
  - 支持双语词序对调匹配（如 `スティール・ボール・ラン ジョジョの奇妙な冒険` vs `ジョジョの奇妙な冒険 スティール・ボール・ラン`）及多分部集合重叠识别（如 `2nd STAGE&3rd STAGE`）
- **窄黑名单防错绑（不掉召回）**：仅对 100% 明确的错误（明确季数冲突如 `3rd Season` vs `2nd Season`、明确クール冲突、搜正片撞上 `ミニアニメ`/`ぷちアニメ`/`総集編`/`PV`、搜续作撞上前一年无标号第一季、Bangumi 非动画条目 `type != 2`）执行硬排除；保留纯罗马音条目与同年改副标题续作的参选资格。

### 2. 四站数据提取策略
- **Bangumi**：调用 `/v0/search/subjects`（限定动画 `type=2`），优先直接消费搜索响应已带的日期与评分直方图以省去冗余详情请求，仅在顶层缺日期时补拉详情读取 `infobox`；使用 `Decimal(ROUND_HALF_UP)` 从 1~10 分直方图精确计算加权均分（2 位小数）。
- **AniList**：使用单次合并 GraphQL 查询同时获取候选列表、完整评分分布、`idMal`、`romaji` 及官方 Twitter 链接，请求量减半。
- **MyAnimeList**：网页搜索采用正则提取 `/anime/{id}` 候选 ID（免疫表格 DOM 改版），详情优先走官方 API `/v2/anime/{id}`；仅在未配置或鉴权/解析异常时回退 HTML 解析，对确定性 404/429/超时不盲抓网页。
- **Filmarks**：优先使用移动端 API `/v2/anime/seasons`（支持 `YYYY-Qn` 季度格式解析），API 不可用或零结果时回退至网页多候选 `js-cassette` 列表择优，写入真实 `/animes/{series}/{season}` 链接。

### 3. 评分写入口径与日期一致性校验
- **评分转换与格式**（保持模板原生公式完全兼容）：
  - **Bangumi / MyAnimeList**：10 分制，保留 2 位小数（`0.00`）
  - **AniList**：100 分制除以 10 转为 10 分制，保留 1 位小数（`0.0`）
  - **Filmarks**：5 分制乘 2 转为 10 分制，保留 1 位小数（`0.0`；若模板含 `Filmarks原始评分` 列则同步写入原始 5 分制分数）
  - **最低样本门槛**：任一平台评分人数 `< 50` 时，该平台的评分与评分人数统一写入 `"NaN"`
- **日期校验（`Notes` 列）**：精准区分平台 `没有找到条目` 与已命中但平台 `暂无开播月份`，并对跨站开播月份不一致的条目列出各站 `YYYYMM` 供人工复核。

### 4. 网络连接池与自适应限流（`utils/network/`）
- **连接复用与 UA 池**：基于 `threading.local()` 复用每个工作线程的 `requests.Session` Keep-Alive 连接池，内置 10 组主流桌面浏览器 UA 按站点与条目稳定选取。
- **站点级平滑节流**：内置 `SiteRateLimiter`，自动观测 AniList `X-RateLimit-Limit` / `X-RateLimit-Remaining` 动态调慢速率，遇到 HTTP 429 自动解析 `Retry-After`（秒数或 HTTP-date）同步全局冷却；对 400/401/403/404 等确定性客户端状态码立即返回不盲目重试。

## 项目结构

```text
mzzbscore/
├── main.py                          # 主程序入口（四站并发提取 + 跨站协同兜底调度）
├── mzzb.xlsx                        # 默认综合数据模板
├── X月新番首月评分.xlsx              # 首月评分发布模板
├── X月新番完结评分.xlsx              # 完结评分发布模板
├── models/
│   └── anime_model.py               # Anime 数据模型
├── src/
│   ├── extractors/                  # 四站与 Twitter 提取器
│   │   ├── base_extractor.py        # 提取器抽象基类与统一错误处理
│   │   ├── bangumi.py               # Bangumi API 提取器
│   │   ├── anilist.py               # AniList GraphQL 提取器
│   │   ├── myanimelist.py           # MyAnimeList 网页召回 + API 详情提取器
│   │   ├── filmarks.py              # Filmarks 移动 API + 网页多候选提取器
│   │   └── twitter.py               # Twitter/X 粉丝数提取器
│   ├── parsers/                     # 页面与协议解析器
│   │   ├── base_parser.py           # 解析器基类
│   │   ├── myanimelist_parser.py    # MAL API/HTML 解析与写入器
│   │   ├── filmarks_parser.py       # Filmarks API/HTML 解析与写入器
│   │   ├── twitter_parser.py        # Twitter 链接解析器
│   │   └── link_parser.py           # 四站 URL 校验与 ID 提取器
│   └── data_process/                # 匹配、转换与表格写回
│       ├── matcher.py               # 高召回多候选结构化排序与窄黑名单引擎
│       ├── excel_handler.py         # Excel 数据/超链接/空译名回填处理
│       ├── score_transformers.py    # 四站评分与人数标准化转换器
│       └── date_validator.py        # 跨站开播月份一致性校验器
├── utils/
│   ├── core/                        # 全局变量、日志、MAL/Twitter 配置管理
│   ├── network/                     # Session 连接池、站点自适应限流、UA 池、代理检测
│   ├── parsers/                     # 搜索词清洗与多变体生成（text_processor.py）
│   ├── excel/                       # Excel 列名定义、动态列映射与模板版本读取
│   ├── validators/                  # 数值/名称有效性校验工具
│   └── date/                        # 四站日期与季度格式解析器
├── unit_test/                       # Pytest 单元测试套件
├── requirements.txt                 # 项目依赖
├── ruff.toml                        # 代码规范配置
└── README.md                        # 项目说明文档
```

## Twitter 粉丝数功能安全建议

- 建议使用专门的小号配置 Twitter 抓取，避免使用个人主账号
- 支持配置多账号自动轮换，降低风控风险
- 账号配置仅保存在本地，不会上传至任何第三方服务器
