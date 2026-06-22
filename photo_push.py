import requests
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import git

# ========== 配置 ==========
CUBOX_API = "https://cubox.pro/c/api/save/asvs88IwMsn"
TARGET_NUM = 5
BLACKLIST_FILE = "pushed_urls.json"
FOLDER_NAME = "每日艺术摄影合集"
TAG_LIST = ["艺术摄影", "海外摄影项目", "自动每日推送"]
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
# =================================

# 加载已推送链接
def load_blacklist():
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()

# 保存已推送链接
def save_blacklist(black_set):
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(list(black_set), f, ensure_ascii=False, indent=2)

# 推送Cubox
def push_to_cubox(work_info):
    desc = f"""
作品详细介绍：
{work_info['work_desc']}

艺术家详细介绍：
{work_info['artist_intro']}

艺术家个人网站：{work_info['artist_site'] or '未提供'}

该作品的链接：{work_info['work_url']}

该艺术家的其他作品：
{', '.join(work_info['other_works']) if work_info['other_works'] else '未提供'}
    """.strip()
    
    payload = {
        "type": "url",
        "content": work_info['work_url'],
        "title": work_info['work_title'],
        "description": desc,
        "tags": TAG_LIST,
        "folder": FOLDER_NAME
    }
    try:
        res = requests.post(CUBOX_API, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        resp = res.json()
        return resp.get("code") == 200
    except:
        return False

# Aint-Bad解析
def parse_aintbad_detail(url):
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.find('h1')
        if not h1:
            return None
        artist_name = h1.get_text(strip=True)
        em_tag = soup.find('em')
        artist_intro = em_tag.get_text(strip=True) if em_tag else "暂无介绍"
        
        work_intro = ""
        paragraphs = soup.find_all('p')
        for p in paragraphs:
            p_text = p.get_text(strip=True)
            if not p_text:
                continue
            if "To view more of" in p_text:
                break
            if p_text == artist_intro:
                continue
            work_intro += p_text + "\n"
        
        work_title = f"Photography Project - {artist_name}"
        artist_site = None
        for a in soup.find_all('a', href=True):
            parent_text = a.parent.get_text() if a.parent else ""
            if "To view more of" in parent_text and "website" in parent_text:
                artist_site = a['href']
                break
        
        other_works = []
        for a in soup.find_all('a', href=True):
            if a.get_text(strip=True) == artist_name and '/tag/' in a['href']:
                other_works.append(a['href'])
                break
        
        return {
            "work_title": work_title,
            "work_desc": work_intro.strip(),
            "artist_intro": artist_intro,
            "artist_site": artist_site,
            "work_url": url,
            "other_works": other_works
        }
    except:
        return None

def crawl_aintbad(blacklist):
    works = []
    try:
        resp = requests.get("https://aint-bad.com", headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for h2 in soup.find_all('h2'):
            a_tag = h2.find('a', href=True)
            if not a_tag:
                continue
            link = a_tag['href']
            if not link.startswith('http'):
                link = "https://aint-bad.com" + link
            if link in blacklist:
                continue
            work = parse_aintbad_detail(link)
            if work:
                works.append(work)
    except:
        pass
    return works

# 主任务
def main():
    print(f"开始执行 {datetime.now()} 的推送任务")
    # 拉取最新仓库代码，保证拿到最新的去重记录
    repo = git.Repo(os.getcwd())
    repo.remotes.origin.pull()
    
    blacklist = load_blacklist()
    all_works = crawl_aintbad(blacklist)
    
    # 去重
    unique_works = []
    seen = set()
    for w in all_works:
        if w['work_url'] not in seen:
            seen.add(w['work_url'])
            unique_works.append(w)
    
    send_list = unique_works[:TARGET_NUM]
    print(f"本次将推送 {len(send_list)} 条内容")
    
    # 推送
    success_count = 0
    for work in send_list:
        if push_to_cubox(work):
            blacklist.add(work['work_url'])
            success_count +=1
            print(f"成功推送：{work['work_title']}")
    
    # 保存去重记录，提交回仓库
    save_blacklist(blacklist)
    repo.git.add(BLACKLIST_FILE)
    repo.index.commit(f"Daily push: {datetime.now().strftime('%Y-%m-%d')}, pushed {success_count} items")
    repo.remotes.origin.push()
    print(f"任务完成，共成功推送 {success_count} 条")

if __name__ == "__main__":
    main()
