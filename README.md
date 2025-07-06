# MZZB Score - 动漫评分聚合工具

## 项目介绍

MZZB Score 是一个动漫评分聚合工具，能够自动从多个知名动漫评分网站（Bangumi、MyAnimeList、AniList、Filmarks）获取动画作品的评分数据，并将这些数据整合到Excel表格中，方便用户进行比较和分析。

## 主要功能

- 从Excel表格中读取动画作品名称列表
- 自动从以下网站获取动画评分数据：
    - Bangumi (番组计划) - 使用官方API
    - MyAnimeList (MAL) - 网页解析
    - AniList (AL) - 使用GraphQL API
    - Filmarks (FM) - 网页解析
- 智能匹配算法，基于发布年份筛选，确保获取正确的动画条目
- 交叉验证功能，当某个网站未找到匹配条目时，尝试使用其他网站的名称进行二次搜索
- 并发数据获取，同时从四个网站获取数据，提高处理效率
- 将所有评分数据更新到Excel表格中，包括评分、评分人数、条目链接等
- 记录详细的日志信息，包括错误和警告
- 检测并汇总日期错误信息

## 安装步骤

### 方法一：从源码运行

1. 克隆或下载本仓库
2. 安装依赖项：
   ```
   pip install -r requirements.txt
   ```
   或手动安装：
   ```
   pip install pandas openpyxl requests lxml
   ```
3. 准备一个包含动画名称的Excel文件（参考`mzzb.xlsx`的格式）
4. 运行主程序：
   ```
   python main.py
   ```

### 方法二：使用打包的可执行文件

1. 下载发布页面提供的可执行文件
2. 将可执行文件与Excel表格放在同一目录下
3. 双击运行可执行文件

## 使用方法

1. 准备一个Excel文件（默认名称为`mzzb.xlsx`），格式如下：
   - A1单元格：目标年份（如"2024年7月"）
   - 从第二行开始，包含一个"原名"列，填入需要查询的动画名称
2. 运行程序，等待数据获取和处理完成
3. 程序会自动将获取到的评分数据更新到Excel表格中

## 项目结构

- `main.py`：主程序入口，协调各模块工作
- `models/`：数据模型定义
    - `anime_model.py`：动画数据模型
- `utils/`：工具函数
    - `network.py`：网络请求封装和缓存
    - `logger.py`：日志管理
    - `text_processor.py`：文本预处理
    - `global_variables.py`：全局变量管理
- `biz/extractors/`：各网站数据提取器
    - `bangumi.py`：Bangumi数据提取
    - `myanimelist.py`：MyAnimeList数据提取
    - `anilist.py`：AniList数据提取
    - `filmarks.py`：Filmarks数据提取
- `biz/data_process/`：数据处理模块
    - `excel_handler.py`：Excel数据写入处理

## 打包指南

使用PyInstaller将项目打包为单个可执行文件：

```
pyinstaller --onefile --name mzzb_score --console --clean main.py
```

## 技术特色

- **并发处理**：使用线程池同时从四个网站获取数据
- **智能匹配**：基于发布年份筛选候选条目，确保数据准确性
- **交叉验证**：当某网站搜索失败时，使用其他网站的名称重试
- **混合数据源**：结合API（AniList、Bangumi）和网页解析（MAL、Filmarks）
- **数据一致性检测**：自动检测各平台开播日期的一致性
- **请求缓存**：内存缓存机制，避免重复网络请求

## 注意事项

- 为避免请求过于频繁被拒绝，程序在每次处理之间有短暂延时
- 如遇到网络问题，程序会自动重试（最多3次）
- 日志信息会同时输出到控制台和`mzzb_score.log`文件中
- 程序支持处理各平台评分的不同量表（如AniList的100分制会自动转换为10分制）