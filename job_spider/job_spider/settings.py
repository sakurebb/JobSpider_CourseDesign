# ============================================================================
# 【合规声明】本代码仅供Python爬虫技术课程设计学习交流使用。
# 严禁用于任何商业目的或大规模采集，使用者须自行遵守牛客网服务协议
# (https://www.nowcoder.com/agreement) 及相关法律法规，自行承担不当使用
# 的法律后果。
# ============================================================================

"""
JobSpider · 全局配置文件 (兼容 Scrapy 2.9+)

=============================================================================
本文件配置了爬虫项目的全部全局行为，涵盖：
    1. 爬取礼貌性 — 延迟、并发
    2. 反爬对抗 — robots协议、请求头伪装
    3. 数据处理 — 自定义管道激活
    4. 日志 & 调试 — INFO级别输出，方便课程设计学习追踪

新手提示：
    每个配置项均附带中文说明，直接按注释修改即可。
    修改后运行 scrapy crawl niuke 无需重启IDE。
=============================================================================
"""

import platform as _platform

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
# 设为 False：大多数招聘网站 robots.txt 会禁止爬虫，学习用途下忽略
# ⚠️  请务必控制爬取频率，尊重目标服务器
ROBOTSTXT_OBEY = False

# ---- 请求延迟（秒） ----
# 每两次请求之间的固定等待时间。设为 1 秒，温和爬取
DOWNLOAD_DELAY = 1

# ---- 单域名并发数 ----
# 对 nowcoder.com 同时只保持 1 个活跃请求，最友善的爬取策略
CONCURRENT_REQUESTS_PER_DOMAIN = 1

# ---- 全局并发数（保留默认，由单域名限制实际生效） ----
# CONCURRENT_REQUESTS = 16  （默认值，无需显式设置）


# ============================================================================
#  三、请求头伪装（模拟 Chrome 浏览器，基础配置）
# ============================================================================

# 仅配置基础 User-Agent，牛客网API对请求头校验宽松，
# 无需复杂的反自动化检测参数伪装
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}


# ============================================================================
#  四、Item 管道配置
# ============================================================================

# 激活自定义 CSV 导出管道，数字 300 为优先级（0-1000，越小越先执行）
ITEM_PIPELINES = {
    "job_spider.pipelines.CsvExportPipeline": 300,
}


# ============================================================================
#  五、自动限速（AutoThrottle）— 学习阶段关闭
# ============================================================================

# 根据服务器响应速度自动调整下载延迟，实际生产环境中推荐开启
# 学习阶段关闭，保持行为可预测便于调试
AUTOTHROTTLE_ENABLED = False

# 若开启自动限速，以下为参考参数（当前不生效）：
# AUTOTHROTTLE_START_DELAY       = 5    # 初始延迟（秒）
# AUTOTHROTTLE_MAX_DELAY         = 60   # 最大延迟（秒）
# AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0  # 目标并发数


# ============================================================================
#  六、HTTP 缓存（开发调试用）
# ============================================================================

# 调试阶段建议开启，避免重复请求浪费时间和IP资源
# 正式采集前务必关闭，否则可能抓到过期数据
# HTTPCACHE_ENABLED           = True
# HTTPCACHE_EXPIRATION_SECS   = 0          # 0 = 永不过期
# HTTPCACHE_DIR               = "httpcache"
# HTTPCACHE_IGNORE_HTTP_CODES = []         # 不缓存的 HTTP 状态码列表


# ============================================================================
#  七、日志配置
# ============================================================================

# INFO: 显示关键信息（请求URL、解析数量、翻页、文件创建/关闭）
# 更详细用 DEBUG，更简洁用 WARNING
LOG_LEVEL = "INFO"

# 日志文件输出（留空 = 仅控制台；填入路径 = 同时写入文件）
# LOG_FILE = "scrapy.log"

# 日志格式（标准 scrapy 格式，含时间戳和日志级别）
# LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


# ============================================================================
#  八、其他关键配置
# ============================================================================

# ---- 请求指纹器实现版本 ----
# 设为 "2.7" 消除 Scrapy 2.9+ 的 REQUEST_FINGERPRINTER_IMPLEMENTATION 弃用警告
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

# 导出文件编码（CSV 由 pipeline 自行控制编码，此值用于 JSON/XML feed）
FEED_EXPORT_ENCODING = "utf-8"

# 请求重试次数（保持默认 2 次，兼顾容错与效率）
# RETRY_TIMES = 2

# 下载超时（秒），纯静态请求无需太长超时
DOWNLOAD_TIMEOUT = 30

# 重试的 HTTP 状态码（默认值已包含 500/502/503/504/408）
# RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]


# ============================================================================
#  九、Windows 平台 Twisted 反应器兼容补丁
# ============================================================================
# 问题背景：
#   Scrapy 启动时会调用 ossignal.install_shutdown_handlers() 注册系统信号
#   处理器（用于 Ctrl+C 优雅退出），该函数内部调用 reactor._handleSignals()。
#   但 Windows 平台所有 Twisted 反应器（SelectReactor / IOCPReactor 等）均
#   未实现该方法，导致爬虫启动瞬间抛出 AttributeError 崩溃。
#
# 修复策略（双层防护）：
#   第1层 — 给默认反应器注入 _handleSignals 空方法
#           settings.py 模块加载时默认反应器已安装，提前打上空补丁
#   第2层 — MonkeyPatch ossignal.install_shutdown_handlers
#           捕获 AttributeError 降级为日志警告，不中断爬虫启动
# ============================================================================

if _platform.system() == "Windows":
    # ----- 第1层：为默认反应器注入 _handleSignals -----
    try:
        from twisted.internet import reactor as _reactor
        if not hasattr(_reactor, "_handleSignals"):
            _reactor._handleSignals = lambda: None
    except Exception:
        pass

    # ----- 第2层：MonkeyPatch ossignal，防止后续反应器切换再次触发 -----
    try:
        from scrapy.utils import ossignal as _ossignal

        _original_install = _ossignal.install_shutdown_handlers

        def _patched_install_shutdown_handlers(function, override_sigint=True):
            """Windows安全版信号处理器安装 — 捕获AttributeError静默降级。"""
            try:
                _original_install(function, override_sigint)
            except AttributeError:
                # Windows反应器不支持POSIX信号，跳过注册
                # Ctrl+C退出仍可通过键盘中断正常触发（稍慢但可用）
                pass

        _ossignal.install_shutdown_handlers = _patched_install_shutdown_handlers
    except Exception:
        pass
