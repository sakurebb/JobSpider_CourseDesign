# ============================================================================
# 【合规提示】本代码仅供Python爬虫技术学习交流使用，请勿用于大规模爬取或商业目的。
# 使用本代码前请阅读并遵守BOSS直聘网站的服务协议(https://www.zhipin.com/terms)。
# 不当使用爬虫可能违反相关法律法规，使用者需自行承担一切法律后果。
# ============================================================================

"""
JobSpider 数据字段定义模块

定义BOSS直聘招聘信息的所有数据字段。
字段设计原则：
    1. 优先覆盖列表页可直接提取的内容，减少详情页请求
    2. 字段命名语义化，见名知义
    3. 所有字段均为 scrapy.Field() 类型，底层为Python字典
"""

import scrapy


class JobSpiderItem(scrapy.Item):
    """
    BOSS直聘招聘职位信息 Item 类

    每条 Item 实例代表一条招聘记录，包含列表页可直接提取的全部字段。
    各字段含义及示例值请参见下方注释。
    """

    # ---- 职位基本信息 ----
    # 职位名称，例如："Python后端开发工程师"
    job_name = scrapy.Field()
    # 薪资范围（原始文本），例如："15k-25k"、"20K-40K·16薪"
    salary = scrapy.Field()
    # 职位详情页URL，例如："https://www.zhipin.com/job_detail/xxx.html"
    job_url = scrapy.Field()

    # ---- 公司相关信息 ----
    # 公司名称，例如："字节跳动"
    company_name = scrapy.Field()
    # 公司所属行业，例如："移动互联网"、"计算机软件"
    industry = scrapy.Field()
    # 公司规模，例如："500-999人"、"10000人以上"
    company_scale = scrapy.Field()

    # ---- 工作地点信息 ----
    # 工作城市，例如："北京"、"上海"、"深圳"
    city = scrapy.Field()
    # 工作区域/具体地点，例如："朝阳区·望京"、"浦东新区·张江"
    district = scrapy.Field()

    # ---- 职位要求信息 ----
    # 经验要求，例如："3-5年"、"经验不限"、"应届生"
    experience = scrapy.Field()
    # 学历要求，例如："本科"、"硕士"、"大专"
    education = scrapy.Field()

    # ---- 补充字段（列表页可能提取的额外信息） ----
    # 招聘者姓名/HR昵称，例如："王经理"
    recruiter_name = scrapy.Field()
    # 招聘者职位，例如："HR"、"技术总监"
    recruiter_title = scrapy.Field()
    # 发布日期/刷新时间，例如："刚刚活跃"、"3天内发布"
    publish_time = scrapy.Field()
