#!/usr/bin/env python3

import re


def slack_to_markdown(content: str) -> str:
    """Convert Slack mrkdwn to OpenAI markdown"""
    # Split the input string into parts based on code blocks and inline code
    parts = re.split(r"(?s)(```.+?```|`[^`\n]+?`)", content)

    # Apply the bold, italic, and strikethrough formatting to text not within code
    result = ""
    for part in parts:
        if part.startswith("```") or part.startswith("`"):
            result += part
        else:
            for o, n in [
                (r"\*(?!\s)([^\*\n]+?)(?<!\s)\*", r"**\1**"),  # *bold* to **bold**
                (r"_(?!\s)([^_\n]+?)(?<!\s)_", r"*\1*"),  # _italic_ to *italic*
                (r"~(?!\s)([^~\n]+?)(?<!\s)~", r"~~\1~~"),  # ~strike~ to ~~strike~~
            ]:
                part = re.sub(o, n, part)
            result += part
    return result


def markdown_to_slack(content: str) -> str:
    """Convert OpenAI markdown to Slack mrkdwn"""
    # Split the input string into parts based on code blocks and inline code
    parts = re.split(r"(?s)(```.+?```|`[^`\n]+?`)", content)

    # Apply the bold, italic, and strikethrough formatting to text not within code
    result = ""
    for part in parts:
        if part.startswith("```") or part.startswith("`"):
            result += part
        else:
            for o, n in [
                (
                    r"\*\*\*(?!\s)([^\*\n]+?)(?<!\s)\*\*\*",
                    r"_*\1*_",
                ),  # ***bold italic*** to *_bold italic_*
                (
                    r"(?<![\*_])\*(?!\s)([^\*\n]+?)(?<!\s)\*(?![\*_])",
                    r"_\1_",
                ),  # *italic* to _italic_
                (r"\*\*(?!\s)([^\*\n]+?)(?<!\s)\*\*", r"*\1*"),  # **bold** to *bold*
                (r"__(?!\s)([^_\n]+?)(?<!\s)__", r"*\1*"),  # __bold__ to *bold*
                (r"~~(?!\s)([^~\n]+?)(?<!\s)~~", r"~\1~"),  # ~~strike~~ to ~strike~
            ]:
                part = re.sub(o, n, part)
            result += part
    return result





def format_message_for_slack(content: str) -> str:
    """Complete formatting pipeline for Slack messages"""
    # 1. Convert markdown links [text](url) to Slack format <url|text> FIRST
    content = convert_markdown_links(content)

    # 2. Convert markdown to Slack format
    content = markdown_to_slack(content)

    # 3. Format remaining bare URLs (but skip already formatted ones)
    content = format_remaining_urls(content)

    return content


def convert_markdown_links(content: str) -> str:
    """Convert markdown links [text](url) to Slack format <url|text>"""
    # Pattern to match markdown links: [text](url)
    markdown_link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'

    def replace_markdown_link(match):
        text = match.group(1)
        url = match.group(2)
        return f"<{url}|{text}>"

    return re.sub(markdown_link_pattern, replace_markdown_link, content)


def format_remaining_urls(content: str) -> str:
    """Format remaining bare URLs that aren't already in Slack format"""
    # Pattern to match URLs that are NOT already in Slack format <url|text>
    # This looks for URLs that are not preceded by < and not followed by |
    url_pattern = r'(?<!<)https?://[^\s<>\[\]]+(?:[^\s<>\[\].,;:!?]|[.,;:!?](?!\s|$))*(?!\|)'

    def replace_url(match):
        url = match.group(0)

        # Extract meaningful text from URL
        if 'tecmundo.com.br' in url:
            if 'meta-ai-studio' in url.lower() or ('meta' in url.lower() and 'ai' in url.lower()):
                return f"<{url}|Meta AI Studio chegou ao Brasil>"
            elif 'chatbots' in url.lower():
                return f"<{url}|Artigo sobre Chatbots - TecMundo>"
            else:
                return f"<{url}|Artigo TecMundo>"

        elif 'slack.com' in url:
            return f"<{url}|Ver mensagem no Slack>"

        elif 'youtube.com' in url or 'youtu.be' in url:
            return f"<{url}|Vídeo YouTube>"

        elif 'drive.google.com' in url:
            return f"<{url}|Google Drive>"

        elif 'docs.google.com' in url:
            return f"<{url}|Google Docs>"

        elif 'calendar.google.com' in url:
            return f"<{url}|Google Calendar>"

        elif 'github.com' in url:
            return f"<{url}|GitHub>"

        elif 'linkedin.com' in url:
            return f"<{url}|LinkedIn>"

        else:
            # Extract domain for generic links
            domain = re.search(r'https?://(?:www\.)?([^/]+)', url)
            if domain:
                domain_name = domain.group(1).replace('www.', '')
                return f"<{url}|{domain_name}>"
            else:
                return f"<{url}|Link>"

    return re.sub(url_pattern, replace_url, content)
