---
name: web_tools
description: Search the web for up-to-date information, news, and fetch web page contents.
---

# Web Search Skill

You have the ability to search the web for up-to-date information to answer user questions.

## When to use Web Tools
- When the user asks about current events, news, or recent developments (e.g. "What is the stock price of Apple?", "Who won the game last night?").
- When you need to find specific facts or documentation that you don't confidently know.
- When the user explicitly asks you to search the web or fetch a URL.

## Available Tools
1. `web_search(query, max_results)`: Use this to search the web for a string. It returns a list of titles, snippets, and URLs.
2. `web_fetch(url)`: Use this if the snippet from `web_search` is not detailed enough, or if the user gives you a specific link to read. It will fetch the webpage and extract readable markdown text.

## Best Practices
- Keep your search queries concise and keyword-focused (e.g., "nvidia q3 earnings 2024" instead of "what were the earnings for NVIDIA in the third quarter of 2024").
- If a search result looks promising but the snippet lacks detail, use `web_fetch(url)` to read the full context before answering the user.
- Always synthesize the information in your own words. Do not just dump the raw search results to the user.
