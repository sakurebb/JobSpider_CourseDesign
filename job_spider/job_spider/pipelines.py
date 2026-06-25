# ============================================================================
# 【合规声明】本代码仅供Python爬虫技术课程设计学习交流使用。
# 严禁用于任何商业目的或大规模采集，使用者须自行遵守目标网站服务协议
# 及相关法律法规，自行承担不当使用的法律后果。
# ============================================================================

"""
JobSpider · 数据管道模块 (兼容 Scrapy 2.9+)

=============================================================================
核心功能：
    1. CSV文件持久化存储（utf-8-sig 编码，Excel/WPS打开中文不乱码）
    2. 爬虫启动时自动创建文件并写入表头（open_spider 钩子）
    3. 每条Item经数据清洗后实时写入CSV（process_item）
    4. 爬虫结束时安全关闭文件句柄（close_spider 钩子）

Scrapy 2.9+ 兼容性设计：
    采用 from_crawler 工厂方法保存 crawler 引用，使用标准的 open_spider /
    close_spider 钩子方法（非信号注册），完全兼容 Scrapy 2.9 及未来版本。
=============================================================================
"""

import csv
import logging
import os

from itemadapter import ItemAdapter


class CsvExportPipeline:
    """
    CSV文件导出 + 数据清洗管道

    生命周期（由Scrapy引擎驱动）：
        from_crawler()     → 保存crawler引用，返回管道实例
        open_spider()      → 创建CSV文件 + 写入表头
        process_item()     → 清洗字段 + 逐行写入（每条Item调用一次）
        close_spider()     → 关闭文件句柄，确保数据落盘

    注意：整个管道仅在爬虫进程中存活一份实例，所有Item共用同一文件句柄。
    """

    # =========================================================================
    #  CSV 列定义（顺序决定 Excel 中列的展示顺序，共13个字段）
    # =========================================================================
    FIELD_NAMES = [
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

    def __init__(self):
        """初始化实例变量（文件句柄在 open_spider 中赋值）。"""
        self.file = None
        self.writer = None
        self.logger = logging.getLogger(__name__)

    # =========================================================================
    #  from_crawler 工厂方法（Scrapy 2.9+ 推荐模式）
    # =========================================================================
    @classmethod
    def from_crawler(cls, crawler):
        """
        Scrapy标准工厂方法。

        由框架在启动时调用，传入crawler对象，返回pipeline实例。
        通过保存crawler引用，管道可在任意方法中访问引擎配置。

        参数:
            crawler: scrapy.crawler.Crawler 实例

        返回:
            CsvExportPipeline 实例
        """
        pipeline = cls()
        pipeline.crawler = crawler
        pipeline.logger = logging.getLogger(__name__)
        return pipeline

    # =========================================================================
    #  open_spider 钩子：爬虫启动 → 创建CSV并写入表头
    # =========================================================================
    def open_spider(self, spider):
        """
        爬虫启动时由Scrapy引擎自动调用（在发送请求之前触发）。

        负责创建 output 目录、打开CSV文件、写入表头行。

        参数:
            spider: 当前运行的Spider实例
        """
        # ---- 定位输出目录（项目根目录下的 output/） ----
        # pipelines.py 位于 job_spider/job_spider/ 下，
        # 向上一级到 job_spider/，再向上一级到项目根目录
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        output_dir = os.path.join(project_root, "output")
        os.makedirs(output_dir, exist_ok=True)

        # ---- CSV 文件路径（以爬虫名命名） ----
        csv_path = os.path.join(output_dir, f"{spider.name}_jobs.csv")

        # ---- 打开文件（utf-8-sig = UTF-8 + BOM，Excel/WPS友好） ----
        self.file = open(
            csv_path, mode="w", encoding="utf-8-sig", newline=""
        )

        # ---- 创建DictWriter并写入表头 ----
        self.writer = csv.DictWriter(self.file, fieldnames=self.FIELD_NAMES)
        self.writer.writeheader()

        self.logger.info(f"CSV文件已创建: {csv_path}")
        self.logger.info(f"表头列数: {len(self.FIELD_NAMES)}")

    # =========================================================================
    #  process_item 核心处理：清洗 + 写入（每条Item触发一次）
    # =========================================================================
    def process_item(self, item, spider):
        """
        处理单条Item：清洗字段 → 写入CSV行。

        该方法对每条由爬虫yield的Item都会被Scrapy引擎调用。
        清洗后的数据仅用于CSV写入，原始Item对象不做修改，
        以保证后续管道（如有）能拿到原始值。

        参数:
            item:  爬虫yield的JobSpiderItem
            spider: 当前Spider实例（Scrapy标准接口要求）

        返回:
            item: 原样返回，不做修改
        """
        if self.writer is None:
            # 防御：如果writer未初始化（如open_spider未触发），则跳过
            self.logger.error("CSV writer未初始化，跳过写入！")
            return item

        adapter = ItemAdapter(item)
        row = {}

        for field in self.FIELD_NAMES:
            raw = adapter.get(field, "")
            cleaned = self._clean_value(raw)
            # 空值填充为 "-"，确保CSV单元格不为空
            row[field] = cleaned if cleaned else "-"

        try:
            self.writer.writerow(row)
        except Exception as exc:
            self.logger.error(f"写入CSV行失败: {exc}")

        return item  # 不改变Item，保持管道链兼容

    # =========================================================================
    #  close_spider 钩子：爬虫结束 → 关闭文件
    # =========================================================================
    def close_spider(self, spider):
        """
        爬虫完全结束后由Scrapy引擎自动调用（无论正常结束还是被手动终止）。

        安全关闭CSV文件句柄，确保缓冲区数据写入磁盘。

        参数:
            spider: 当前Spider实例
        """
        if self.file:
            self.file.close()
            self.logger.info("CSV文件已安全关闭")

    # =========================================================================
    #  静态工具：字段值清洗
    # =========================================================================
    @staticmethod
    def _clean_value(value):
        """
        清洗单个字段值。

        清洗规则:
            1. 若为列表（XPath多值返回），取第一个非空元素
            2. 转为字符串，去除首尾空白
            3. 压缩内部连续空白（多空格、换行、制表符 → 单空格）

        参数:
            value: 原始字段值（str / list / None / 其他）

        返回:
            str: 清洗后的文本，空串表示无有效内容
        """
        # 列表 → 第一个非空元素
        if isinstance(value, list):
            value = next((v for v in value if v), "")

        # 统一为字符串
        if not isinstance(value, str):
            value = str(value) if value is not None else ""

        # 去首尾空白
        value = value.strip()

        # 压缩内部空白
        value = " ".join(value.split())

        return value
