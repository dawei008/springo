"""
Web Search Tools
Search engines and web content fetching
"""

from typing import Any, Dict

# Optional imports
try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Search engine configuration
_search_config = {
    "engine": "brave",
    "api_key": "",
    "custom_url": ""
}


def set_search_config(engine: str, api_key: str = "", custom_url: str = ""):
    """Update search engine configuration"""
    global _search_config
    _search_config["engine"] = engine
    _search_config["api_key"] = api_key
    _search_config["custom_url"] = custom_url


def get_search_config() -> Dict[str, Any]:
    """Get current search engine configuration"""
    return _search_config.copy()


def _search_brave(query: str, max_results: int, api_key: str, freshness: str = None) -> Dict[str, Any]:
    """Search using Brave Search API"""
    if not HAS_REQUESTS:
        return {"error": "Requests library not available"}
    if not api_key:
        return {"error": "Brave Search API key not configured. Set it in Settings."}
    try:
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key
        }
        params = {
            "q": query,
            "count": min(max_results, 20)
        }

        freshness_labels = {
            "pd": "past_day",
            "pw": "past_week",
            "pm": "past_month",
            "py": "past_year"
        }
        if freshness and freshness in freshness_labels:
            params["freshness"] = freshness
            freshness_label = freshness_labels[freshness]
        else:
            freshness_label = "all_time"

        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("description", ""),
                "age": item.get("age", "")
            })

        return {
            "query": query,
            "engine": "brave",
            "search_time": current_time,
            "freshness": freshness_label,
            "results": results,
            "count": len(results)
        }
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return {"error": "Invalid Brave API key. Check your key in Settings."}
        return {"error": f"Brave search failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Brave search failed: {str(e)}"}


def _search_tavily(query: str, max_results: int, api_key: str, freshness: str = None) -> Dict[str, Any]:
    """Search using Tavily API"""
    if not HAS_REQUESTS:
        return {"error": "Requests library not available"}
    if not api_key:
        return {"error": "Tavily API key not configured. Set it in Settings."}
    try:
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        freshness_to_days = {"pd": 1, "pw": 7, "pm": 30, "py": 365}
        freshness_labels = {"pd": "past_day", "pw": "past_week", "pm": "past_month", "py": "past_year"}

        days = freshness_to_days.get(freshness) if freshness else None
        freshness_label = freshness_labels.get(freshness, "all_time") if freshness else "all_time"

        headers = {"Content-Type": "application/json"}
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": min(max_results, 10),
            "include_answer": True
        }

        if days:
            payload["days"] = days

        response = requests.post(
            "https://api.tavily.com/search",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("content", ""),
                "published_date": item.get("published_date", "")
            })

        return {
            "query": query,
            "engine": "tavily",
            "search_time": current_time,
            "freshness": freshness_label,
            "answer": data.get("answer", ""),
            "results": results,
            "count": len(results)
        }
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return {"error": "Invalid Tavily API key. Check your key in Settings."}
        return {"error": f"Tavily search failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Tavily search failed: {str(e)}"}


def _search_custom(query: str, max_results: int, api_key: str, custom_url: str, freshness: str = None) -> Dict[str, Any]:
    """Search using custom API"""
    if not HAS_REQUESTS:
        return {"error": "Requests library not available"}
    if not custom_url:
        return {"error": "Custom search URL not configured. Set it in Settings."}
    try:
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        modified_query = query
        freshness_label = "all_time"
        if freshness:
            now = datetime.now()
            freshness_labels = {"pd": "past_day", "pw": "past_week", "pm": "past_month", "py": "past_year"}
            freshness_label = freshness_labels.get(freshness, "all_time")

            if freshness == "pd":
                modified_query = f"{query} {now.strftime('%Y-%m-%d')}"
            elif freshness in ["pw", "pm"]:
                modified_query = f"{query} {now.strftime('%B %Y')}"
            elif freshness == "py":
                modified_query = f"{query} {now.year}"

        url = custom_url.replace("{query}", requests.utils.quote(modified_query))

        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        try:
            data = response.json()
            if isinstance(data, list):
                results = data[:max_results]
            elif "results" in data:
                results = data["results"][:max_results]
            elif "items" in data:
                results = data["items"][:max_results]
            else:
                results = [data]
        except:
            results = [{"content": response.text[:5000]}]

        return {
            "query": query,
            "modified_query": modified_query if modified_query != query else None,
            "engine": "custom",
            "search_time": current_time,
            "freshness": freshness_label,
            "note": "Custom API may not support time filtering; time keywords added to query" if freshness else None,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        return {"error": f"Custom search failed: {str(e)}"}


def web_search(query: str, max_results: int = 10, freshness: str = None) -> Dict[str, Any]:
    """Search the web using configured search engine"""
    engine = _search_config.get("engine", "brave")
    api_key = _search_config.get("api_key", "")
    custom_url = _search_config.get("custom_url", "")

    if engine in ["brave", "tavily"] and not api_key:
        return {"error": f"{engine.capitalize()} Search API key not configured. Please set it in Settings."}
    if engine == "custom" and not custom_url:
        return {"error": "Custom search URL not configured. Please set it in Settings."}

    if engine == "brave":
        return _search_brave(query, max_results, api_key, freshness)
    elif engine == "tavily":
        return _search_tavily(query, max_results, api_key, freshness)
    elif engine == "custom":
        return _search_custom(query, max_results, api_key, custom_url, freshness)
    else:
        return {"error": f"Unknown search engine: {engine}"}


def web_fetch(url: str, selector: str = None) -> Dict[str, Any]:
    """Fetch web page content"""
    if not HAS_REQUESTS:
        return {"error": "Requests library not available. Install with: pip install requests beautifulsoup4"}

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        if selector:
            elements = soup.select(selector)
            text = "\n".join(el.get_text(strip=True) for el in elements)
        else:
            text = soup.get_text(separator="\n", strip=True)

        if len(text) > 50000:
            text = text[:50000] + "\n... (truncated)"

        return {
            "url": url,
            "title": soup.title.string if soup.title else None,
            "content": text,
            "length": len(text)
        }
    except Exception as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}
