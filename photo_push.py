import requests
import json
import os
import time
import re
from datetime import datetime
from bs4 import BeautifulSoup
import git

# ========== 配置区 ==========
CUBOX_API = "https://cubox.pro/c/api/save/asvs88IwMsn"
TARGET_NUM = 5
MIN_NUM = 3  # 至少要凑够这么多条
SEND_INTERVAL = 3
BLACKLIST_FILE = "pushed_urls.json"
FOLDER_NAME = "每日艺术摄影合集"
TAG_LIST = ["艺术摄影", "海外摄影项目", "自动每日推送"]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
MAX_PAGES_PER_SITE = 3  # 每个网站最多翻几页（避免爬太久）
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

# ========== 通用：从页面提取文章链接 ==========
def extract_links_from_page(soup, base_url, blacklist, pattern=None):
    """从页面中提取所有符合条件的文章链接"""
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        if not href.startswith("http"):
            href = base_url.rstrip("/") + href
        # 去重 + 黑名单过滤
        if href in links or href in blacklist:
            continue
        # 正则过滤（可选）
        if pattern and not re.search(pattern, href):
            continue
        # 排除分类页、标签页等非文章页
        if any(x in href for x in ["/category/", "/tag/", "/page/", "#"]):
            continue
        links.append(href)
    return links

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

def crawl_aintbad(blacklist, target_count):
    """Aint-Bad 多页抓取，凑够 target_count 条就停"""
    works_pool = []
    found_urls = set()
    
    for page in range(1, MAX_PAGES_PER_SITE + 1):
        if len(works_pool) >= target_count:
            break
        try:
            url = f"https://aint-bad.com/page/{page}/" if page > 1 else "https://aint-bad.com"
            print(f"  抓取 Aint-Bad 第 {page} 页...")
            res = requests.get(url, headers=HEADERS, timeout=12)
            if res.status_code != 200:
                break
            soup = BeautifulSoup(res.text, "html.parser")
            
            page_links = []
            for h2 in soup.find_all("h2"):
                a = h2.find("a", href=True)
                if not a:
                    continue
                link = a["href"]
                if not link.startswith("http"):
                    link = "https://aint-bad.com" + link
                if link in blacklist or link in found_urls:
                    continue
                page_links.append(link)
                found_urls.add(link)
            
            print(f"    本页找到 {len(page_links)} 条新链接")
            
            for link in page_links:
                if len(works_pool) >= target_count:
                    break
                item = parse_aintbad_detail(link)
                if item:
                    works_pool.append(item)
                time.sleep(0.3)
        except Exception as e:
            print(f"  Aint-Bad 第 {page} 页抓取失败: {e}")
            break
    
    print(f"  Aint-Bad 共获取 {len(works_pool)} 条有效内容")
    return works_pool

# ========== IGNANT Photography 解析 ==========
def parse_ignant_detail(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        
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
        
        # 相关作品
        other_works = []
        related = soup.find(string=lambda t: t and "Related Posts" in t)
        if related:
            related_section = related.find_parent()
            if related_section:
                for a in related_section.find_all_next("a", href=True, limit=5):
                    href = a.get("href")
                    if href and href.startswith("http") and "ignant.com" in href:
                        other_works.append(href)
        
        artist_intro = f"{artist_name}，当代摄影师，作品刊载于 IGNANT 等国际艺术设计媒体。"
        if work_intro and artist_name:
            first_para = work_intro.split("\n")[0]
            if artist_name in first_para:
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
        return None

def crawl_ignant(blacklist, target_count):
    """IGNANT 多分类 + 多页抓取，凑够 target_count 条就停"""
    works_pool = []
    found_urls = set()
    
    # 优先抓主分类，再抓子分类
    categories = [
        "/category/photography/",           # 主分类（最新）
        "/category/photography/conceptual/", # 观念摄影
        "/category/photography/documentary/", # 纪实摄影
        "/category/photography/landscape/",  # 风景摄影
        "/category/photography/travel/",     # 旅行摄影
    ]
    
    for cat in categories:
        if len(works_pool) >= target_count:
            break
        
        for page in range(1, MAX_PAGES_PER_SITE + 1):
            if len(works_pool) >= target_count:
                break
            try:
                url = f"https://www.ignant.com{cat}page/{page}/" if page > 1 else f"https://www.ignant.com{cat}"
                print(f"  抓取 IGNANT {cat} 第 {page} 页...")
                res = requests.get(url, headers=HEADERS, timeout=12)
                if res.status_code != 200:
                    break
                soup = BeautifulSoup(res.text, "html.parser")
                
                # 提取文章链接
                page_links = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if not href:
                        continue
                    # IGNANT 文章格式：/2020/11/03/xxx/
                    if not re.search(r'/\d{4}/\d{2}/\d{2}/', href):
                        continue
                    if not href.startswith("http"):
                        href = "https://www.ignant.com" + href
                    if href in blacklist or href in found_urls:
                        continue
                    # 排除非摄影分类的文章
                    if "/category/" in href or "/tag/" in href:
                        continue
                    page_links.append(href)
                    found_urls.add(href)
                
                print(f"    本页找到 {len(page_links)} 条新链接")
                
                for link in page_links:
                    if len(works_pool) >= target_count:
                        break
                    item = parse_ignant_detail(link)
                    if item:
                        works_pool.append(item)
                    time.sleep(0.3)
            except Exception as e:
                print(f"  IGNANT {cat} 第 {page} 页抓取失败: {e}")
                break
    
    print(f"  IGNANT 共获取 {len(works_pool)} 条有效内容")
    return works_pool

# ========== Amber Hakim 个人站 ==========
def crawl_amberhakim(blacklist):
    works_pool = []
    try:
        print("  抓取 Amber Hakim...")
        res = requests.get("https://amberhakim.com", headers=HEADERS, timeout=12)
        soup = BeautifulSoup(res.text, "html.parser")
        
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href and "/project/" in href:
                if not href.startswith("http"):
                    href = "https://amberhakim.com" + href
                if href in blacklist:
                    continue
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
        print(f"  Amber Hakim 抓取失败: {e}")
    
    print(f"  Amber Hakim 共获取 {len(works_pool)} 条有效内容")
    return works_pool

# ========== 主函数 ==========
def main():
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"====== 每日摄影推送任务启动 {run_time} ======")

    # 拉取最新代码
    repo = git.Repo(os.getcwd())
    repo.remotes.origin.pull()

    blacklist = load_blacklist()
    print(f"当前黑名单（已推送）数量：{len(blacklist)} 条")

    all_candidates = []
    
    # 按优先级依次抓取，凑够 TARGET_NUM 就停
    remaining = TARGET_NUM
    
    print("\n【1/3】抓取 Aint-Bad...")
    aintbad_works = crawl_aintbad(blacklist, remaining)
    all_candidates.extend(aintbad_works)
    remaining = max(0, TARGET_NUM - len(all_candidates))
    
    if remaining > 0:
        print(f"\n【2/3】抓取 IGNANT Photography（还需 {remaining} 条）...")
        ignant_works = crawl_ignant(blacklist, remaining)
        all_candidates.extend(ignant_works)
        remaining = max(0, TARGET_NUM - len(all_candidates))
    
    if remaining > 0:
        print(f"\n【3/3】抓取 Amber Hakim（还需 {remaining} 条）...")
        amber_works = crawl_amberhakim(blacklist)
        all_candidates.extend(amber_works)
    
    # 最终去重保险
    unique_list = []
    seen_url = set()
    for item in all_candidates:
        if item["work_url"] not in seen_url:
            seen_url.add(item["work_url"])
            unique_list.append(item)

    print(f"\n====== 抓取汇总 ======")
    print(f"共获取 {len(unique_list)} 条未推送内容")

    send_batch = unique_list[:TARGET_NUM]
    
    if len(send_batch) < MIN_NUM:
        print(f"⚠️ 警告：仅获取到 {len(send_batch)} 条内容，不足最低要求 {MIN_NUM} 条")
        print("建议：增加更多信源网站，或调大 MAX_PAGES_PER_SITE")
    
    print(f"本次将推送 {len(send_batch)} 条内容")

    # 逐条推送
    success_cnt = 0
    log_records = []
    for idx, work in enumerate(send_batch):
        ok, msg = push_single_item(work)
        log_records.append(f"[{work['source']}] {msg}")
        if ok:
            success_cnt += 1
            blacklist.add(work["work_url"])
        if idx != len(send_batch) - 1:
            time.sleep(SEND_INTERVAL)

    # 保存黑名单
    save_blacklist(blacklist)
    repo.git.add(BLACKLIST_FILE)
    commit_msg = f"Daily push: {datetime.now().strftime('%Y-%m-%d')}, pushed {success_cnt} items"
    repo.index.commit(commit_msg)
    repo.remotes.origin.push()

    # 汇总
    summary = f"""
【每日艺术摄影推送完成通知】
执行时间：{run_time}
抓取来源：Aint-Bad、IGNANT Photography、Amber Hakim
抓取策略：优先最新，不够则自动翻页挖历史
已推送历史总数：{len(blacklist)} 条
本次推送：{success_cnt}/{len(send_batch)} 条
单条间隔：{SEND_INTERVAL}秒
存放文件夹：每日艺术摄影合集

明细日志：
"""
    for line in log_records:
        summary += line + "\n"
    print(summary)

if __name__ == "__main__":
    main()
