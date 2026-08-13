"""
ByteDance campus recruitment adapter.
Uses curl_cffi to bypass anti-bot protection with TLS fingerprint impersonation.
"""
from .base import BaseAdapter, JobPost
from curl_cffi import requests


class ByteDanceAdapter(BaseAdapter):
    name = "bytedance"
    display_name = "字节跳动"

    API_URL = "https://jobs.bytedance.com/api/v1/search/job/posts"

    # Pre-configured filter IDs (from public API taxonomy)
    CATEGORIES = {
        "后端": "6704215862557018372",
        "算法": "6704215956018694411",
        "前端": "6704215886108035339",
        "客户端": "6704215957146962184",
        "数据": "6704215974586486024",
    }

    CITIES = {
        "北京": "CT_11", "上海": "CT_125", "深圳": "CT_128",
        "杭州": "CT_52", "广州": "CT_45", "成都": "CT_22",
    }

    HEADERS = {
        "portal-channel": "campus",
        "portal-platform": "pc",
        "website-path": "campus",
        "Origin": "https://jobs.bytedance.com",
        "Referer": "https://jobs.bytedance.com/campus/position",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }

    def fetch(self, keyword: str, category: str = "后端",
              limit: int = 50, max_results: int = 500,
              recruitment_ids: list[str] | None = None) -> list[JobPost]:

        if recruitment_ids is None:
            recruitment_ids = ["201"]  # 2027校招

        cat_id = self.CATEGORIES.get(category, category)
        session = requests.Session()
        results = []
        seen = set()

        print(f"\n[{self.display_name}] 搜索: {keyword} (分类: {category})")

        for offset in range(0, max_results, limit):
            body = {
                "keyword": keyword, "limit": limit, "offset": offset,
                "portal_type": 3, "portal_entrance": 1,
                "language": "zh",
                "recruitment_id_list": recruitment_ids,
                "job_category_id_list": [cat_id],
            }

            try:
                r = session.post(self.API_URL, json=body,
                                 headers=self.HEADERS,
                                 impersonate="chrome131", timeout=30)
                data = r.json()
                if data.get("code") != 0:
                    print(f"  API error: {data.get('message', data)}")
                    break

                posts = data["data"]["job_post_list"]
                total = data["data"]["count"]
                print(f"  offset={offset} 获取 {len(posts)} 条, 共 {total} 条")

                for p in posts:
                    pid = str(p["id"])
                    if pid in seen:
                        continue
                    seen.add(pid)
                    results.append(JobPost(
                        id=pid,
                        title=p.get("title", ""),
                        department=p.get("department", ""),
                        city=p.get("city_name", ""),
                        type=p.get("recruitment_name", ""),
                        description=p.get("description", ""),
                        requirement=p.get("requirement", ""),
                        extra=p.get("extra_requirement", ""),
                    ))

                if offset + limit >= total:
                    break

                self._rate_limit()

            except Exception as e:
                print(f"  offset={offset} 失败: {e}")
                break

        saved = self.save(results)
        print(f"  保存 {saved} 个新JD (去重后)")

        return results
