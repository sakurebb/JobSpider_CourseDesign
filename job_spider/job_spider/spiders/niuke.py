# ============================================================================
# 【合规声明】本代码仅供Python爬虫技术课程设计学习交流使用。
# 严禁用于任何商业目的或大规模采集，使用者须自行遵守牛客网服务协议
# (https://www.nowcoder.com/agreement) 及相关法律法规，自行承担不当使用
# 的法律后果。
# ============================================================================

"""
牛客网招聘爬虫 · 核心逻辑 (纯静态请求，零浏览器渲染)

=============================================================================
技术方案：为什么使用API接口而非解析HTML页面？
=============================================================================
牛客网招聘板块（校招/社招）前端为React SPA单页应用，服务端直接返回的HTML
仅为空白骨架（<div id="app"></div>），所有职位数据由浏览器端JavaScript
异步调用内部API后动态渲染。

但我们无需Playwright！经过分析，牛客网内部API接口
(/np-api/u/job/square-search) 对请求来源校验极为宽松，仅需基础
User-Agent即可直接获取JSON格式的结构化职位数据。

使用API接口方案相比浏览器渲染具有以下优势：
    1. 速度极快 — 单次请求<1s，无浏览器启动开销
    2. 数据完整 — JSON结构化数据，无需XPath/CSS解析，零漏抓
    3. 极低资源 — 无需Chromium进程，内存占用可忽略
    4. 维护简单 — API字段稳定，不受前端DOM结构变更影响

=============================================================================
依赖安装（首次运行前执行，仅需一次）：
    pip install scrapy
    （无需安装 scrapy-playwright 或 playwright）

使用方式：
    scrapy crawl niuke

可修改参数（无需改代码逻辑）：
    - 修改 KEYWORD 类变量即可切换搜索关键词
    - 修改 RECRUIT_TYPE 类变量切换校招(1)/社招(2)
    - 修改 MAX_PAGES 类变量限制最大爬取页数
=============================================================================
"""

import json
import time
import uuid
from datetime import datetime

from scrapy import Spider
from scrapy.http import FormRequest

from ..items import JobSpiderItem


class NiukeSpider(Spider):
    """
    牛客网 · 招聘信息爬虫

    通过牛客网内部API接口直接获取JSON格式的职位数据，
    全程使用Scrapy原生静态HTTP请求，无浏览器渲染开销。
    """

    # =========================================================================
    #  爬虫元信息
    # =========================================================================
    name = "niuke"                       # scrapy crawl 时使用的名称
    allowed_domains = [                  # 防止爬虫意外越界到外部站点
        "nowcoder.com",
        "www.nowcoder.com",
    ]

    # =========================================================================
    #  可自定义的搜索参数（修改这些值即可切换搜索条件）
    # =========================================================================
    KEYWORD = "Python"                   # 搜索关键词，可改为 Java / 前端 / 测试 等
    RECRUIT_TYPE = 1                     # 招聘类型: 1=校招, 2=社招
    MAX_PAGES = 10                       # 最大翻页数（防止无限翻页），每页约20条
    PAGE_SIZE = 20                       # 每页职位数量（建议保持默认20）

    def __init__(self, *args, **kwargs):
        """
        初始化爬虫实例，将类变量统一转换为正确类型。

        当通过命令行 -a 参数传值时（如 scrapy crawl niuke -a MAX_PAGES=2），
        所有参数均以字符串形式传入。此方法将其强制转换为类变量声明的原始类型，
        避免后续比较/计算中出现类型错误。
        """
        super().__init__(*args, **kwargs)
        # 确保整数类型变量在命令行传参时也是 int
        self.MAX_PAGES = int(self.MAX_PAGES)
        self.RECRUIT_TYPE = int(self.RECRUIT_TYPE)
        self.PAGE_SIZE = int(self.PAGE_SIZE)

    # =========================================================================
    #  API接口信息
    # =========================================================================
    API_URL = "https://www.nowcoder.com/np-api/u/job/square-search"

    # =========================================================================
    #  本爬虫专属配置（会与 settings.py 合并）
    # =========================================================================
    custom_settings = {
        # ----- 静态请求温和策略 -----
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 1,
    }

    # =========================================================================
    #  学历编码映射表（API返回的eduLevel数值 → 中文描述）
    # =========================================================================
    EDU_LEVEL_MAP = {
        0: "",           # 不限/未知
        1000: "大专",
        3000: "大专",
        5000: "本科",
        6000: "硕士",
        7000: "博士",
        9000: "学历不限",
    }

    # =========================================================================
    #  经验年限编码映射表（API返回的workYearType数值 → 中文描述）
    # =========================================================================
    WORK_YEAR_MAP = {
        0: "",           # 不限/未知
        1: "应届生",
        2: "经验不限",
        3: "1年以下",
        4: "1-3年",
        5: "3-5年",
        6: "5-10年",
        7: "10年以上",
    }

    # =========================================================================
    #  入口：构建API请求
    # =========================================================================
    def start_requests(self):
        """
        Scrapy引擎入口，生成初始搜索请求。

        POST方式请求牛客网内部API接口，搜索指定关键词的职位。
        生成一个随机visitorId（UUID格式），在整个爬取过程中复用，
        模拟正常用户的一次浏览会话。

        Yields:
            FormRequest: 第1页的API搜索请求
        """
        visitor_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)

        # API需要在URL中携带毫秒级时间戳（防缓存，非安全校验）
        url = f"{self.API_URL}?_={timestamp}"

        # POST表单参数（全部为字符串类型）
        form_data = {
            "careerJobId": "",
            "jobCity": "",
            "page": "1",
            "query": self.KEYWORD,
            "random": "true",
            "recommend": "false",
            "recruitType": str(self.RECRUIT_TYPE),
            "salaryType": "2",
            "pageSize": str(self.PAGE_SIZE),
            "requestFrom": "1",
            "order": "0",
            "pageSource": "5001",
            "visitorId": visitor_id,
        }

        recruit_label = "校招" if self.RECRUIT_TYPE == 1 else "社招"
        self.logger.info("=" * 60)
        self.logger.info(
            f"牛客网招聘爬虫启动 - 关键词: {self.KEYWORD}"
            f" | 类型: {recruit_label} | 最大页数: {self.MAX_PAGES}"
        )
        self.logger.info(f"API接口: {self.API_URL}")
        self.logger.info("=" * 60)

        yield FormRequest(
            url=url,
            method="POST",
            formdata=form_data,
            callback=self.parse,
            dont_filter=True,
            meta={
                "visitor_id": visitor_id,
                "current_page": 1,
            },
        )

    # =========================================================================
    #  核心解析：JSON响应 → Item + 翻页
    # =========================================================================
    def parse(self, response):
        """
        解析API返回的JSON数据，逐条提取职位信息，并处理翻页。

        参数:
            response: Scrapy TextResponse（API返回的JSON文本）

        Yields:
            JobSpiderItem  — 单条招聘记录
            FormRequest    — 下一页请求（如未达最大页数）
        """
        # ---- 第1步：解析JSON ----
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            self.logger.error(f"API响应JSON解析失败: {exc}")
            self.logger.error(f"响应内容前300字符: {response.text[:300]}")
            return

        # ---- 第2步：检查API业务状态码 ----
        code = data.get("code")
        if code != 0:
            self.logger.error(
                f"API返回业务异常 - code={code}, msg={data.get('msg', '')}"
            )
            return

        # ---- 第3步：提取分页信息 ----
        result = data.get("data")
        if not result:
            self.logger.warning("API响应中无data字段，终止解析")
            return

        total_count = result.get("totalCount", 0)
        total_page = result.get("totalPage", 0)
        current_page = response.meta.get("current_page", 1)
        job_list = result.get("datas", [])

        if total_count == 0:
            self.logger.warning(
                f"关键词 '{self.KEYWORD}' 搜索结果为零，请尝试其他关键词"
            )
            self.logger.info("=" * 60)
            return

        self.logger.info(
            f"[第{current_page}页] 本页{len(job_list)}条"
            f" | 总计{total_count}条/{total_page}页"
        )

        # ---- 第4步：逐条解析职位数据（异常隔离：单条失败不影响其他） ----
        parsed_count = 0
        for idx, job_wrapper in enumerate(job_list, start=1):
            try:
                item = self._parse_job_item(job_wrapper)
                if item and item.get("job_name"):
                    yield item
                    parsed_count += 1
                else:
                    self.logger.debug(
                        f"第{idx}条数据缺少职位名称，已跳过"
                    )
            except Exception as exc:
                self.logger.error(
                    f"解析第{idx}条职位数据时出错: {exc}"
                )

        self.logger.info(f"[第{current_page}页] 成功解析 {parsed_count} 条")

        # ---- 第5步：翻页逻辑 ----
        if current_page >= self.MAX_PAGES:
            self.logger.info(
                f"已达到最大爬取页数限制（{self.MAX_PAGES}页），停止翻页。"
            )
            self.logger.info("=" * 60)
            return

        if current_page >= total_page:
            self.logger.info(
                f"已爬取全部 {total_page} 页，爬虫任务完成！"
            )
            self.logger.info("=" * 60)
            return

        # 构建下一页请求
        next_page = current_page + 1
        next_req = self._build_next_page_request(response, next_page)
        yield next_req

    # =========================================================================
    #  辅助方法：单条JSON数据 → Item字段映射
    # =========================================================================
    def _parse_job_item(self, job_wrapper):
        """
        将API返回的单条JSON职位数据映射到JobSpiderItem字段。

        API返回格式为 {"data": {...}, "rc_type": ...}，
        其中 data 对象包含职位的全部信息。

        参数:
            job_wrapper: API返回的单条职位原始数据（dict）

        返回:
            JobSpiderItem | None
        """
        job = job_wrapper.get("data", {})
        if not job:
            return None

        item = JobSpiderItem()

        # ---- 职位名称 ----
        item["job_name"] = self._safe_str(job.get("jobName"))

        # ---- 薪资范围（格式化为 "XXK-XXK" 或 "XXK-XXK·N薪"） ----
        salary_min = job.get("salaryMin", 0) or 0
        salary_max = job.get("salaryMax", 0) or 0
        salary_month = job.get("salaryMonth", 0) or 0
        if salary_min and salary_max:
            if salary_month and salary_month != 12:
                item["salary"] = f"{salary_min}K-{salary_max}K·{salary_month}薪"
            else:
                item["salary"] = f"{salary_min}K-{salary_max}K"
        else:
            item["salary"] = ""

        # ---- 职位详情链接 ----
        job_id = job.get("id", "")
        if job_id:
            rt = job.get("recruitType", self.RECRUIT_TYPE)
            item["job_url"] = (
                f"https://www.nowcoder.com/jobs/detail/{job_id}"
                f"?recruitType={rt}"
            )
        else:
            item["job_url"] = ""

        # ---- 公司信息 ----
        company = job.get("recommendInternCompany") or {}
        item["company_name"] = self._safe_str(company.get("companyName"))

        # ---- 行业（取标签列表第一个） ----
        industry_list = company.get("industryTagNameList") or []
        item["industry"] = industry_list[0] if industry_list else ""

        # ---- 公司规模 ----
        item["company_scale"] = self._safe_str(company.get("personScales"))

        # ---- 城市 & 区域 ----
        item["city"] = self._safe_str(job.get("jobCity"))
        item["district"] = self._safe_str(job.get("jobAddress"))

        # ---- 学历要求（优先编码映射表，未命中从标签兜底） ----
        edu_level = job.get("eduLevel", 0) or 0
        item["education"] = self.EDU_LEVEL_MAP.get(edu_level, "")
        if not item["education"]:
            item["education"] = self._extract_from_tags(
                job, ["本科", "硕士", "博士", "大专", "学历不限"]
            )

        # ---- 经验要求（优先编码映射表，未命中从标签兜底） ----
        work_year = job.get("workYearType", 0) or 0
        item["experience"] = self.WORK_YEAR_MAP.get(work_year, "")
        if not item["experience"]:
            item["experience"] = self._extract_from_tags(
                job,
                [
                    "应届生", "经验不限", "在校生", "毕业生",
                    "1年以下", "1-3年", "3-5年", "5-10年", "10年以上",
                ],
            )

        # ---- 毕业年份（仅校招有，作为经验的补充信息） ----
        graduation_year = self._safe_str(job.get("graduationYear"))
        if graduation_year and not item["experience"]:
            item["experience"] = f"应届生（{graduation_year}）"

        # ---- 招聘者信息 ----
        boss_user = job.get("apiSimpleBossUser") or {}
        item["recruiter_name"] = self._safe_str(
            boss_user.get("userAppellation")
        )

        # 招聘者职位（从user.identity中提取）
        user_info = job.get("user") or {}
        identities = user_info.get("identity") or []
        if identities and len(identities) > 0:
            item["recruiter_title"] = self._safe_str(
                identities[0].get("jobName")
            )
        else:
            item["recruiter_title"] = ""

        # ---- 发布时间（毫秒时间戳 → "YYYY-MM-DD"） ----
        create_time = job.get("createTime")
        if create_time:
            try:
                dt = datetime.fromtimestamp(create_time / 1000)
                item["publish_time"] = dt.strftime("%Y-%m-%d")
            except (OSError, ValueError):
                item["publish_time"] = ""
        else:
            item["publish_time"] = ""

        return item

    # =========================================================================
    #  辅助方法：从标签列表中提取特定信息
    # =========================================================================
    @staticmethod
    def _extract_from_tags(job, keywords):
        """
        遍历 pcTagInfo.jobInfoTagList 标签列表，
        查找包含指定关键词的标签文本。

        参数:
            job:      单条API职位数据（dict）
            keywords: 要匹配的关键词列表

        返回:
            str: 第一个匹配到的标签文本，未匹配则返回空字符串
        """
        pc_tag_info = job.get("pcTagInfo") or {}
        tag_list = pc_tag_info.get("jobInfoTagList") or []
        for tag_item in tag_list:
            tag = tag_item.get("tag") or {}
            title = (tag.get("title") or "").strip()
            for kw in keywords:
                if kw in title:
                    return title
        return ""

    # =========================================================================
    #  辅助方法：安全取字符串
    # =========================================================================
    @staticmethod
    def _safe_str(value):
        """
        将任意值安全转换为字符串，None/空值返回空字符串。

        参数:
            value: 任意类型的值

        返回:
            str: 清理后的字符串
        """
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    # =========================================================================
    #  辅助方法：构建下一页请求
    # =========================================================================
    def _build_next_page_request(self, response, next_page):
        """
        构建下一页的API POST请求。

        参数:
            response:   当前页的Response对象（用于获取meta中的visitor_id）
            next_page:  下一页的页码（int）

        返回:
            FormRequest: 下一页的API请求对象
        """
        visitor_id = response.meta.get(
            "visitor_id", str(uuid.uuid4())
        )
        timestamp = int(time.time() * 1000)
        url = f"{self.API_URL}?_={timestamp}"

        form_data = {
            "careerJobId": "",
            "jobCity": "",
            "page": str(next_page),
            "query": self.KEYWORD,
            "random": "true",
            "recommend": "false",
            "recruitType": str(self.RECRUIT_TYPE),
            "salaryType": "2",
            "pageSize": str(self.PAGE_SIZE),
            "requestFrom": "1",
            "order": "0",
            "pageSource": "5001",
            "visitorId": visitor_id,
        }

        self.logger.info(f"[翻页] 请求第 {next_page} 页...")

        return FormRequest(
            url=url,
            method="POST",
            formdata=form_data,
            callback=self.parse,
            dont_filter=True,
            meta={
                "visitor_id": visitor_id,
                "current_page": next_page,
            },
        )


# ============================================================================
#  附录：操作文档
# ============================================================================
#
# 一、依赖安装（首次运行前执行，仅需一次）
#     pip install scrapy
#     （无需安装 scrapy-playwright 或 playwright）
#     （Windows用户建议同时执行 pip install pywin32）
#
# 二、爬虫启动命令
#     cd job_spider
#     scrapy crawl niuke
#
# 三、修改搜索关键词
#     打开本文件，找到 KEYWORD 类变量（约第80行）：
#         KEYWORD = "Python"       ← 修改引号内的关键词即可
#     可改为：Java、前端、测试、数据分析、产品经理 等
#
# 四、切换校招/社招
#     修改 RECRUIT_TYPE 类变量：
#         RECRUIT_TYPE = 1         ← 1=校招, 2=社招
#
# 五、调整最大爬取页数
#     修改 MAX_PAGES 类变量：
#         MAX_PAGES = 10           ← 数字改大改小均可
#
# 六、输出文件
#     CSV文件路径：项目根目录/output/niuke_jobs.csv
#     编码格式：utf-8-sig（Excel/WPS直接打开中文不乱码）
#
# 七、常见问题
#     Q: 爬取结果为0条？
#     A: 检查 KEYWORD 是否过于冷门，尝试改为常见关键词（如 Java、前端）
#
#     Q: 报错 JSON 解析失败？
#     A: 可能是牛客网API临时调整，可检查 API_URL 是否需要更新
#
#     Q: 报错与 Twisted/Reactor 相关？
#     A: Windows用户执行 pip install pywin32 后重试
#
#     Q: 如何限制城市？
#     A: 修改 start_requests 中 form_data 的 "jobCity" 参数为具体城市名
#        例如 "jobCity": "北京"、"jobCity": "上海"
# ============================================================================
