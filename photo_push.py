import requests
import json
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup
import git

# ========== 配置区 ==========
CUBOX_API = "https://cubox.pro/c/api/save/asvs88IwMsn"
TARGET_NUM = 5
SEND_INTERVAL = 3  # 每条间隔3秒防限流
BLACKLIST_FILE = "pushed_urls.json"
FOLDER_NAME = "每日艺术摄影合集"
TAG_LIST = ["艺术摄影", "海外摄影项目", "自动每日推送"]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
# ============================

def load_blacklist():
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_blacklist(black_set):
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(list(black_set), f, ensure_ascii=False, indent=2)

def push_single_item(work_info):
    desc_block = f"""作品详细介绍：
{work_info['work_desc']}

艺术家详细介绍：
{work_info['artist_intro']}

艺术家个人网站：{work_info['artist_site'] if work_info['artist_site'] else '暂无独立官网'}

该作品的链接：{work_info['work_url']}

该艺术家的其他作品：
{chr(10).join(work_info['other_works']) if work_info['other_works'] else '暂无其他作品收录'}
"""
    payload = {
        "type": "url",
        "content": work_info['work_url'],
        "title": work_info['work_title'],
        "description": desc_block.strip(),
        "tags": TAG_LIST,
        "folder": FOLDER_NAME
    }
    try:
        resp = requests.post(
            CUBOX_API,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=12
        )
        res_json = resp.json()
        if res_json.get("code") == 200:
            return True, f"✅ {work_info['work_title']} 推送成功"
        else:
            return False, f"❌ {work_info['work_title']} 失败，返回：{res_json}"
    except Exception as e:
        return False, f"⚠️ {work_info['work_title']} 请求异常：{str(e)}"

# ========== Aint-Bad 解析 ==========
def parse_aintbad_detail(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.find("h1")
        if not h1:
            return None
        artist_name = h1.get_text(strip=True)
        em_tag = soup.find("em")
        artist_intro = em_tag.get_text(strip=True) if em_tag else "暂无艺术家简介"

        work_intro = ""
        for p in soup.find_all("p"):
            txt = p.get_text(strip=True)
            if not txt or txt == artist_intro:
                continue
            if "To view more of" in txt:
                break
            work_intro += txt + "\n"

        artist_site = None
        for a in soup.find_all("a", href=True):
            parent_txt = a.parent.get_text() if a.parent else ""
            if "To view more of" in parent_txt and "website" in parent_txt:
                artist_site = a["href"]
                break

        other_works = []
        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True) == artist_name and "/tag/" in a["href"]:
                other_works.append(a["href"])
                break

        return {
            "work_title": f"{artist_name} - Aint-Bad 专题",
            "work_desc": work_intro.strip(),
            "artist_intro": artist_intro,
            "artist_site": artist_site,
            "work_url": url,
            "other_works": other_works,
            "source": "Aint-Bad"
        }
    except Exception:
        return None

def crawl_aintbad(blacklist):
    works_pool = []
    try:
        res = requests.get("https://aint-bad.com", headers=HEADERS, timeout=12)
        soup = BeautifulSoup(res.text, "html.parser")
        for h2 in soup.find_all("h2"):
            a = h2.find("a", href=True)
            if not a:
                continue
            link = a["href"]
            if not link.startswith("http"):
                link = "https://aint-bad.com" + link
            if link in blacklist:
                continue
            item = parse_aintbad_detail(link)
            if item:
                works_pool.append(item)
    except Exception as e:
        print(f"Aint-Bad 抓取失败: {e}")
    return works_pool

# ========== IGNANT Photography 解析 ==========
def parse_ignant_detail(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 提取标题
        h1 = soup.find("h1")
        if not h1:
            return None
        title = h1.get_text(separator=" ", strip=True)
        
        # 提取艺术家名字
        artist_name = ""
        artist_site = None
        name_label = soup.find(string=lambda t: t and t.strip() == "Name")
        if name_label:
            name_parent = name_label.find_parent()
            if name_parent:
                artist_link = name_parent.find_next("a")
                if artist_link:
                    artist_name = artist_link.get_text(strip=True)
                    artist_site = artist_link.get("href")
        
        # 提取正文
        work_intro = ""
        article_content = soup.find("article") or soup
        for p in article_content.find_all("p"):
            txt = p.get_text(strip=True)
            if not txt or txt.startswith("All images ©"):
                continue
            if len(txt) < 20:
                continue
            work_intro += txt + "\n"
            if len(work_intro) > 1500:
                break
        
        # 提取相关作品
        other_works = []
        related = soup.find(string=lambda t: t and "Related Posts" in t)
        if related:
            related_section = related.find_parent()
            if related_section:
                for a in related_section.find_all_next("a", href=True, limit=5):
                    href = a.get("href")
                    if href and href.startswith("http") and "ignant.com" in href:
                        other_works.append(href)
        
        # 艺术家简介（从正文中提取第一段包含艺术家名字的）
        artist_intro = f"{artist_name}，当代摄影师，作品刊载于 IGNANT 等国际艺术设计媒体。"
        if work_intro:
            first_para = work_intro.split("\n")[0]
            if artist_name and artist_name in first_para:
                artist_intro = first_para[:300]
        
        return {
            "work_title": f"{title} - {artist_name}" if artist_name else title,
            "work_desc": work_intro.strip(),
            "artist_intro": artist_intro,
            "artist_site": artist_site,
            "work_url": url,
            "other_works": other_works[:3],
            "source": "IGNANT"
        }
    except Exception as e:
        print(f"IGNANT 详情解析失败 {url}: {e}")
        return None

def crawl_ignant(blacklist):
    works_pool = []
    try:
        res = requests.get("https://www.ignant.com/category/photography/", headers=HEADERS, timeout=12)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 提取所有文章链接
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # IGNANT 文章链接格式：/2020/11/03/xxx/
            if href and "/category/" not in href and "/tag/" not in href:
                # 检查是否是文章链接（包含年份路径）
                import re
                if re.search(r'/\d{4}/\d{2}/\d{2}/', href):
                    if not href.startswith("http"):
                        href = "https://www.ignant.com" + href
                    if href not in links and href not in blacklist:
                        links.append(href)
        
        # 只解析前10条，避免耗时太长
        for link in links[:10]:
            item = parse_ignant_detail(link)
            if item:
                works_pool.append(item)
            time.sleep(0.5)  # 礼貌间隔
    except Exception as e:
        print(f"IGNANT 抓取失败: {e}")
    return works_pool

# ========== Amber Hakim 个人站解析 ==========
def crawl_amberhakim(blacklist):
    works_pool = []
    try:
        res = requests.get("https://amberhakim.com", headers=HEADERS, timeout=12)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 提取所有项目链接
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href and "/project/" in href:
                if not href.startswith("http"):
                    href = "https://amberhakim.com" + href
                if href in blacklist:
                    continue
                # 简单解析
                title = a.get_text(strip=True) or "Amber Hakim 摄影项目"
                works_pool.append({
                    "work_title": f"{title} - Amber Hakim",
                    "work_desc": "Amber Hakim 的个人摄影项目，以感性和独特的视觉语言著称，涵盖个人叙事和音乐领域的创作。",
                    "artist_intro": "Amber Hakim，当代摄影师，以其感性和视觉独特的摄影项目闻名，作品涵盖个人叙事和音乐领域，风格细腻而富有情绪张力。",
                    "artist_site": "https://amberhakim.com",
                    "work_url": href,
                    "other_works": ["https://amberhakim.com/projects"],
                    "source": "Amber Hakim"
                })
    except Exception as e:
        print(f"Amber Hakim 抓取失败: {e}")
    return works_pool

# ========== 主函数 ==========
def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"====== 每日摄影推送任务启动 {run_time} ======")

    # 拉取最新代码
    repo = git.Repo(os.getcwd())
    repo.remotes.origin.pull()

    blacklist = load_blacklist()
    print(f"当前黑名单数量：{len(blacklist)} 条")

    # 多站点抓取
    all_candidates = []
    
    print("正在抓取 Aint-Bad...")
    all_candidates.extend(crawl_aintbad(blacklist))
    
    print("正在抓取 IGNANT Photography...")
    all_candidates.extend(crawl_ignant(blacklist))
    
    print("正在抓取 Amber Hakim...")
    all_candidates.extend(crawl_amberhakim(blacklist))

    # 去重
    unique_list = []
    seen_url = set()
    for item in all_candidates:
        if item["work_url"] not in seen_url:
            seen_url.add(item["work_url"])
            unique_list.append(item)

    print(f"共抓取到 {len(unique_list)} 条未推送内容")

    # 取前 N 条推送
    send_batch = unique_list[:TARGET_NUM]
    
    # 如果不够3条，打印警告（后续可扩展归档页兜底）
    if len(send_batch) < 3:
        print(f"⚠️ 警告：仅抓取到 {len(send_batch)} 条新内容，不足3条")
    
    print(f"本次将推送 {len(send_batch)} 条内容")

    # 逐条推送，间隔3秒
    success_cnt = 0
    log_records = []
    for idx, work in enumerate(send_batch):
        ok, msg = push_single_item(work)
        log_records.append(f"[{work['source']}] {msg}")
        if ok:
            success_cnt += 1
            blacklist.add(work["work_url"])
        # 不是最后一条就间隔
        if idx != len(send_batch) - 1:
            time.sleep(SEND_INTERVAL)

    # 保存黑名单并提交回仓库
    save_blacklist(blacklist)
    repo.git.add(BLACKLIST_FILE)
    commit_msg = f"Daily push: {datetime.now().strftime('%Y-%m-%d')}, pushed {success_cnt} items"
    repo.index.commit(commit_msg)
    repo.remotes.origin.push()

    # 汇总输出
    summary = f"""
【每日艺术摄影推送完成通知】
执行时间：{run_time}
抓取来源：Aint-Bad、IGNANT Photography、Amber Hakim
待推送总数：{len(send_batch)} 条
推送成功：{success_cnt} 条
单条间隔：{SEND_INTERVAL}秒
存放文件夹：每日艺术摄影合集

明细日志：
"""
    for line in log_records:
        summary += line + "\n"
    print(summary)

if __name__ == "__main__":
    main()
