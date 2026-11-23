# utils/excel/excel_utils.py
# Excel操作相关的工具函数

import logging
import re

from .excel_columns import ExcelColumns


class ExcelColumnHelper:
    """Excel列定位助手，支持通过列名定位列位置"""

    def __init__(self, ws, header_row=2):
        self.ws = ws
        self.header_row = header_row
        self.columns = {}
        self._build_column_mapping()

    def _build_column_mapping(self):
        """构建列名到列索引的映射"""
        try:
            for idx, cell in enumerate(self.ws[self.header_row]):
                if cell.value and str(cell.value).strip():
                    clean_name = str(cell.value).strip()
                    self.columns[clean_name] = idx
            logging.info(f"成功映射 {len(self.columns)} 个Excel列")
        except Exception as e:
            logging.error(f"构建列映射时出错: {e}")

    def get_col_index(self, column_name):
        """获取列索引，如果列不存在返回None"""
        return self.columns.get(column_name.strip())

    def has_column(self, column_name):
        """检查列是否存在"""
        return column_name.strip() in self.columns

    def safe_write(self, row, column_name, value):
        """安全写入数据到指定列"""
        col_idx = self.get_col_index(column_name)
        if col_idx is not None:
            try:
                row[col_idx].value = value if value is not None else None
                return True
            except Exception as e:
                logging.error(f"写入列 '{column_name}' 时出错: {e}")
                return False
        else:
            logging.warning(f"列 '{column_name}' 不存在，跳过写入")
            return False

    def safe_write_hyperlink(self, row_num, column_name, url, display_text=None):
        """安全写入超链接到指定列"""
        col_idx = self.get_col_index(column_name)
        if col_idx is not None and url:
            try:
                cell = self.ws.cell(row=row_num, column=col_idx + 1)
                cell.hyperlink = url
                cell.value = display_text if display_text else url
                return True
            except Exception as e:
                logging.error(f"写入超链接到列 '{column_name}' 时出错: {e}")
                return False
        else:
            if col_idx is None:
                logging.warning(f"列 '{column_name}' 不存在，跳过超链接写入")
            return False


def get_template_version(ws, col_helper=None):
    """
    读取 Excel 模板版本号，兼容三套官方模板的不同列宽：
    1. 优先读取 M1（标准 mzzb.xlsx）
    2. 其次读取 Filmarks 列对应的第 1 行单元格（首月模板 L1 / 完结模板 R1）
    3. 兜底扫描第 1 行中的 8 位 YYYYMMDD 版本整数
    """
    m1_val = ws["M1"].value
    if isinstance(m1_val, int):
        return m1_val
    if isinstance(m1_val, str) and m1_val.strip().isdigit():
        return int(m1_val.strip())

    if col_helper is None:
        col_helper = ExcelColumnHelper(ws)

    fm_idx = col_helper.get_col_index(ExcelColumns.FILMARKS_SCORE)
    if fm_idx is not None:
        fm_header_val = ws.cell(row=1, column=fm_idx + 1).value
        if isinstance(fm_header_val, int):
            return fm_header_val
        if isinstance(fm_header_val, str) and fm_header_val.strip().isdigit():
            return int(fm_header_val.strip())

    for col in range(1, min(ws.max_column + 1, 45)):
        val = ws.cell(row=1, column=col).value
        if isinstance(val, int) and 20200000 <= val <= 20991231:
            return val
        if isinstance(val, str) and re.fullmatch(r"20\d{6}", val.strip()):
            return int(val.strip())

    return m1_val


def safe_write_cell(cell, value):
    """通用的安全写入单元格函数"""
    try:
        cell.value = value if value is not None else None
    except Exception as e:
        logging.error(f"写入单元格时出错: {e}")


def get_workbook_info(file_path):
    """获取工作簿基本信息"""
    try:
        from openpyxl import load_workbook

        wb = load_workbook(file_path)
        ws = wb.active
        return {
            "worksheet_name": ws.title,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "target_year": str(ws["A1"].value)[:4] if ws["A1"].value else None,
        }
    except Exception as e:
        logging.error(f"获取工作簿信息时出错: {e}")
        return {}
