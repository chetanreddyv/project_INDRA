"""
mcp_servers/web_tools.py — Web Search and Fetch tools.

This plugin provides the agent with the ability to search the web and
fetch specific webpage contents, returning readable markdown.
"""

import logging
from typing import Dict, Any

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

logger = logging.getLogger("mcp.web_tools")

# ══════════════════════════════════════════════════════════════
# Tool Implementations
# ══════════════════════════════════════════════════════════════

def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web for current information.
    
    Args:
        query: The search query.
        max_results: The maximum number of results to return (default: 5).
        
    Returns:
        A string containing a markdown-formatted list of search results,
        including titles, snippets, and URLs.
    """
    logger.info(f"🛠️ web_search(query='{query}', max_results={max_results})")
    try:
        results = []
        with DDGS() as ddgs:
            # text() is standard search. It returns an iterator.
            # We wrap in a try-catch per-iteration in case DDGS throws a rate limit halfway.
            try:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(r)
            except Exception as inner_e:
                logger.warning(f"DDGS interrupted during fetch: {inner_e}")
                
        if not results:
            return f"No results found for query: '{query}'. Try a shorter, more keyword-focused query."
            
        lines = [f"Search results for '{query}':\n"]
        for i, res in enumerate(results, start=1):
            title = res.get("title", "No Title")
            href = res.get("href", "No URL")
            body = res.get("body", "No Snippet")
            # Truncate overly long bodies just in case
            if len(body) > 500:
                body = body[:500] + "..."
            lines.append(f"### {i}. [{title}]({href})\n{body}\n")
            
        out_str = "\n".join(lines)
        logger.info(f"✅ web_search returned {len(results)} results ({len(out_str)} chars)")
        return out_str
    except Exception as e:
        logger.error(f"❌ web_search error: {e}")
        return f"Error executing search: {e}. The search engine might be rate-limiting. Try asking the user for a different query, or try using web_fetch on a known URL instead."


def web_fetch(url: str) -> str:
    """
    Fetch a URL and return its readable text/markdown content.
    Use this to read a full article or page found via web_search.
    
    Args:
        url: The web page URL to fetch.
        
    Returns:
        A string containing the readable text extracted from the webpage.
    """
    logger.info(f"🛠️ web_fetch(url='{url}')")
    try:
        # Some academic or news sites require a non-bot User-Agent
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        with httpx.Client(headers=headers, timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            
        soup = BeautifulSoup(resp.content, "html.parser")
        
        # Remove noisy elements
        for script in soup(["script", "style", "nav", "footer", "aside"]):
            script.extract()
            
        # Get text
        text = soup.get_text(separator="\n\n")
        
        # Clean up excessive blank lines
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)
        
        # Truncate if massively huge to save context window tokens
        max_chars = 15000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n... [Content Truncated due to length]"
            
        logger.info(f"✅ web_fetch extracted {len(text)} characters")
        return f"Content of {url}:\n\n{text}"
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ web_fetch HTTP error: {e}")
        return f"Failed to fetch {url}: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"❌ web_fetch error: {e}")
        return f"Failed to fetch {url}: {e}"

# ══════════════════════════════════════════════════════════════
# Tool Registry
# ══════════════════════════════════════════════════════════════

TOOL_REGISTRY: Dict[str, Any] = {
    "web_search": web_search,
    "web_fetch": web_fetch,
}
