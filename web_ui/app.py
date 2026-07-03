# ============================================================================
# 招聘数据采集与可视化系统 · Flask 后端
# ============================================================================
"""
后端 API 服务，提供：
  1. 页面路由（Dashboard 主页）
  2. 数据 API（职位列表、统计数据、单条详情）
  3. 爬虫控制 API（启动/停止/状态/实时日志 SSE）
  4. 数据导出 API（CSV 下载）

启动方式：
    cd web_ui
    pip install flask
    python app.py
    浏览器打开 http://localhost:5000
"""

# ---- Windows 非ASCII主机名兼容补丁 ----
# Python 3.7 在Windows上调用 socket.getfqdn() 时，若计算机名含中文等
# 非ASCII字符，会抛出 UnicodeDecodeError 导致 Flask/Werkzeug 无法启动。
# 此补丁在模块加载阶段注入，必须在任何网络相关导入之前执行。
import socket as _socket
_original_getfqdn = _socket.getfqdn
def _patched_getfqdn(name=''):
    try:
        return _original_getfqdn(name)
    except UnicodeDecodeError:
        return name if name else 'localhost'
_socket.getfqdn = _patched_getfqdn

import csv
import io
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from queue import Queue

from flask import Flask, Response, jsonify, render_template, request, send_file

# ============================================================================
#  Flask 应用初始化
# ============================================================================
app = Flask(__name__)
app.secret_key = os.urandom(24)

# 项目根目录（JobSpider_CourseDesign/）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRAPY_DIR = PROJECT_ROOT / "job_spider"
OUTPUT_DIR = SCRAPY_DIR / "output"
DEFAULT_CSV = OUTPUT_DIR / "niuke_jobs.csv"

# ============================================================================
#  爬虫进程管理（全局状态）
# ============================================================================
_spider_process = None
_spider_status = {
    "running": False,
    "pid": None,
    "keyword": "",
    "recruit_type": 1,
    "start_time": None,
    "progress": 0,
    "total_pages": 0,
    "message": "",
}
_spider_log_queue = Queue()  # 线程安全的日志队列（SSE 消费）
_spider_log_subscribers = []  # SSE 客户端列表

logger = logging.getLogger(__name__)


# ============================================================================
#  辅助函数：CSV 数据读取与索引
# ============================================================================

def _read_csv(csv_path=None):
    """
    读取 CSV 文件，返回 list[dict]。
    自动处理 utf-8-sig 编码（BOM 头）。
    """
    if csv_path is None:
        csv_path = DEFAULT_CSV
    else:
        csv_path = Path(csv_path)

    if not csv_path.exists():
        return []

    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 清洗每行的字段值
            cleaned = {}
            for k, v in row.items():
                v = (v or "").strip()
                cleaned[k] = v
            rows.append(cleaned)
    return rows


def _parse_salary_range(salary_str):
    """
    解析薪资格式字符串，返回 (min_k, max_k) 或 (None, None)。

    支持格式：
      "16K-23K·15薪"  → (16, 23)
      "8K-16K"        → (8, 16)
      "4K-8K·13薪"    → (4, 8)
      "-" / ""        → (None, None)
    """
    if not salary_str or salary_str == "-":
        return None, None
    # 先去掉 ·N薪 后缀
    clean = re.sub(r"·\d+薪", "", salary_str.strip())
    m = re.match(r"(\d+(?:\.\d+)?)\s*K?\s*-\s*(\d+(?:\.\d+)?)\s*K?", clean, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            pass
    return None, None


def _split_cities(city_str):
    """拆分多城市字段，如 '北京,上海,杭州' → ['北京', '上海', '杭州']"""
    if not city_str or city_str == "-":
        return []
    return [c.strip() for c in city_str.split(",") if c.strip()]


# ============================================================================
#  页面路由
# ============================================================================

@app.route("/")
def index():
    """Dashboard 主页面"""
    return render_template("index.html")


# ============================================================================
#  数据 API
# ============================================================================

@app.route("/api/jobs")
def api_jobs():
    """
    获取职位列表（分页 + 搜索 + 筛选 + 排序）。

    Query params:
      page       — 页码，默认 1
      page_size  — 每页条数，默认 20
      search     — 全局搜索关键词（匹配职位名、公司名）
      city       — 城市筛选
      education  — 学历筛选
      industry   — 行业筛选
      experience — 经验筛选
      sort_by    — 排序字段，默认空
      sort_order — asc / desc，默认 asc
    """
    rows = _read_csv()

    # ---- 筛选 ----
    search = request.args.get("search", "").strip().lower()
    city_filter = request.args.get("city", "").strip()
    education_filter = request.args.get("education", "").strip()
    industry_filter = request.args.get("industry", "").strip()
    experience_filter = request.args.get("experience", "").strip()

    if search:
        rows = [
            r for r in rows
            if search in r.get("job_name", "").lower()
            or search in r.get("company_name", "").lower()
        ]
    if city_filter:
        rows = [r for r in rows if city_filter in r.get("city", "")]
    if education_filter:
        rows = [r for r in rows if r.get("education", "") == education_filter]
    if industry_filter:
        rows = [r for r in rows if r.get("industry", "") == industry_filter]
    if experience_filter:
        rows = [r for r in rows if experience_filter in r.get("experience", "")]

    # ---- 排序 ----
    sort_by = request.args.get("sort_by", "").strip()
    sort_order = request.args.get("sort_order", "asc").strip()
    if sort_by and sort_by in [
        "job_name", "salary", "company_name", "city", "education",
        "experience", "industry", "publish_time",
    ]:
        reverse = sort_order == "desc"
        rows.sort(key=lambda r: r.get(sort_by, ""), reverse=reverse)

    # ---- 分页 ----
    total = len(rows)
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(1, int(request.args.get("page_size", 20))))
    start = (page - 1) * page_size
    end = start + page_size
    page_data = rows[start:end]

    # ---- 构建筛选器选项（基于全部数据） ----
    all_rows = _read_csv()
    cities_set = set()
    educations_set = set()
    industries_set = set()
    experiences_set = set()
    for r in all_rows:
        if r.get("city") and r["city"] != "-":
            for c in _split_cities(r["city"]):
                cities_set.add(c)
        if r.get("education") and r["education"] != "-":
            educations_set.add(r["education"])
        if r.get("industry") and r["industry"] != "-":
            industries_set.add(r["industry"])
        if r.get("experience") and r["experience"] != "-":
            experiences_set.add(r["experience"])

    return jsonify({
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "data": page_data,
        "filters": {
            "cities": sorted(cities_set),
            "educations": sorted(educations_set),
            "industries": sorted(industries_set),
            "experiences": sorted(experiences_set),
        },
    })


@app.route("/api/stats")
def api_stats():
    """
    获取所有聚合统计数据（图表数据源）。

    返回：
      - overview: 总览 KPI
      - salary_stats: 薪资区间分布
      - city_stats: 城市岗位数量 Top 20
      - industry_stats: 行业分布
      - education_stats: 学历要求分布
      - experience_stats: 经验要求分布
      - company_scale_stats: 公司规模分布
      - publish_time_trend: 按月发布趋势
    """
    rows = _read_csv()

    if not rows:
        return jsonify({"overview": {}, "salary_stats": [], "city_stats": [],
                        "industry_stats": [], "education_stats": [],
                        "experience_stats": [], "company_scale_stats": [],
                        "publish_time_trend": []})

    # ---- Overview KPI ----
    total_jobs = len(rows)
    companies = set()
    cities_set = set()
    for r in rows:
        if r.get("company_name") and r["company_name"] != "-":
            companies.add(r["company_name"])
        if r.get("city") and r["city"] != "-":
            for c in _split_cities(r["city"]):
                cities_set.add(c)

    total_companies = len(companies)
    total_cities = len(cities_set)

    # 平均薪资
    salary_mins = []
    salary_maxs = []
    for r in rows:
        mn, mx = _parse_salary_range(r.get("salary", ""))
        if mn is not None and mx is not None:
            salary_mins.append(mn)
            salary_maxs.append(mx)
    avg_salary_min = round(sum(salary_mins) / len(salary_mins), 1) if salary_mins else 0
    avg_salary_max = round(sum(salary_maxs) / len(salary_maxs), 1) if salary_maxs else 0

    # 最新采集时间
    times = [r.get("publish_time", "") for r in rows if r.get("publish_time") and r["publish_time"] != "-"]
    latest_time = max(times) if times else ""
    data_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    overview = {
        "total_jobs": total_jobs,
        "total_companies": total_companies,
        "total_cities": total_cities,
        "avg_salary_min": avg_salary_min,
        "avg_salary_max": avg_salary_max,
        "data_time": data_time,
        "latest_job_time": latest_time,
    }

    # ---- 薪资区间分布 ----
    salary_bins = [
        ("0-8K", 0, 8), ("8-12K", 8, 12), ("12-16K", 12, 16),
        ("16-20K", 16, 20), ("20-25K", 20, 25), ("25-35K", 25, 35),
        ("35K+", 35, float("inf")),
    ]
    salary_stats = []
    for label, lo, hi in salary_bins:
        count = 0
        for r in rows:
            mn, mx = _parse_salary_range(r.get("salary", ""))
            if mn is not None and mx is not None:
                mid = (mn + mx) / 2
                if lo <= mid < hi:
                    count += 1
        salary_stats.append({"name": label, "value": count})

    # ---- 城市分布（拆分多城市） ----
    city_counter = Counter()
    for r in rows:
        cities = _split_cities(r.get("city", ""))
        for c in cities:
            city_counter[c] += 1
    city_stats = [{"name": c, "value": n}
                  for c, n in city_counter.most_common(20)]

    # ---- 行业分布 ----
    industry_counter = Counter()
    for r in rows:
        ind = r.get("industry", "")
        if ind and ind != "-":
            industry_counter[ind] += 1
    industry_stats = [{"name": k, "value": v}
                      for k, v in industry_counter.most_common()]

    # ---- 学历要求分布 ----
    edu_counter = Counter()
    for r in rows:
        edu = r.get("education", "")
        if edu and edu != "-":
            edu_counter[edu] += 1
    education_stats = [{"name": k, "value": v}
                       for k, v in edu_counter.most_common()]

    # ---- 经验要求分布 ----
    exp_counter = Counter()
    for r in rows:
        exp = r.get("experience", "")
        if exp and exp != "-":
            # 归类简化
            if "应届生" in exp or "毕业生" in exp or "在校生" in exp:
                exp_counter["应届生"] += 1
            elif "经验不限" in exp:
                exp_counter["经验不限"] += 1
            elif "1年以下" in exp:
                exp_counter["1年以下"] += 1
            elif "1-3年" in exp:
                exp_counter["1-3年"] += 1
            elif "3-5年" in exp:
                exp_counter["3-5年"] += 1
            elif "5-10年" in exp:
                exp_counter["5-10年"] += 1
            elif "10年以上" in exp:
                exp_counter["10年以上"] += 1
            else:
                exp_counter["其他"] += 1
    experience_stats = [{"name": k, "value": v}
                        for k, v in exp_counter.most_common()]

    # ---- 公司规模分布 ----
    scale_counter = Counter()
    for r in rows:
        scale = r.get("company_scale", "")
        if scale and scale != "-":
            scale_counter[scale] += 1
    company_scale_stats = [{"name": k, "value": v}
                           for k, v in scale_counter.most_common()]

    # ---- 发布时间趋势（按月聚合） ----
    month_counter = Counter()
    for r in rows:
        pt = r.get("publish_time", "")
        if pt and pt != "-" and len(pt) >= 7:
            month = pt[:7]  # YYYY-MM
            month_counter[month] += 1
    month_sorted = sorted(month_counter.items())
    publish_time_trend = [{"name": m, "value": c} for m, c in month_sorted]

    return jsonify({
        "overview": overview,
        "salary_stats": salary_stats,
        "city_stats": city_stats,
        "industry_stats": industry_stats,
        "education_stats": education_stats,
        "experience_stats": experience_stats,
        "company_scale_stats": company_scale_stats,
        "publish_time_trend": publish_time_trend,
    })


@app.route("/api/job/<int:job_index>")
def api_job_detail(job_index):
    """获取单条职位详情（按列表索引）"""
    rows = _read_csv()
    if 0 <= job_index < len(rows):
        return jsonify(rows[job_index])
    return jsonify({"error": "Not found"}), 404


# ============================================================================
#  数据导出 API
# ============================================================================

@app.route("/api/export/csv")
def api_export_csv():
    """下载当前数据为 CSV 文件"""
    if not DEFAULT_CSV.exists():
        return jsonify({"error": "No data file found"}), 404

    return send_file(
        str(DEFAULT_CSV),
        mimetype="text/csv",
        as_attachment=True,
        attachment_filename="niuke_jobs.csv",
    )


# ============================================================================
#  爬虫控制 API
# ============================================================================

def _run_spider(keyword, recruit_type, max_pages):
    """
    在子线程中启动 Scrapy 爬虫进程，并捕获 stdout 写入日志队列。
    """
    global _spider_process, _spider_status, _spider_log_queue

    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "niuke",
        "-a", f"KEYWORD={keyword}",
        "-a", f"RECRUIT_TYPE={recruit_type}",
        "-a", f"MAX_PAGES={max_pages}",
    ]

    _spider_log_queue.put(f"[系统] 启动命令: {' '.join(cmd)}")
    _spider_log_queue.put(f"[系统] 工作目录: {SCRAPY_DIR}")

    try:
        # Windows 需要 CREATE_NEW_PROCESS_GROUP 以便支持终止
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        _spider_process = subprocess.Popen(
            cmd,
            cwd=str(SCRAPY_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )

        _spider_status["pid"] = _spider_process.pid
        _spider_log_queue.put(f"[系统] 爬虫进程已启动 (PID: {_spider_process.pid})")

        # 逐行读取 stdout，推入日志队列
        for line in _spider_process.stdout:
            line = line.rstrip("\n").rstrip("\r")
            if line:
                _spider_log_queue.put(line)
                # 尝试从日志中解析进度信息
                _parse_log_progress(line, max_pages)

        _spider_process.wait()

        if _spider_process.returncode == 0:
            _spider_log_queue.put("[系统] ✅ 爬虫任务完成！")
            _spider_status["progress"] = max_pages
        else:
            _spider_log_queue.put(
                f"[系统] ❌ 爬虫异常退出 (returncode={_spider_process.returncode})"
            )

    except FileNotFoundError:
        _spider_log_queue.put("[系统] ❌ 错误: 未找到 scrapy 命令，请确认已安装 Scrapy")
    except Exception as exc:
        _spider_log_queue.put(f"[系统] ❌ 爬虫运行异常: {exc}")
    finally:
        _spider_process = None
        _spider_status["running"] = False
        _spider_status["pid"] = None
        _spider_log_queue.put("[系统] 爬虫进程已结束。")


def _parse_log_progress(line, max_pages):
    """从 Scrapy 日志行中提取爬取进度信息。"""
    global _spider_status
    # 匹配 "[第N页] 本页X条 | 总计Y条/Z页"
    m = re.search(r"\[第(\d+)页\].*总计\d+条/(\d+)页", line)
    if m:
        current = int(m.group(1))
        total = int(m.group(2))
        _spider_status["progress"] = current
        _spider_status["total_pages"] = total
    # 匹配已达到最大页数
    if "已达到最大爬取页数限制" in line:
        _spider_status["progress"] = max_pages
    if "已爬取全部" in line:
        _spider_status["progress"] = max_pages


@app.route("/api/spider/start", methods=["POST"])
def api_spider_start():
    """
    启动爬虫。

    Request body (JSON):
      { keyword: str, recruit_type: int, max_pages: int }
    """
    global _spider_process, _spider_status, _spider_log_queue

    if _spider_process is not None and _spider_process.poll() is None:
        return jsonify({
            "success": False,
            "message": "爬虫已在运行中，请等待当前任务完成或先停止",
        }), 409

    data = request.get_json(silent=True) or {}
    keyword = data.get("keyword", "Python").strip() or "Python"
    recruit_type = int(data.get("recruit_type", 1))
    max_pages = int(data.get("max_pages", 10))

    # 清空旧的日志
    _spider_log_queue = Queue()

    _spider_status = {
        "running": True,
        "pid": None,
        "keyword": keyword,
        "recruit_type": recruit_type,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "progress": 0,
        "total_pages": max_pages,
        "message": f"正在爬取关键词 '{keyword}'，最大 {max_pages} 页...",
    }

    # 在后台线程中启动爬虫
    thread = threading.Thread(
        target=_run_spider,
        args=(keyword, recruit_type, max_pages),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "message": "爬虫已启动", "keyword": keyword})


@app.route("/api/spider/stop", methods=["POST"])
def api_spider_stop():
    """停止正在运行的爬虫进程。"""
    global _spider_process, _spider_status

    if _spider_process is None or _spider_process.poll() is not None:
        return jsonify({"success": False, "message": "没有正在运行的爬虫进程"})

    try:
        if sys.platform == "win32":
            # Windows: 使用 CTRL_BREAK_EVENT 发送到进程组
            _spider_process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            _spider_process.terminate()

        # 等待最多 5 秒
        try:
            _spider_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _spider_process.kill()

        _spider_status["running"] = False
        _spider_status["message"] = "爬虫已被用户停止"
        _spider_log_queue.put("[系统] ⏹ 爬虫已被用户停止。")

        return jsonify({"success": True, "message": "爬虫已停止"})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/api/spider/status")
def api_spider_status():
    """获取爬虫运行状态。"""
    global _spider_process, _spider_status

    # 检查进程是否仍在运行
    if _spider_process is not None:
        if _spider_process.poll() is not None:
            _spider_status["running"] = False

    return jsonify(_spider_status)


@app.route("/api/spider/logs")
def api_spider_logs():
    """
    SSE (Server-Sent Events) 端点，实时推送爬虫日志。
    """

    def generate():
        # 注册为新客户端
        q = Queue()
        _spider_log_subscribers.append(q)
        try:
            while True:
                # 非阻塞地从全局队列读取并分发给客户端
                while not _spider_log_queue.empty():
                    try:
                        line = _spider_log_queue.get_nowait()
                        yield f"data: {json.dumps({'line': line})}\n\n"
                    except Exception:
                        break

                # 也检查客户端自己的队列
                try:
                    line = q.get(timeout=0.5)
                    yield f"data: {json.dumps({'line': line})}\n\n"
                except Exception:
                    pass

                # 给订阅者发送心跳
                yield ": heartbeat\n\n"

                if not _spider_status["running"] and _spider_log_queue.empty():
                    yield f"data: {json.dumps({'line': '[系统] --- 日志结束 ---', 'done': True})}\n\n"
                    break
        except GeneratorExit:
            pass
        finally:
            if q in _spider_log_subscribers:
                _spider_log_subscribers.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================================
#  启动入口
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  招聘数据采集与可视化系统")
    print(f"  数据文件: {DEFAULT_CSV}")
    print(f"  Scrapy 目录: {SCRAPY_DIR}")
    print("  浏览器打开: http://localhost:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
