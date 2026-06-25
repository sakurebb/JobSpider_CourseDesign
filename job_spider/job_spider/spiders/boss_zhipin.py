# ============================================================================
# 【合规声明】本代码仅供Python爬虫技术课程设计学习交流使用。
# 严禁用于任何商业目的或大规模采集，使用者须自行遵守BOSS直聘网站服务协议
# (https://www.zhipin.com/terms) 及相关法律法规，自行承担不当使用的法律后果。
# ============================================================================

"""
BOSS直聘爬虫 · 核心逻辑 (兼容 Scrapy 2.16 + scrapy-playwright)

=============================================================================
关键技术决策：为什么引入 Playwright？
=============================================================================
BOSS直聘职位搜索页是React SPA单页应用，所有岗位数据由浏览器端
JavaScript异步调用API后动态渲染。Scrapy默认HTTP下载器不执行JS，
拿到的HTML仅为空白骨架（<div id="app"></div>），因此XPath匹配数恒为0。

Playwright 启动完整的 Chromium 浏览器环境，等待JS执行完毕、DOM渲染
完成后返回完整的HTML给Scrapy，从根本上解决"拿不到数据"的问题。

依赖安装（首次运行前执行，仅需一次）：
    pip install scrapy-playwright
    playwright install chromium

=============================================================================
使用方式：
    scrapy crawl boss_zhipin

可修改参数（无需改代码逻辑）：
    - 修改 KEYWORD / CITY_CODE 两个类变量即可切换搜索条件
    - 城市编码速查表见下方注释
=============================================================================
"""

from urllib.parse import urljoin

import scrapy
from scrapy import Request

# ---- 导入自定义Item ----
from ..items import JobSpiderItem

# ---- 尝试导入 Playwright 支持 ----
try:
    from scrapy_playwright.page import PageMethod
    PLAYWRIGHT_AVAILABLE = True
except ImportError:                     # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False
    PageMethod = None                   # 占位，避免 NameError


# ============================================================================
#  城市编码速查表（BOSS直聘 city 参数）
#  可直接赋值给下方 CITY_CODE 常量的 value
# ============================================================================
#   北京: 100010000     上海: 101020100     广州: 101280100
#   深圳: 101280600     杭州: 101210100     成都: 101270100
#   南京: 101190100     武汉: 101200100     西安: 101110100
#   苏州: 101190400     重庆: 100040000     长沙: 101250100


class BossZhipinSpider(scrapy.Spider):
    """
    BOSS直聘 · 招聘信息爬虫

    继承 scrapy.Spider（基础类），未使用 CrawlSpider，
    以便对XPath提取逻辑和翻页流程做细粒度控制，代码更清晰、更易调试。
    """

    # =========================================================================
    #  爬虫元信息
    # =========================================================================
    name = "boss_zhipin"               # scrapy crawl 时使用的名称
    allowed_domains = ["zhipin.com"]   # 防止爬虫意外越界到外部站点

    # =========================================================================
    #  可自定义的搜索参数（修改这两个值即可切换搜索条件）
    # =========================================================================
    KEYWORD = "Python"                 # 搜索关键词，可改为 Java / 前端 等
    CITY_CODE = "100010000"            # 城市编码，100010000 = 北京，速查表见本文件头部

    # =========================================================================
    #  动态构建起始URL（f-string 拼接，避免手动修改URL字符串）
    # =========================================================================
    @property
    def search_url(self):
        """根据 KEYWORD 和 CITY_CODE 动态生成搜索页URL"""
        return (
            f"https://www.zhipin.com/web/geek/job"
            f"?query={self.KEYWORD}&city={self.CITY_CODE}"
        )

    start_urls = []  # 声明后由 start_requests 接管，此处置空便于阅读

    # =========================================================================
    #  本爬虫专属配置（custom_settings 会与 settings.py 合并）
    # =========================================================================
    custom_settings = {
        # ----- 单域名温和策略 -----
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 2,

        # ----- Playwright 下载处理器（路由 http/https 请求到 Chromium）-----
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
    }

    # =========================================================================
    #  入口：构建起始请求（注入 Playwright 渲染指令）
    # =========================================================================
    def start_requests(self):
        """
        替代 start_urls 的请求入口。
        每一个请求都携带 playwright meta 标记，告知 DownloadHandler
        使用 Chromium 渲染此页面，而非直接返回服务器HTML。
        """
        # 快速失败：如果 Playwright 未安装，直接给出明确的安装指引
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "\n" + "=" * 60 + "\n"
                " scrapy-playwright 未安装，无法渲染JS动态页面！\n"
                " 请依次执行以下命令（仅需一次）：\n"
                "    pip install scrapy-playwright\n"
                "    playwright install chromium\n"
                "=" * 60
            )

        url = self.search_url
        self.logger.info(f"起始搜索URL: {url}")

        yield Request(
            url=url,
            meta={
                "playwright": True,                     # 激活 Playwright 渲染
                "playwright_page_methods": [
                    # 等待至少一条职位卡片出现在 DOM 中（最长等待15秒）
                    PageMethod(
                        "wait_for_selector",
                        "div.job-card-wrapper, li.job-card-wrapper, "
                        "div.job-card-body, div.search-job-result",
                        timeout=15000,
                    ),
                ],
            },
            callback=self.parse,
            dont_filter=True,
        )

    # =========================================================================
    #  核心解析：列表页 → Item + 翻页
    # =========================================================================
    def parse(self, response):
        """
        解析职位搜索列表页（Playwright已渲染完成的完整HTML）。

        Yields:
            JobSpiderItem  — 单条招聘记录
            scrapy.Request — 下一页请求（如存在）
        """
        self.logger.info("=" * 60)
        self.logger.info(f"正在解析: {response.url}")

        # ------------------------------------------------------------------
        # 第1步：定位职位卡片容器
        # ------------------------------------------------------------------
        job_cards = response.xpath(
            # 优先选择器链（按BOSS直聘当前主流DOM结构排列）
            '//div[contains(@class, "job-card-wrapper")]'        # 通用包裹
            '| //li[contains(@class, "job-card-wrapper")]'       # 旧版 li 包裹
            '| //div[contains(@class, "job-card-body")]'         # 卡片内容区
            '| //div[contains(@class, "search-job-result")]//li' # 搜索结果列表
            '| //div[contains(@class, "job-list-box")]//li'      # 新版列表容器
        )

        # 极端兜底：如果上面都没命中，尝试匹配任何含 job- 类名的容器
        if not job_cards:
            self.logger.warning(
                "主选择器未命中，尝试宽泛后备选择器..."
            )
            job_cards = response.xpath(
                '//*[contains(@class, "job-card")]'
                '| //li[contains(@class, "job")]'
                '| //div[contains(@class, "job-")]'
            )

            # 若仍然为空，打印页面片段帮助调试
            if not job_cards:
                page_snippet = response.xpath(
                    '//body//text()'
                ).getall()
                snippet_str = "".join(page_snippet).strip()[:500]
                self.logger.error(
                    "仍未匹配到任何职位卡片！"
                    "页面可能触发了安全验证，或DOM结构已重大变更。"
                    f"\n页面文本片段(前500字符):\n{snippet_str}"
                )

        self.logger.info(f"本页匹配到 {len(job_cards)} 条职位卡片")

        # ------------------------------------------------------------------
        # 第2步：逐条提取数据（异常隔离：单条失败不影响其他卡片）
        # ------------------------------------------------------------------
        for idx, card in enumerate(job_cards, start=1):
            try:
                item = self._parse_job_card(card, response.url)
                if item and item.get("job_name"):
                    yield item
                else:
                    self.logger.debug(
                        f"第{idx}条卡片缺少职位名称，已跳过"
                    )
            except Exception as exc:
                # 单条解析异常不中断整个页面
                self.logger.error(
                    f"解析第{idx}条职位卡片时出错: {exc}", exc_info=True
                )
                continue

        # ------------------------------------------------------------------
        # 第3步：翻页
        # ------------------------------------------------------------------
        yield from self._handle_pagination(response)

    # =========================================================================
    #  辅助方法：单卡片字段提取
    # =========================================================================
    @staticmethod
    def _first_text(selector, xpath, default=""):
        """
        安全提取 XPath 匹配的第一个文本节点。

        参数:
            selector:   scrapy.Selector / SelectorList
            xpath:      相对XPath表达式
            default:    提取失败时的默认值

        返回:
            str: 提取到的文本（已 strip），或 default
        """
        result = selector.xpath(xpath).get()
        return result.strip() if result else default

    @staticmethod
    def _pick(selector, *xpaths):
        """
        按顺序尝试多个XPath，返回第一个非空结果。
        所有XPath均未命中则返回空字符串。
        """
        for xp in xpaths:
            val = selector.xpath(xp).get()
            if val and val.strip():
                return val.strip()
        return ""

    def _parse_job_card(self, card, current_url):
        """
        从单个职位卡片的 Selector 中提取全部字段。

        参数:
            card:        单张卡片的 scrapy.Selector
            current_url: 当前列表页URL（用于拼接相对链接）

        返回:
            JobSpiderItem | None
        """
        item = JobSpiderItem()

        # ---- 职位名称 ----
        item["job_name"] = self._pick(
            card,
            './/span[@class="job-name"]/text()',
            './/span[contains(@class, "job-name")]/text()',
            './/a[contains(@class, "job-title")]/text()',
            './/div[contains(@class, "job-title")]//span/text()',
        )

        # ---- 薪资 ----
        item["salary"] = self._pick(
            card,
            './/span[@class="salary"]/text()',
            './/span[contains(@class, "salary")]/text()',
            './/div[contains(@class, "salary")]/text()',
        )

        # ---- 详情链接（补全为绝对URL） ----
        raw_url = self._pick(
            card,
            './/a[contains(@class, "job-card-left")]/@href',
            './/a[contains(@class, "job-title")]/@href',
            './/a[contains(@href, "/job_detail")]/@href',
            './/a[contains(@href, "/job/")]/@href',
        )
        item["job_url"] = urljoin(current_url, raw_url) if raw_url else ""

        # ---- 公司名称 ----
        item["company_name"] = self._pick(
            card,
            './/h3[@class="company-name"]//a/text()',
            './/h3[contains(@class, "company-name")]//text()',
            './/a[contains(@ka, "company")]/text()',
            './/div[contains(@class, "company-text")]//h3/a/text()',
        )

        # ---- 公司行业 & 规模（同一容器） ----
        company_tags = card.xpath(
            './/ul[contains(@class, "company-tag-list")]/li/text()'
        ).getall()
        # 也可从 company-text 区提取
        if not company_tags:
            company_tags = card.xpath(
                './/div[contains(@class, "company-text")]//p/text()'
            ).getall()

        company_tags = [t.strip() for t in company_tags if t.strip()]

        # 启发式：行业通常是第一个不含"人"字的标签；规模包含"人"
        for tag in company_tags:
            if ("人" in tag or "规模" in tag) and not item.get("company_scale"):
                item["company_scale"] = tag
            elif not item.get("industry"):
                item["industry"] = tag

        # 兜底：如果上面没识别出来，按位置分配
        if not item.get("industry") and len(company_tags) >= 1:
            tag0 = company_tags[0]
            if "人" not in tag0 and "规模" not in tag0:
                item["industry"] = tag0
        if not item.get("company_scale") and len(company_tags) >= 2:
            item["company_scale"] = company_tags[-1]

        # ---- 工作城市 & 区域（来自 job-area） ----
        area_text = self._first_text(
            card,
            './/span[@class="job-area"]/text()'
        )
        if not area_text:
            area_text = self._first_text(
                card,
                './/span[contains(@class, "job-area")]/text()'
            )

        # BOSS直聘 area_text 格式示例: "北京·朝阳区"
        if area_text:
            parts = area_text.split("·", 1)
            item["city"] = parts[0].strip()
            item["district"] = parts[1].strip() if len(parts) > 1 else ""
        else:
            item["city"] = ""
            item["district"] = ""

        # ---- 经验 & 学历（来自 job-limit 区域） ----
        limit_texts = card.xpath(
            './/div[contains(@class, "job-limit")]//text()'
            '| .//p[contains(@class, "job-limit")]//text()'
        ).getall()

        # 清理文本
        limit_texts = [t.strip() for t in limit_texts if t.strip()]

        for token in limit_texts:
            # 经验关键词
            if any(kw in token for kw in ["年", "应届", "经验", "毕业生"]):
                if not item.get("experience"):
                    item["experience"] = token
            # 学历关键词
            elif any(kw in token for kw in ["本科", "大专", "硕士", "博士", "学历"]):
                if not item.get("education"):
                    item["education"] = token
            # 城市兜底：如果 area 没提取到城市，尝试从 limit 区域补
            elif not item.get("city") and len(token) >= 2:
                # 粗略匹配：中文城市名通常2-4个字
                item["city"] = token

        # 再次兜底
        if not item.get("experience"):
            item["experience"] = self._pick(
                card,
                './/li[contains(@class, "exp")]/text()',
                './/span[contains(text(), "年")]/text()',
            )
        if not item.get("education"):
            item["education"] = self._pick(
                card,
                './/li[contains(@class, "edu")]/text()',
                './/span[contains(text(), "本科")]/text()',
                './/span[contains(text(), "大专")]/text()',
                './/span[contains(text(), "硕士")]/text()',
                './/span[contains(text(), "博士")]/text()',
            )

        # ---- 招聘者信息 ----
        item["recruiter_name"] = self._first_text(
            card,
            './/div[contains(@class, "info-publis")]//h3/text()'
        )
        item["recruiter_title"] = self._first_text(
            card,
            './/div[contains(@class, "info-publis")]//p/text()'
        )

        # ---- 发布时间 ----
        item["publish_time"] = self._pick(
            card,
            './/span[contains(@class, "time")]/text()',
            './/span[contains(text(), "发布")]/text()',
            './/span[contains(text(), "活跃")]/text()',
        )

        # ---- 若城市仍为空，尝试综合兜底 ----
        if not item["city"]:
            item["city"] = self._first_text(
                card,
                './/span[contains(@class, "location")]/text()'
            )

        return item

    # =========================================================================
    #  辅助方法：翻页
    # =========================================================================
    def _handle_pagination(self, response):
        """
        识别"下一页"按钮并生成下一列表页的 Playwright 请求。

        翻页链：第1页 → 第2页 → ... → 最后一页（next disabled 则停）
        """
        next_url = None

        # 优先级1：class 含 "next" 的 <a> 标签
        next_url = response.xpath(
            '//a[contains(@class, "next")]/@href'
        ).get()

        # 优先级2：文字为"下一页"的链接
        if not next_url:
            next_url = response.xpath(
                '//a[contains(text(), "下一页")]/@href'
                '| //a[contains(text(), "下页")]/@href'
            ).get()

        # 优先级3：翻页器内非 disabled 的 next
        if not next_url:
            next_url = response.xpath(
                '//div[contains(@class, "page") or contains(@class, "pager")]'
                '//a[contains(@class, "next") and '
                'not(contains(@class, "disabled"))]/@href'
            ).get()

        # 优先级4：page 参数递增——根据当前URL推断下一页
        if not next_url:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(response.url)
            qs = parse_qs(parsed.query)
            current_page = int(qs.get("page", ["1"])[0])
            next_page = current_page + 1
            # BOSS直聘搜索结果通常不显示超过10页（约300条），设个硬上限
            if next_page <= 10:
                qs["page"] = [str(next_page)]
                new_query = urlencode(qs, doseq=True)
                next_url = urlunparse(parsed._replace(query=new_query))
                self.logger.info(
                    f"URL推算下一页: 第{current_page}页 → 第{next_page}页"
                )

        if next_url:
            next_url = urljoin(response.url, next_url)
            self.logger.info(f"翻至下一页: {next_url}")

            yield Request(
                url=next_url,
                meta={
                    "playwright": True,             # 翻页同样需要JS渲染
                    "playwright_page_methods": [
                        PageMethod(
                            "wait_for_selector",
                            "div.job-card-wrapper, li.job-card-wrapper, "
                            "div.job-card-body",
                            timeout=15000,
                        ),
                    ],
                },
                callback=self.parse,               # 递归解析
                dont_filter=True,
            )
        else:
            self.logger.info(
                "未找到下一页入口，翻页结束（可能已到达最后一页）。"
            )
            self.logger.info("=" * 60)
