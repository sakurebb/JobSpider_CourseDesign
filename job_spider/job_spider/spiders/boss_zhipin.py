# ============================================================================
# 【合规提示】本代码仅供Python爬虫技术学习交流使用，请勿用于大规模爬取或商业目的。
# 使用本代码前请阅读并遵守BOSS直聘网站的服务协议(https://www.zhipin.com/terms)。
# 不当使用爬虫可能违反相关法律法规，使用者需自行承担一切法律后果。
# ============================================================================

"""
BOSS直聘爬虫核心逻辑模块

功能概述：
    1. 从BOSS直聘职位搜索列表页抓取招聘信息
    2. 使用 XPath 进行数据提取
    3. 自动翻页，直到最后一页
    4. 异常隔离：单条数据解析失败不影响整体爬取

使用方式：
    scrapy crawl boss_zhipin

注意事项：
    - 起始URL中的 query 和 city 参数可按需修改
    - 爬取间隔已在 settings.py 中设为2秒/次，请勿调低
    - BOSS直聘页面结构可能更新，若XPath失效请按F12检查当前HTML结构后调整
"""

import scrapy
from urllib.parse import urljoin

# 导入自定义Item类
from ..items import JobSpiderItem


class BossZhipinSpider(scrapy.Spider):
    """
    BOSS直聘招聘信息爬虫

    继承自 scrapy.Spider（基础爬虫类），不使用 CrawlSpider，
    以便手动控制XPath提取逻辑和翻页流程，代码更易理解和调试。
    """
    # ----- 爬虫标识 -----
    name = "boss_zhipin"                # 爬虫唯一名称，scrapy crawl 时使用
    allowed_domains = ["zhipin.com"]    # 限定域名，防止爬虫跑偏到其他网站

    # ----- 起始URL配置 -----
    # 【提示】下方URL可按需修改：
    #   - query=Python      → 搜索关键词，可改为 Java、前端、产品经理 等
    #   - city=100010000    → 城市编码（100010000=北京），常见城市码见下方注释
    #     · 北京: 100010000   · 上海: 101020100   · 广州: 101280100
    #     · 深圳: 101280600   · 杭州: 101210100   · 成都: 101270100
    #   - page=1            → 起始页码
    start_urls = [
        "https://www.zhipin.com/web/geek/job?query=Python&city=100010000"
    ]

    # ----- 自定义配置（仅对本爬虫生效） -----
    # 可以通过 custom_settings 覆盖项目全局 settings.py 的配置
    custom_settings = {
        # 本爬虫针对单一域名，并发数设为1最安全
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        # 每次请求间隔（秒），与 settings.py 中的 DOWNLOAD_DELAY 叠加生效
        # 保守设为2秒，避免触发反爬
        "DOWNLOAD_DELAY": 2,
    }

    # ========================================================================
    #  核心解析方法：parse()
    #  每请求一个URL（起始URL或翻页URL），Scrapy都会回调此方法
    # ========================================================================
    def parse(self, response):
        """
        解析职位搜索列表页，提取每条招聘信息并处理翻页。

        参数:
            response: Scrapy 下载器返回的 HTTP 响应对象

        Yields:
            JobSpiderItem: 每条招聘记录
            scrapy.Request: 下一页的请求（如果有下一页）
        """
        self.logger.info("=" * 60)
        self.logger.info(f"正在解析页面: {response.url}")

        # --------------------------------------------------------------------
        # 第1步：定位所有职位卡片
        # --------------------------------------------------------------------
        # BOSS直聘列表页中，每个职位是一个 <li> 元素，外层是 job-list 容器。
        # 常见的选择器模式（根据当前页面结构调整）：
        #   - 新版SPA页面: //li[contains(@class, "job-card-wrapper")]
        #   - 旧版页面:     //div[@class="job-list"]//li
        #   - 通用尝试:     //li[contains(@class, "job-")]
        #
        # 【重要】如果XPath失效，请用浏览器打开目标页面 → F12开发者工具 →
        #        找到职位卡片对应的DOM元素 → 更新下方XPath表达式
        job_cards = response.xpath(
            '//li[contains(@class, "job-card-wrapper")]'
            '| //div[@class="job-list"]//li'
            '| //div[contains(@class, "job-primary")]'
        )

        # 如果没有匹配到任何卡片，尝试更宽泛的选择器并打印调试信息
        if not job_cards:
            self.logger.warning(
                "未匹配到职位卡片！当前页面结构可能与XPath不匹配。"
                "正在尝试备用选择器..."
            )
            # 备用选择器：尝试匹配任何包含 job 类名的 li 或 div
            job_cards = response.xpath(
                '//li[contains(@class, "job")]'
                '| //div[contains(@class, "job-")]'
            )

        self.logger.info(f"本页匹配到 {len(job_cards)} 条职位卡片")

        # --------------------------------------------------------------------
        # 第2步：逐条提取职位信息
        # --------------------------------------------------------------------
        for card in job_cards:
            try:
                item = self._parse_job_card(card, response.url)
                if item and item.get("job_name"):
                    yield item
            except Exception as e:
                # 单条数据解析失败时记录日志并继续，不中断整个爬虫
                self.logger.error(f"解析单条职位卡片时出错: {e}", exc_info=True)
                continue

        # --------------------------------------------------------------------
        # 第3步：翻页处理
        # --------------------------------------------------------------------
        yield from self._handle_pagination(response)

    # ========================================================================
    #  辅助方法：解析单条职位卡片
    # ========================================================================
    def _parse_job_card(self, card, current_url):
        """
        用XPath从单个职位卡片中提取所有字段。

        参数:
            card: 单个职位卡片的 Selector 对象
            current_url: 当前列表页URL（用于拼接相对链接）

        返回:
            JobSpiderItem 实例，或 None（解析失败时）
        """
        item = JobSpiderItem()

        # ---- 职位名称 ----
        # 常见选择器: h3>a 中的文本，或 span.job-name
        job_name = (
            card.xpath('.//span[@class="job-name"]/text()').get()
            or card.xpath('.//span[contains(@class, "job-name")]/text()').get()
            or card.xpath('.//a[contains(@class, "job-title")]/text()').get()
            or card.xpath('.//div[contains(@class, "job-title")]//text()').get()
            or ""
        )
        item["job_name"] = job_name

        # ---- 薪资 ----
        salary = (
            card.xpath('.//span[@class="salary"]/text()').get()
            or card.xpath('.//span[contains(@class, "salary")]/text()').get()
            or card.xpath('.//span[contains(@class, "red")]/text()').get()
            or ""
        )
        item["salary"] = salary

        # ---- 职位详情链接 ----
        # 通常是职位名称上的 <a> 标签的 href 属性
        job_url = (
            card.xpath('.//a[contains(@class, "job-title")]/@href').get()
            or card.xpath('.//span[@class="job-name"]/a/@href').get()
            or card.xpath('.//a[contains(@href, "job_detail")]/@href').get()
            or card.xpath('.//a[contains(@href, "/job/")]/@href').get()
            or ""
        )
        # 补全为绝对URL
        if job_url and not job_url.startswith("http"):
            job_url = urljoin(current_url, job_url)
        item["job_url"] = job_url

        # ---- 公司名称 ----
        company_name = (
            card.xpath('.//h3[@class="company-name"]/a/text()').get()
            or card.xpath('.//h3[contains(@class, "company-name")]//text()').get()
            or card.xpath('.//div[contains(@class, "company-text")]//h3/a/text()').get()
            or card.xpath('.//a[contains(@ka, "company")]/text()').get()
            or ""
        )
        item["company_name"] = company_name

        # ---- 公司行业 ----
        industry = (
            card.xpath('.//li[contains(@class, "company-industry")]/text()').get()
            or card.xpath('.//p[contains(@class, "industry")]/text()').get()
            or card.xpath(
                './/div[contains(@class, "company-text")]//p/text()[1]'
            ).get()
            or ""
        )
        item["industry"] = industry

        # ---- 公司规模 ----
        company_scale = (
            card.xpath('.//li[contains(@class, "company-scale")]/text()').get()
            or card.xpath('.//p[contains(@class, "scale")]/text()').get()
            or card.xpath(
                './/div[contains(@class, "company-text")]//p/text()[last()]'
            ).get()
            or ""
        )
        item["company_scale"] = company_scale

        # ---- 工作城市 & 区域 ----
        # 城市和区域通常在标签列表中：<p>北京 朝阳区 · 3-5年 · 本科</p>
        # 策略：获取包含地点信息的完整文本，再拆分
        job_tags_text = (
            card.xpath('.//p[contains(@class, "job-limit")]//text()').get()
            or card.xpath(
                './/div[contains(@class, "job-limit")]//span/text()'
            ).get()
            or ""
        )

        if not job_tags_text:
            # 备用：单独提取每个标签
            city = (
                card.xpath(
                    './/span[contains(@class, "job-area")]/text()'
                ).get()
                or ""
            )
            district = ""
            experience = ""
            education = ""
        else:
            # 标签文本格式示例: "北京 朝阳区 3-5年 本科"
            # 按空格/分隔符拆分
            parts = [p.strip() for p in job_tags_text.replace("·", " ").split() if p.strip()]
            city = parts[0] if len(parts) >= 1 else ""
            district = parts[1] if len(parts) >= 2 else ""
            experience = ""
            education = ""
            # 遍历剩余部分，区分经验与学历
            for p in parts[2:]:
                if any(kw in p for kw in ["年", "应届", "经验"]):
                    experience = p
                elif any(kw in p for kw in ["本科", "大专", "硕士", "博士", "学历"]):
                    education = p

        item["city"] = city
        item["district"] = district

        # ---- 经验要求 ----
        # 如果上面已从标签中提取到了经验，则跳过，否则尝试单独提取
        if not experience:
            experience = (
                card.xpath('.//li[contains(@class, "exp")]/text()').get()
                or card.xpath('.//span[contains(text(), "年")]/text()').get()
                or ""
            )
        item["experience"] = experience

        # ---- 学历要求 ----
        if not education:
            education = (
                card.xpath('.//li[contains(@class, "edu")]/text()').get()
                or card.xpath(
                    './/span[contains(text(), "本科") or contains(text(), "大专") '
                    'or contains(text(), "硕士") or contains(text(), "博士")]/text()'
                ).get()
                or ""
            )
        item["education"] = education

        # ---- 招聘者信息（列表页有时会展示） ----
        recruiter_name = (
            card.xpath('.//div[contains(@class, "info-publis")]//h3/text()').get()
            or card.xpath('.//span[contains(@class, "recruiter")]/text()').get()
            or ""
        )
        item["recruiter_name"] = recruiter_name

        recruiter_title = (
            card.xpath('.//div[contains(@class, "info-publis")]//p/text()').get()
            or ""
        )
        item["recruiter_title"] = recruiter_title

        # ---- 发布时间 ----
        publish_time = (
            card.xpath('.//span[contains(@class, "time")]/text()').get()
            or card.xpath('.//span[contains(text(), "发布")]/text()').get()
            or card.xpath('.//span[contains(text(), "活跃")]/text()').get()
            or ""
        )
        item["publish_time"] = publish_time

        return item

    # ========================================================================
    #  辅助方法：翻页处理
    # ========================================================================
    def _handle_pagination(self, response):
        """
        识别页面中的"下一页"按钮并生成下一页请求。

        翻页策略：
            1. 优先查找 class="next" 的 <a> 标签
            2. 其次查找包含"下一页"文字的链接
            3. 如果找不到可用的下一页链接，说明已是最后一页，停止翻页

        参数:
            response: 当前页面的 HTTP 响应对象

        Yields:
            scrapy.Request: 下一页的请求（如果有），或 None
        """
        # 方式1：查找 class 为 "next" 的翻页链接
        next_page_url = response.xpath(
            '//a[contains(@class, "next")]/@href'
        ).get()

        # 方式2：查找文字为"下一页"的链接
        if not next_page_url:
            next_page_url = response.xpath(
                '//a[contains(text(), "下一页")]/@href'
            ).get()

        # 方式3：查找翻页器中 disabled 为非最后一页的 next 按钮
        if not next_page_url:
            next_page_url = response.xpath(
                '//div[contains(@class, "page")]'
                '//a[contains(@class, "next") and not(contains(@class, "disabled"))]/@href'
            ).get()

        if next_page_url:
            # 补全为绝对URL
            next_page_url = urljoin(response.url, next_page_url)
            self.logger.info(f"找到下一页: {next_page_url}")

            # 生成下一页的请求，回调方法依然是 self.parse（递归解析）
            yield scrapy.Request(
                url=next_page_url,
                callback=self.parse,
                # dont_filter=True: 即使URL在去重集合中，也强制请求
                # （通常翻页URL不会重复，加上更安全）
                dont_filter=True,
            )
        else:
            self.logger.info(
                "未找到下一页链接，已到达最后一页，翻页结束。"
            )
            self.logger.info("=" * 60)
