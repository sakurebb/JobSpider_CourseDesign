# ============================================================================
# 【合规提示】本代码仅供Python爬虫技术学习交流使用，请勿用于大规模爬取或商业目的。
# 使用本代码前请阅读并遵守BOSS直聘网站的服务协议(https://www.zhipin.com/terms)。
# ============================================================================

"""
JobSpider 数据管道模块

功能概述：
    1. 爬虫启动时自动创建CSV文件并写入表头
    2. 对每条Item进行基础数据清洗（去空格、统一格式）
    3. 将清洗后的数据实时写入CSV文件
    4. 爬虫结束时安全关闭文件

为什么选CSV而不是JSON？
    - CSV可直接用Excel/WPS打开，方便非技术人员查看
    - utf-8-sig编码保证Windows环境下中文不乱码
"""

import csv
import os
from itemadapter import ItemAdapter


class CsvExportPipeline:
    """
    CSV文件导出与数据清洗管道

    工作流程：
        spider_opened → process_item（逐行写入）→ spider_closed

    Attributes:
        file (TextIOWrapper): CSV文件的文件句柄
        writer (csv.DictWriter): CSV字典写入器
        fieldnames (list): CSV文件的列名列表（与Item字段保持一致）
    """

    def __init__(self):
        """初始化管道实例变量"""
        self.file = None       # CSV文件句柄
        self.writer = None     # csv.DictWriter 实例

    # ========================================================================
    #  第一步：爬虫启动时 —— 创建CSV文件，写入表头
    # ========================================================================
    def open_spider(self, spider):
        """
        爬虫启动时的回调，在此处完成文件创建和表头写入。

        参数:
            spider: 当前正在运行的Spider实例，可通过 spider.name 获取爬虫名
        """
        # 输出目录：项目根目录下的 output 文件夹
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        # 如果 output 文件夹不存在则自动创建
        os.makedirs(output_dir, exist_ok=True)

        # 输出文件路径（按爬虫名命名，避免多爬虫数据混在一起）
        csv_file_path = os.path.join(output_dir, f"{spider.name}_jobs.csv")

        # 以 utf-8-sig 编码打开文件
        # utf-8-sig 比 utf-8 多了BOM头，Excel打开时能正确识别中文编码
        self.file = open(csv_file_path, mode="w", encoding="utf-8-sig", newline="")

        # 定义CSV的列名（顺序决定Excel中列的顺序）
        self.fieldnames = [
            "job_name",         # 职位名称
            "salary",           # 薪资范围
            "company_name",     # 公司名称
            "city",             # 工作城市
            "district",         # 工作区域
            "experience",       # 经验要求
            "education",        # 学历要求
            "industry",         # 公司行业
            "company_scale",    # 公司规模
            "recruiter_name",   # 招聘者昵称
            "recruiter_title",  # 招聘者职位
            "publish_time",     # 发布日期
            "job_url",          # 职位详情链接
        ]

        # 创建 DictWriter 并写入表头
        self.writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)
        self.writer.writeheader()

        spider.logger.info(f"CSV文件已创建: {csv_file_path}")
        spider.logger.info(f"表头已写入，共 {len(self.fieldnames)} 列")

    # ========================================================================
    #  第二步：每条Item到来时 —— 清洗 + 写入
    # ========================================================================
    def process_item(self, item, spider):
        """
        处理每条 Item：数据清洗 + 写入CSV。

        参数:
            item: 爬虫 yield 出的 JobSpiderItem 实例
            spider: 当前Spider实例

        返回:
            item: 清洗后的Item（不改变Item本身，仅清洗写入CSV的数据）
        """
        # 将Item转为普通字典，方便操作
        adapter = ItemAdapter(item)
        cleaned_data = {}

        for field in self.fieldnames:
            # 获取原始值，字段不存在则用空字符串兜底
            raw_value = adapter.get(field, "")

            # ---- 数据清洗 ----
            cleaned_value = self._clean_field(raw_value)

            # ---- 统一空白占位 ----
            # 空值统一填 "-"，方便Excel筛选和阅读
            if not cleaned_value:
                cleaned_value = "-"

            cleaned_data[field] = cleaned_value

        # 写入CSV（实际写入时机取决于文件缓冲，爬虫结束时 flush）
        try:
            self.writer.writerow(cleaned_data)
        except Exception as e:
            spider.logger.error(f"写入CSV失败: {e}")

        # 原样返回item，不修改Item对象本身（保持管道链兼容性）
        return item

    # ========================================================================
    #  第三步：爬虫结束时 —— 关闭文件，释放资源
    # ========================================================================
    def close_spider(self, spider):
        """
        爬虫结束时的回调，关闭CSV文件句柄，防止数据丢失。

        参数:
            spider: 当前Spider实例
        """
        if self.file:
            self.file.close()
            spider.logger.info("CSV文件已安全关闭，数据保存完成！")

    # ========================================================================
    #  辅助方法：字段数据清洗
    # ========================================================================
    def _clean_field(self, value):
        """
        对单个字段值进行基础清洗。

        清洗规则：
            1. 去除首尾空格
            2. 将多个连续空格/换行符压缩为单个空格
            3. 统一全角数字/字母为半角（可选，按需启用）

        参数:
            value: 原始字段值（可能是 str、list、None）

        返回:
            str: 清洗后的文本
        """
        # 如果XPath返回的是列表，取第一个有效元素
        if isinstance(value, list):
            value = value[0] if value else ""

        # 确保是字符串类型
        value = str(value) if value else ""

        # 去除首尾空白字符（空格、换行、制表符等）
        value = value.strip()

        # 将内部多个连续空白字符（换行、制表、多余空格）压缩为单个空格
        value = " ".join(value.split())

        return value
