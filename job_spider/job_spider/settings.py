# ============================================================================
# 【合规声明】本代码仅供Python爬虫技术课程设计学习交流使用。
# 严禁用于任何商业目的或大规模采集，使用者须自行遵守BOSS直聘网站服务协议
# (https://www.zhipin.com/terms) 及相关法律法规，自行承担不当使用的法律后果。
# ============================================================================

"""
JobSpider · 全局配置文件 (兼容 Scrapy 2.16)

=============================================================================
本文件配置了爬虫项目的全部全局行为，涵盖：
    1. 爬取礼貌性 — 延迟、并发、自动限速
    2. 反爬对抗 — robots协议、请求头伪装
    3. 动态渲染 — Playwright 集成（解决BOSS直聘SPA拿不到数据问题）
    4. 数据处理 — 自定义管道激活
    5. 日志 & 调试 — INFO级别输出，方便课程设计学习追踪

新手提示：
    每个配置项均附带中文说明，直接按注释修改即可。
    修改后运行 scrapy crawl boss_zhipin 无需重启IDE。
=============================================================================
"""

# ============================================================================
#  一、基础标识
# ============================================================================

# 爬虫项目名称（scrapy startproject 时生成，无需修改）
BOT_NAME = "job_spider"

# 爬虫模块搜索路径 — Scrapy 从这里发现 Spider 类
SPIDER_MODULES = ["job_spider.spiders"]
NEWSPIDER_MODULE = "job_spider.spiders"


# ============================================================================
#  二、爬取礼貌性配置
# ============================================================================

# ---- robots.txt 协议 ----
# 设为 False：BOSS直聘 robots.txt 通常会禁止所有爬虫，学习用途下忽略
# ⚠️  请务必控制爬取频率，尊重目标服务器
ROBOTSTXT_OBEY = False

# ---- 请求延迟（秒） ----
# 每两次请求之间的固定等待时间。设为 2 秒，温和爬取、降低封IP风险
# 如果运行时频繁触发验证码，可临时上调至 3~5 秒
DOWNLOAD_DELAY = 2

# ---- 单域名并发数 ----
# 对 zhipin.com 同时只保持 1 个活跃请求，最友善的爬取策略
CONCURRENT_REQUESTS_PER_DOMAIN = 1

# ---- 全局并发数（保留默认，由单域名限制实际生效） ----
# CONCURRENT_REQUESTS = 16  （默认值，无需显式设置）


# ============================================================================
#  三、请求头伪装（模拟 Chrome 浏览器）
# ============================================================================

# 这是最基础的反爬手段：如果不设 User-Agent，Scrapy 默认值 "Scrapy/2.x"
# 会被绝大多数网站直接拒绝。以下伪装为 Windows Chrome 125 正常用户。
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
}


# ============================================================================
#  四、Playwright 动态渲染配置（核心：解决 SPA 页面无数据问题）
# ============================================================================

# ---- 浏览器类型 ----
# 使用 Chromium（Chrome 的开源版本），与BOSS直聘兼容性最好
PLAYWRIGHT_BROWSER_TYPE = "chromium"

# ---- 启动参数：隐藏自动化痕迹 ----
# BOSS直聘会检测 navigator.webdriver 等自动化标记，
# 以下参数可大幅降低被识别为自动化工具的概率
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,  # True = 无头模式（后台运行，不弹浏览器窗口）
    "args": [
        "--disable-blink-features=AutomationControlled",  # 隐藏 WebDriver 标记
        "--no-sandbox",                                    # Linux 环境必需
        "--disable-dev-shm-usage",                         # 避免共享内存不足
        "--disable-gpu",                                   # 无头模式建议关闭GPU
        "--disable-infobars",                              # 隐藏"Chrome正在受自动化控制"提示条
    ],
}

# ---- 默认上下文参数 ----
# 模拟真实浏览器的视口尺寸，避免因窗口太小被识别
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000  # 页面加载超时（毫秒）
PLAYWRIGHT_CONTEXTS = {
    "default": {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }
}

# ---- 将 http/https 流量路由到 Playwright 下载处理器 ----
# 任何带 {'playwright': True} meta 的 Request 会自动使用 Playwright 渲染
# 未带该标记的 Request 仍走默认下载器，二者可共存
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

# ---- Playwright 请求并发数 ----
# 限制同时打开的浏览器页面数，保护本机资源和目标服务器
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 1

# ---- 意外关闭处理 ----
# 当浏览器意外崩溃或无法启动时，强制中止（设为 True 便于快速暴露配置问题）
PLAYWRIGHT_ABORT_REQUEST = True


# ============================================================================
#  五、Scrapy 信号与错误处理
# ============================================================================

# 当出现 DNS 查询失败、连接超时等错误时，是否继续后续请求
# 保持默认 True（不因个别请求失败而终止全部爬取）
# SCHEDULER_DEBUG = False


# ============================================================================
#  六、Item 管道配置
# ============================================================================

# 激活自定义 CSV 导出管道，数字 300 为优先级（0-1000，越小越先执行）
ITEM_PIPELINES = {
    "job_spider.pipelines.CsvExportPipeline": 300,
}


# ============================================================================
#  七、自动限速（AutoThrottle）
# ============================================================================

# 根据服务器响应速度自动调整下载延迟，实际生产环境中推荐开启
# 学习阶段关闭，保持行为可预测便于调试
AUTOTHROTTLE_ENABLED = False

# 若开启自动限速，以下为参考参数（当前不生效）：
# AUTOTHROTTLE_START_DELAY       = 5    # 初始延迟（秒）
# AUTOTHROTTLE_MAX_DELAY         = 60   # 最大延迟（秒）
# AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0  # 目标并发数


# ============================================================================
#  八、HTTP 缓存（开发调试用）
# ============================================================================

# 调试阶段建议开启，避免重复请求浪费时间和IP资源
# 正式采集前务必关闭，否则可能抓到过期数据
# HTTPCACHE_ENABLED           = True
# HTTPCACHE_EXPIRATION_SECS   = 0          # 0 = 永不过期
# HTTPCACHE_DIR               = "httpcache"
# HTTPCACHE_IGNORE_HTTP_CODES = []         # 不缓存的 HTTP 状态码列表


# ============================================================================
#  九、日志配置
# ============================================================================

# INFO: 显示关键信息（请求URL、解析数量、翻页链接、文件创建/关闭）
# 更详细用 DEBUG，更简洁用 WARNING
LOG_LEVEL = "INFO"

# 日志文件输出（留空 = 仅控制台；填入路径 = 同时写入文件）
# LOG_FILE = "scrapy.log"

# 日志格式（标准 scrapy 格式，含时间戳和日志级别）
# LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


# ============================================================================
#  十、其他关键配置
# ============================================================================

# 导出文件编码（CSV 由 pipeline 自行控制编码，此值用于 JSON/XML feed）
FEED_EXPORT_ENCODING = "utf-8"

# 请求重试次数（保持默认 2 次，兼顾容错与效率）
# RETRY_TIMES = 2

# 下载超时（秒），默认 180 秒对 Playwright 渲染的页面已足够
# DOWNLOAD_TIMEOUT = 180

# 重试的 HTTP 状态码（默认值已包含 500/502/503/504/408）
# RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]

# ---- 禁用未使用中间件的警告 ----
# 由于我们仅在 boss_zhipin 爬虫中启用 Playwright，未在全局 DOWNLOADER_MIDDLEWARES
# 中配置新的中间件，此设置可避免 Scrapy 打印大量中间件冲突警告
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,
    "scrapy.downloadermiddlewares.redirect.RedirectMiddleware": 600,
}
