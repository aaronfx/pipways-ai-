import json
import re
from .main import openrouter_chat
from typing import Dict, List, Tuple
from .main import asyncpg

def generate_blog_content(topic: str, keywords: str, audience: str, tone: str) -> Dict:
    prompt = f"""Generate an SEO-optimized blog post for a trading academy on the topic: {topic}.
Keywords: {keywords}
Target audience: {audience}
Tone: {tone}

Output in Editor.js compatible JSON format:
{{
    "title": "Main Title",
    "meta_title": "SEO Meta Title (max 70 chars)",
    "meta_description": "SEO Meta Description (max 160 chars)",
    "focus_keyword": "Primary keyword",
    "excerpt": "Short excerpt",
    "content": {{
        "time": timestamp,
        "blocks": [
            {{"id": "unique_id", "type": "header", "data": {{"text": "H1 Text", "level": 1}}}},
            {{"id": "unique_id", "type": "paragraph", "data": {{"text": "Paragraph text"}}}},
            // Include other blocks: list, quote, table, code, image (with placeholder url), embed (with example TradingView url), delimiter
        ],
        "version": "2.28.0"
    }}
}}"""

    messages = [
        {"role": "system", "content": "You are an expert trading content writer. Create structured, SEO-friendly content with proper heading hierarchy."},
        {"role": "user", "content": prompt}
    ]
    
    response, error = openrouter_chat(messages, max_tokens=3000)
    
    if error:
        raise Exception(error)
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except:
        raise Exception("Failed to parse AI response")

def calculate_reading_time(content_data: Dict) -> int:
    text = ''
    for block in content_data.get('blocks', []):
        if block['type'] in ['header', 'paragraph', 'quote', 'list', 'code']:
            if 'text' in block['data']:
                text += block['data']['text'] + ' '
            elif 'items' in block['data']:
                text += ' '.join(block['data']['items']) + ' '
            elif 'code' in block['data']:
                text += block['data']['code'] + ' '
    word_count = len(text.split())
    return max(1, word_count // 200)

def calculate_seo_score(content_data: Dict, title: str, meta_description: str, focus_keyword: str) -> Tuple[int, List[str]]:
    score = 0
    suggestions = []
    
    # Title checks
    if not title:
        suggestions.append("Add a title")
    elif len(title) > 70:
        suggestions.append("Title too long (max 70 chars)")
    else:
        score += 20
    if focus_keyword and focus_keyword.lower() in title.lower():
        score += 10
    
    # Meta description
    if not meta_description:
        suggestions.append("Add meta description")
    elif len(meta_description) > 160:
        suggestions.append("Meta description too long (max 160 chars)")
    elif len(meta_description) < 120:
        suggestions.append("Meta description too short (ideal 120-160 chars)")
    else:
        score += 20
    
    # Content length
    full_text = ' '.join([b['data'].get('text', '') for b in content_data.get('blocks', []) if 'text' in b['data']])
    word_count = len(full_text.split())
    if word_count < 300:
        suggestions.append("Content too short (aim for 300+ words)")
    elif word_count > 2000:
        score += 10
    else:
        score += 10
    
    # Headings
    headings = [b for b in content_data.get('blocks', []) if b['type'] == 'header']
    h1_count = sum(1 for h in headings if h['data']['level'] == 1)
    h2_count = sum(1 for h in headings if h['data']['level'] == 2)
    if h1_count != 1:
        suggestions.append("Should have exactly one H1 heading")
    else:
        score += 10
    if h2_count < 2:
        suggestions.append("Add at least 2 H2 headings")
    else:
        score += 10
    
    # Keyword density
    if focus_keyword:
        density = full_text.lower().count(focus_keyword.lower()) / word_count * 100 if word_count > 0 else 0
        if 0.5 <= density <= 2.5:
            score += 10
        else:
            suggestions.append(f"Keyword density {density:.1f}% (ideal 0.5-2.5%)")
    
    # Images alt text
    images = [b for b in content_data.get('blocks', []) if b['type'] == 'image']
    for img in images:
        if not img['data'].get('alt'):
            suggestions.append("Add alt text to images")
            break
    if images and all(img['data'].get('alt') for img in images):
        score += 5
    
    # Internal links (simple check for <a href="/blog/")
    if '<a href="/blog/' not in full_text:
        suggestions.append("Add internal links")
    else:
        score += 5
    
    return min(100, score), suggestions

async def get_link_suggestions(content_data: Dict, conn) -> List[Dict]:
    # Extract keywords from content
    full_text = ' '.join([b['data'].get('text', '') for b in content_data.get('blocks', []) if 'text' in b['data']])
    keywords = re.findall(r'\b\w{5,}\b', full_text.lower())[:10]  # Top 10 long words
    
    suggestions = []
    for kw in keywords:
        posts = await conn.fetch("""
            SELECT title, slug FROM blog_posts 
            WHERE status = 'published' AND (title ILIKE $1 OR content_json::text ILIKE $1)
            LIMIT 3
        """, f"%{kw}%")
        for p in posts:
            suggestions.append({"title": p['title'], "slug": p['slug']})
    
    # Deduplicate
    unique = {s['slug']: s for s in suggestions}
    return list(unique.values())
