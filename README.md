# MZZB Score - 动画评分相关数据提取工具

## 项目介绍

MZZB Score 是一个动漫评分聚合工具，能够自动从多个知名动漫评分网站（Bangumi、MyAnimeList、AniList、Filmarks）获取动画作品的评分数据，并将这些数据整合到Excel表格中，方便用户进行比较和分析。

## 主要功能

- 从Excel表格中读取动画作品名称列表
- **链接优先提取策略**：自动检测Excel中的平台链接列（`Bangumi_url`、`Anilist_url`、`Myanimelist_url`、`Filmarks_url`），优先使用已有链接直接提取数据
- **双模式数据获取**：
  - 链接模式：直接从Excel中的URL链接提取数据，速度快且准确
  - 搜索模式：当没有链接时，通过名称搜索获取数据
- 自动从以下网站获取动画评分数据：
  - Bangumi (番组计划) - 使用官方API，支持subject ID直接提取
  - MyAnimeList (MAL) - 网页解析，支持完整URL直接提取
  - AniList (AL) - 使用GraphQL API，支持anime ID直接提取
  - Filmarks (FM) - 网页解析，支持完整URL直接提取
- **智能评分标准化**：自动转换不同平台的评分制度（如AniList 100分制转10分制，Filmarks 5分制转10分制）
- **日期一致性检查**：验证各平台开播日期的一致性，自动检测和汇总日期错误信息
- 智能匹配算法，基于发布年份筛选，确保获取正确的动画条目
- 交叉验证功能，当某个网站未找到匹配条目时，尝试使用其他网站的名称进行二次搜索
- 并发数据获取，同时从四个网站获取数据，提高处理效率
- 将所有评分数据更新到Excel表格中，包括评分、评分人数、条目链接等
- 支持超链接和纯文本URL的自动识别
- 记录详细的日志信息，包括错误和警告

## 安装步骤

### 方法一：从源码运行

1. 克隆或下载本仓库
2. 安装依赖项：
   ```
   pip install -r requirements.txt
   ```

3. 准备一个包含动画名称的Excel文件（参考`mzzb.xlsx`的格式）
4. 运行主程序：
   ```
   python main.py
   ```

### 方法二：使用打包的可执行文件

1. 下载Releases发布页面提供的最新的`mzzb_score.exe`文件
2. 将`mzzb_score.exe`文件与`mzzb.xlsx`表格放在同一目录下
3. 双击运行`mzzb_score.exe`文件

## 使用方法

1. 准备一个Excel文件（默认名称为`mzzb.xlsx`），格式如下：
   - A1单元格：目标年份（如"2024年7月"）
   - 从第二行开始，包含一个"原名"列，填入需要查询的动画名称
   - **可选**：预填各平台URL列（`Bangumi_url`、`Anilist_url`、`Myanimelist_url`、`Filmarks_url`），程序将优先使用这些链接直接提取数据
2. 运行程序，程序会自动执行以下流程：
   - 检查每行是否已有平台链接
   - 对于有链接的平台，直接从链接提取数据（快速准确）
   - 对于没有链接的平台，通过名称搜索获取数据（兜底保障）
3. 程序会自动将获取到的评分数据更新到Excel表格中

## 项目结构

- `main.py`：主程序入口，协调各模块工作
- `models/`：数据模型定义
  - `anime_model.py`：动画数据模型
- `utils/`：工具函数模块
  - `network.py`：网络请求封装和缓存
  - `logger.py`：日志管理
  - `text_processor.py`：文本预处理
  - `global_variables.py`：全局变量管理
  - `link_parser.py`：**链接解析器**，从各平台URL中提取ID和信息
  - `excel_utils.py`：Excel操作工具，包含列助手和安全写入功能
  - `excel_columns.py`：Excel列定义和映射配置
  - `data_validators.py`：数据验证和清理工具
  - `const.py`：常量定义
- `biz/extractors/`：各网站数据提取器
  - `bangumi.py`：Bangumi数据提取（支持ID直接提取和搜索模式）
  - `myanimelist.py`：MyAnimeList数据提取（支持URL直接提取和搜索模式）
  - `anilist.py`：AniList数据提取（支持ID直接提取和搜索模式）
  - `filmarks.py`：Filmarks数据提取（支持URL直接提取和搜索模式）
- `biz/data_process/`：数据处理模块
  - `excel_handler.py`：Excel数据写入处理
  - `score_transformers.py`：**评分标准化转换器**，处理不同平台评分制度转换
  - `date_validator.py`：**日期一致性验证器**，检查各平台开播日期一致性

## 打包指南

使用PyInstaller将项目打包为单个可执行文件：

```
pyinstaller --onefile --name mzzb_score --console --clean main.py
```

## 技术特色

- **链接优先双模式运行**：智能检测Excel中的平台链接，优先使用直接提取模式，搜索模式作为兜底
- **链接解析和URL检测**：支持超链接和纯文本URL，自动从各平台URL中提取关键ID信息
- **评分标准化系统**：自动处理不同平台的评分制度差异（AniList 100分制 → 10分制，Filmarks 5分制 → 10分制）
- **日期一致性检测**：自动检测各平台开播日期的一致性，识别数据冲突并生成错误报告
- **并发处理**：使用线程池同时从四个网站获取数据
- **智能匹配**：基于发布年份筛选候选条目，确保数据准确性
- **交叉验证**：当某网站搜索失败时，使用其他网站的名称重试
- **混合数据源**：结合API（AniList、Bangumi）和网页解析（MAL、Filmarks）
- **请求缓存**：内存缓存机制，避免重复网络请求
- **模块化架构**：清晰的分层设计，便于维护和扩展

## 注意事项

- 为避免请求过于频繁被拒绝，程序在每次处理之间有短暂延时
- 如遇到网络问题，程序会自动重试（最多3次）
- 日志信息会同时输出到控制台和`mzzb_score.log`文件中
- 程序支持处理各平台评分的不同量表，会自动进行标准化转换
- 链接模式比搜索模式更快更准确，建议在Excel中预填已知的平台链接