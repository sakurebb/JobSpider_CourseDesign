# ============================================================================
# 【合规声明】本代码仅供Python爬虫技术课程设计学习交流使用。
# 严禁用于任何商业目的或大规模采集，使用者须自行遵守BOSS直聘网站服务协议
# (https://www.zhipin.com/terms) 及相关法律法规，自行承担不当使用的法律后果。
# ============================================================================

"""
JobSpider · 数据管道模块 (兼容 Scrapy 2.16)

=============================================================================
核心功能：
    1. CSV文件持久化存储（utf-8-sig 编码，Excel/WPS打开中文不乱码）
    2. 爬虫启动时自动创建文件并写入表头
    3. 每条Item经数据清洗后实时写入CSV
    4. 爬虫结束时安全关闭文件句柄，防止数据丢失

Scrapy 2.16 兼容性设计：
    本管道摒弃旧版 open_spider() / close_spider() 直接接收 spider 参数
    的写法，统一采用 from_crawler 工厂模式 + signal 注册机制，完全消除
    ScrapyDeprecationWarning，确保在 Scrapy 2.16 及未来版本正常运行。
=============================================================================
"""

import csv
import os

from itemadapter import ItemAdapter
from scrapy import signals


class CsvExportPipeline:
    """
    CSV文件导出 + 数据清洗管道

    生命周期（由 Scrapy 信号驱动）：
        from_crawler()
          └─ 注册 spider_opened / spider_closed 信号
              └─ _on_spider_opened():  创建CSV + 写表头
              └─ process_item():       清洗 + 逐行写入（每条Item调用一次）
              └─ _on_spider_closed():  关闭文件句柄

    注意：整个管道仅在爬虫进程中存活一份实例，所有 Item 共用同一文件句柄。
    """

    # =========================================================================
    #  CSV 列定义（顺序决定 Excel 中列的展示顺序）
    # =========================================================================
    FIELD_NAMES = [
        "job_name",         # 职位名称
        "salary",           # 薪资范围
        "company_name",     # 公司名称
        "city",             # 工作城市
        "district",         # 工作区域
        "experience",      # 经验要求
        "education",        # 学历要求
        "industry",         # 公司行业
        "company_scale",    # 公司规模
        "recruiter_name",   # 招聘者昵称
        "recruiter_title",  # 招聘者职位
        "publish_time",     # 发布日期/活跃状态
        "job_url",          # 职位详情链接
    ]

    def __init__(self):
        """初始化实例变量（文件句柄在外层打开后赋值）"""
        self.file = None
        self.writer = None

    # =========================================================================
    #  from_crawler 工厂方法（Scrapy 2.16 推荐模式）
    # =========================================================================
    @classmethod
    def from_crawler(cls, crawler):
        """
        Scrapy 标准工厂方法。

        由框架在启动时调用，传入 crawler 对象，返回 pipeline 实例。
        通过 crawler.signals.connect() 将启动/结束回调注册到信号系统，
        彻底替代旧版 open_spider(self, spider) 写法，消除废弃警告。

        参数:
            crawler: scrapy.crawler.Crawler 实例

        返回:
            CsvExportPipeline 实例
        """
        pipeline = cls()
        # 将 spider_opened / spider_closed 绑定到 Scrapy 信号
        crawler.signals.connect(pipeline._on_spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(pipeline._on_spider_closed, signal=signals.spider_closed)
        return pipeline

    # =========================================================================
    #  信号回调：爬虫启动 → 创建 CSV 并写入表头
    # =========================================================================
    def _on_spider_opened(self, spider):
        """
        spider_opened 信号回调。

        在爬虫启动、开始发送请求之前触发。
        负责创建 output 目录、打开CSV文件、写入表头行。

        参数:
            spider: 当前运行的 Spider 实例
        """
        # ---- 输出目录（项目根目录下的 output/） ----
        # 定位到 job_spider 项目根（pipelines.py 的上一级目录的上一级）
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        output_dir = os.path.join(project_root, "output")
        os.makedirs(output_dir, exist_ok=True)

        # ---- CSV 文件路径（以爬虫名命名） ----
        csv_path = os.path.join(output_dir, f"{spider.name}_jobs.csv")

        # ---- 打开文件（utf-8-sig = UTF-8 + BOM，Excel 友好） ----
        self.file = open(
            csv_path, mode="w", encoding="utf-8-sig", newline=""
        )

        # ---- 创建 DictWriter 并写表头 ----
        self.writer = csv.DictWriter(self.file, fieldnames=self.FIELD_NAMES)
        self.writer.writeheader()

        spider.logger.info(f"📁 CSV 文件已创建: {csv_path}")
        spider.logger.info(f"📋 表头列数: {len(self.FIELD_NAMES)}")

    # =========================================================================
    #  核心处理：清洗 + 写入（每条 Item 触发一次）
    # =========================================================================
    def process_item(self, item, spider):
        """
        处理单条 Item：清洗字段 → 写入 CSV 行。

        该方法对每条经爬虫 yield 的 Item 都会被 Scrapy 引擎调用。
        清洗后的数据仅用于 CSV 写入，原始 Item 对象不做修改，
        以保证后续管道（如有）能拿到原始值。

        参数:
            item:  爬虫 yield 的 JobSpiderItem
            spider: 当前 Spider 实例

        返回:
            item: 原样返回，不做修改
        """
        if self.writer is None:
            # 防御：如果某种原因 writer 未初始化，直接返回 item
            spider.logger.error("CSV writer 未初始化，跳过写入！")
            return item

        adapter = ItemAdapter(item)
        row = {}

        for field in self.FIELD_NAMES:
            raw = adapter.get(field, "")
            cleaned = self._clean_value(raw)
            row[field] = cleaned if cleaned else "-"

        try:
            self.writer.writerow(row)
        except Exception as exc:
            spider.logger.error(f"写入CSV行失败: {exc}")

        return item  # 不改变 Item，保持管道链兼容

    # =========================================================================
    #  信号回调：爬虫结束 → 关闭文件
    # =========================================================================
    def _on_spider_closed(self, spider, reason):
        """
        spider_closed 信号回调。

        爬虫完全结束后（无论正常结束还是被手动终止）触发。
        安全关闭 CSV 文件句柄，确保缓冲区数据写入磁盘。

        参数:
            spider: 当前 Spider 实例
            reason: 关闭原因（'finished' / 'cancelled' / 'shutdown' 等）
        """
        if self.file:
            self.file.close()
            spider.logger.info(
                f"✅ CSV 文件已安全关闭 (关闭原因: {reason})"
            )

    # =========================================================================
    #  静态工具：字段值清洗
    # =========================================================================
    @staticmethod
    def _clean_value(value):
        """
        清洗单个字段值。

        清洗规则:
            1. 若为列表（XPath 多值返回），取第一个非空元素
            2. 转为字符串，去除首尾空白
            3. 压缩内部连续空白（多空格、换行、制表符 → 单空格）

        参数:
            value: 原始字段值（str / list / None / 其他）

        返回:
            str: 清洗后的文本，空串表示无有效内容
        """
        # 列表 → 第一个元素
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
