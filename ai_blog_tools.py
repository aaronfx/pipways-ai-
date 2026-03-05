# ai_blog_tools.py
import os
import json
import re
import requests
from typing import Dict, List, Tuple, Optional
from datetime import datetime

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

def openrouter_chat(messages, model="anthropic/claude-3.5-sonnet", max_tokens=2000):
    """Helper function to call OpenRouter API"""
    if not OPENROUTER_API_KEY:
        return None, "OpenRouter API key not configured"
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pipways.com",
        "X-Title": "Pipways Trading Platform"
    }
    
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

def generate_blog_content(topic: str, keywords: Optional[str], audience: str, tone: str) -> Dict:
    """Generate AI blog content with Editor.js compatible structure"""
    
    prompt = f"""Create a comprehensive, SEO-optimized blog post about "{topic}" for {audience} traders.
    
Keywords to include: {keywords or 'trading, forex, risk management'}
Tone: {tone}

Generate the response in this exact JSON format:
{{
    "title": "SEO Optimized H1 Title",
    "meta_title": "Meta title under 70 chars",
    "meta_description": "Compelling meta description under 160 chars",
    "focus_keyword": "primary keyword",
    "excerpt": "Brief summary for blog listing",
    "content_blocks": [
        {{"type": "header", "data": {{"level": 2, "text": "Introduction"}}}},
        {{"type": "paragraph", "data": {{"text": "Opening paragraph..."}}}},
        {{"type": "header", "data": {{"level": 2, "text": "Main Section"}}}},
        {{"type": "header", "data": {{"level": 3, "text": "Subsection"}}}},
        {{"type": "paragraph", "data": {{"text": "Content..."}}}},
        {{"type": "list", "data": {{"style": "unordered", "items": ["Point 1", "Point 2"]}}}},
        {{"type": "quote", "data": {{"text": "Inspirational trading quote", "caption": "Author"}}}},
        {{"type": "header", "data": {{"level": 2, "text": "Conclusion"}}}}
    ],
    "suggested_internal_links": ["Risk Management", "Trading Psychology", "Technical Analysis"],
    "reading_time": 5
}}"""

    messages = [
        {
            "role": "system",
            "content": "You are an expert trading content writer and SEO specialist. Create engaging, educational content for forex traders. Always return valid JSON."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    response, error = openrouter_chat(messages, max_tokens=2500)
    
    if error:
        return {
            "error": error,
            "title": f"Guide to {topic}",
            "content_blocks": [{"type": "paragraph", "data": {"text": "AI generation failed. Please write manually."}}]
        }
    
    try:
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        pass
    
    # Fallback structure
    return {
        "title": f"Complete Guide to {topic}",
        "meta_title": f"{topic} | Pipways Trading Academy",
        "meta_description": f"Learn everything about {topic} in this comprehensive guide for {audience} traders.",
        "focus_keyword": topic.lower(),
        "excerpt": f"Master {topic} with our expert guide designed for {audience} traders.",
        "content_blocks": [
            {"type": "header", "data": {"level": 2, "text": "Introduction"}},
            {"type": "paragraph", "data": {"text": response[:500] if response else "Content generation in progress..."}},
            {"type": "header", "data": {"level": 2, "text": "Key Takeaways"}}
        ],
        "suggested_internal_links": [],
        "reading_time": 3
    }

def calculate_reading_time(content_json: Dict) -> int:
    """Calculate reading time in minutes based on content blocks"""
    if not content_json or 'blocks' not in content_json:
        return 1
    
    total_words = 0
    
    for block in content_json.get('blocks', []):
        block_type = block.get('type')
        data = block.get('data', {})
        
        if block_type == 'paragraph':
            total_words += len(data.get('text', '').split())
        elif block_type == 'header':
            total_words += len(data.get('text', '').split())
        elif block_type == 'list':
            items = data.get('items', [])
            for item in items:
                total_words += len(str(item).split())
        elif block_type == 'quote':
            total_words += len(data.get('text', '').split())
    
    # Average reading speed: 200 words per minute
    reading_time = max(1, round(total_words / 200))
    return reading_time

def calculate_seo_score(content_json: Dict, title: str, meta_description: str, focus_keyword: str) -> Tuple[int, List[str]]:
    """Calculate SEO score and return suggestions"""
    score = 0
    suggestions = []
    
    if not content_json or 'blocks' not in content_json:
        return 0, ["No content to analyze"]
    
    blocks = content_json.get('blocks', [])
    
    # Check for H1 (should only be one, in title)
    h1_count = sum(1 for b in blocks if b.get('type') == 'header' and b.get('data', {}).get('level') == 1)
    if h1_count > 1:
        suggestions.append("Remove extra H1 headings - only one H1 allowed")
    elif h1_count == 0:
        suggestions.append("Add an H1 heading for better SEO structure")
    else:
        score += 10
    
    # Check for H2 headings
    h2_count = sum(1 for b in blocks if b.get('type') == 'header' and b.get('data', {}).get('level') == 2)
    if h2_count < 2:
        suggestions.append(f"Add more H2 headings (found {h2_count}, need at least 2)")
    else:
        score += 15
    
    # Check for H3 headings
    h3_count = sum(1 for b in blocks if b.get('type') == 'header' and b.get('data', {}).get('level') == 3)
    if h3_count > 0:
        score += 10
    
    # Check content length (word count)
    total_words = 0
    for block in blocks:
        if block.get('type') == 'paragraph':
            total_words += len(block.get('data', {}).get('text', '').split())
    
    if total_words < 300:
        suggestions.append(f"Content too short ({total_words} words). Aim for 800+ words")
    elif total_words < 600:
        score += 10
        suggestions.append(f"Consider expanding content (currently {total_words} words)")
    else:
        score += 20
    
    # Check meta description
    if not meta_description:
        suggestions.append("Add meta description")
    elif len(meta_description) < 120:
        suggestions.append(f"Meta description too short ({len(meta_description)} chars). Aim for 120-160")
    elif len(meta_description) > 160:
        suggestions.append(f"Meta description too long ({len(meta_description)} chars). Max 160")
    else:
        score += 15
    
    # Check focus keyword usage
    if focus_keyword:
        content_text = ' '.join([
            b.get('data', {}).get('text', '') 
            for b in blocks 
            if b.get('type') in ['paragraph', 'header']
        ]).lower()
        
        keyword_count = content_text.count(focus_keyword.lower())
        if keyword_count == 0:
            suggestions.append(f"Focus keyword '{focus_keyword}' not found in content")
        elif keyword_count < 2:
            suggestions.append(f"Use focus keyword '{focus_keyword}' more frequently")
        else:
            score += 15
    else:
        suggestions.append("Set a focus keyword for better SEO")
    
    # Check for images
    image_count = sum(1 for b in blocks if b.get('type') == 'image')
    if image_count == 0:
        suggestions.append("Add at least one image to improve engagement")
    else:
        score += 10
    
    # Check for lists
    list_count = sum(1 for b in blocks if b.get('type') == 'list')
    if list_count == 0:
        suggestions.append("Add bulleted or numbered lists for better readability")
    else:
        score += 5
    
    # Ensure score is between 0-100
    score = min(100, max(0, score))
    
    if score >= 80:
        suggestions.insert(0, "Great job! Your post is well-optimized.")
    elif score >= 60:
        suggestions.insert(0, "Good start. Address the suggestions above to improve.")
    else:
        suggestions.insert(0, "Several SEO improvements needed. See suggestions below.")
    
    return score, suggestions

async def get_link_suggestions(content_json: Dict, conn) -> List[Dict]:
    """Analyze content and suggest internal links to existing blog posts"""
    if not content_json or 'blocks' not in content_json:
        return []
    
    # Extract text content
    content_text = ' '.join([
        b.get('data', {}).get('text', '') 
        for b in content_json.get('blocks', []) 
        if b.get('type') in ['paragraph', 'header']
    ]).lower()
    
    # Get all published posts
    posts = await conn.fetch("""
        SELECT id, title, slug, category 
        FROM blog_posts 
        WHERE status = 'published'
    """)
    
    suggestions = []
    
    for post in posts:
        title_lower = post['title'].lower()
        category_lower = (post['category'] or '').lower()
        
        # Check if post title or category appears in content
        if title_lower in content_text or category_lower in content_text:
            # Check if already linked (simple check)
            if post['slug'] not in content_text:
                suggestions.append({
                    "id": post['id'],
                    "title": post['title'],
                    "slug": post['slug'],
                    "category": post['category'],
                    "context": f"Consider linking to '{post['title']}' when discussing {post['category'] or 'this topic'}"
                })
    
    # Limit to top 5 suggestions
    return suggestions[:5]
