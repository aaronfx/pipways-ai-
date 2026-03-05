from fastapi import APIRouter, Depends, HTTPException, Form, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List
from datetime import datetime
import json
import re
import uuid
from .main import get_db, get_current_admin, get_current_user
from .ai_blog_tools import generate_blog_content, calculate_seo_score, get_link_suggestions, calculate_reading_time
from .main import asyncpg

blog_router = APIRouter(tags=["blog"])

# Helper to render JSON content to HTML for server-side rendering
def render_content_blocks(blocks: List[dict]) -> str:
    html = ""
    for block in blocks:
        block_type = block.get('type')
        data = block.get('data')
        if block_type == 'header':
            level = data.get('level', 1)
            html += f"<h{level}>{data.get('text', '')}</h{level}>\n"
        elif block_type == 'paragraph':
            html += f"<p>{data.get('text', '')}</p>\n"
        elif block_type == 'list':
            style = data.get('style')
            items = data.get('items', [])
            tag = 'ul' if style == 'unordered' else 'ol'
            html += f"<{tag}>\n"
            for item in items:
                html += f"<li>{item}</li>\n"
            html += f"</{tag}>\n"
        elif block_type == 'quote':
            html += f"<blockquote>{data.get('text', '')}</blockquote>\n"
        elif block_type == 'table':
            content = data.get('content', [])
            html += "<table>\n"
            for row in content:
                html += "<tr>\n"
                for cell in row:
                    html += f"<td>{cell}</td>\n"
                html += "</tr>\n"
            html += "</table>\n"
        elif block_type == 'code':
            html += f"<pre><code>{data.get('code', '')}</code></pre>\n"
        elif block_type == 'image':
            url = data.get('file', {}).get('url', '')
            caption = data.get('caption', '')
            alt = data.get('alt', caption)
            html += f"<img src=\"{url}\" alt=\"{alt}\" />\n"
            if caption:
                html += f"<figcaption>{caption}</figcaption>\n"
        elif block_type == 'embed':
            url = data.get('embed')
            html += f"<iframe src=\"{url}\" width=\"100%\" height=\"400\" frameborder=\"0\"></iframe>\n"
        elif block_type == 'delimiter':
            html += "<hr />\n"
    return html

# Helper to generate Article schema
def generate_article_schema(post: dict, base_url: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post['title'],
        "author": {
            "@type": "Person",
            "name": "Pipways Team"  # Or fetch author name
        },
        "datePublished": post['published_at'].isoformat() if post['published_at'] else None,
        "image": post['featured_image'],
        "publisher": {
            "@type": "Organization",
            "name": "Pipways",
            "logo": {
                "@type": "ImageObject",
                "url": f"{base_url}/logo.png"  # Update with actual logo
            }
        },
        "url": f"{base_url}/blog/{post['slug']}",
        "description": post['meta_description'] or post['excerpt'],
        "keywords": post['meta_keywords']
    }

@blog_router.get("/posts", response_class=JSONResponse)
async def get_blog_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    category: Optional[str] = None,
    tag: Optional[str] = None,
    status: Optional[str] = "published",
    search: Optional[str] = None,
    conn=Depends(get_db)
):
    """Get blog posts with filtering and pagination"""
    try:
        offset = (page - 1) * per_page
        params = []
        where_clauses = []
        
        if status:
            where_clauses.append(f"status = ${len(params)+1}")
            params.append(status)
        
        if category:
            where_clauses.append(f"category = ${len(params)+1}")
            params.append(category)
        
        if tag:
            where_clauses.append(f"${len(params)+1} = ANY(tags)")
            params.append(tag)
        
        if search:
            where_clauses.append(f"(title ILIKE ${len(params)+1} OR content ILIKE ${len(params)+1} OR excerpt ILIKE ${len(params)+1})")
            params.append(f"%{search}%")
        
        # For published, add time filter
        if status == 'published':
            where_clauses.append(f"(published_at <= NOW() OR published_at IS NULL)")
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Get posts
        posts = await conn.fetch(f"""
            SELECT id, title, slug, excerpt, featured_image, category, tags,
                   meta_title, meta_description, published_at, view_count, created_at
            FROM blog_posts
            WHERE {where_sql}
            ORDER BY published_at DESC NULLS LAST
            LIMIT ${len(params)+1} OFFSET ${len(params)+2}
        """, *params, per_page, offset)
        
        # Get total count
        count_result = await conn.fetchrow(f"""
            SELECT COUNT(*) as total FROM blog_posts WHERE {where_sql}
        """, *params[:-2] if len(params) > 2 else [])
        
        total = count_result['total'] if count_result else 0
        
        return {
            "posts": [dict(p) for p in posts],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.get("/post/{slug}", response_class=JSONResponse)
async def get_blog_post_api(
    slug: str,
    conn=Depends(get_db)
):
    """Get single blog post by slug (API version)"""
    try:
        post = await conn.fetchrow("""
            SELECT * FROM blog_posts 
            WHERE slug = $1 AND status = 'published' AND (published_at <= NOW() OR published_at IS NULL)
        """, slug)
        
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Increment view count
        await conn.execute("""
            UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1
        """, post['id'])
        
        return dict(post)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.get("/{slug}", response_class=HTMLResponse)
async def get_blog_post_html(
    slug: str,
    request: Request,
    conn=Depends(get_db)
):
    """Server-rendered blog post for SEO"""
    try:
        post = await conn.fetchrow("""
            SELECT * FROM blog_posts 
            WHERE slug = $1 AND status = 'published' AND (published_at <= NOW() OR published_at IS NULL)
        """, slug)
        
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Handle scheduled posts
        if post['status'] == 'scheduled' and post['scheduled_at'] <= datetime.utcnow():
            await conn.execute("""
                UPDATE blog_posts SET status = 'published', published_at = $1 WHERE id = $2
            """, post['scheduled_at'], post['id'])
            post = await conn.fetchrow("SELECT * FROM blog_posts WHERE id = $1", post['id'])
        
        # Increment view count
        await conn.execute("UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1", post['id'])
        
        base_url = str(request.base_url).rstrip('/')
        content_html = render_content_blocks(post['content_json'].get('blocks', []) if post['content_json'] else [])
        schema = generate_article_schema(dict(post), base_url)
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{post['meta_title'] or post['title']}</title>
    <meta name="description" content="{post['meta_description'] or post['excerpt']}">
    <meta name="keywords" content="{post['meta_keywords']}">
    <meta property="og:title" content="{post['meta_title'] or post['title']}">
    <meta property="og:description" content="{post['meta_description'] or post['excerpt']}">
    <meta property="og:image" content="{post['og_image'] or post['featured_image']}">
    <meta property="og:url" content="{base_url}/blog/{slug}">
    <meta name="twitter:card" content="summary_large_image">
    <script type="application/ld+json">{json.dumps(schema)}</script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #0f172a; color: #e2e8f0; }}
        article {{ max-width: 800px; margin: 0 auto; padding: 2rem; }}
    </style>
</head>
<body>
    <article>
        <header>
            <h1>{post['title']}</h1>
            <p>Published on {post['published_at'].strftime('%B %d, %Y') if post['published_at'] else ''}</p>
            <p>Reading time: {post['reading_time']} minutes</p>
            {f'<img src="{post["featured_image"]}" alt="{post["title"]}">' if post['featured_image'] else ''}
        </header>
        <div>{content_html}</div>
        <footer>
            <div>Tags: {', '.join(post['tags'] or [])}</div>
            <!-- Social share buttons -->
            <div>
                <a href="https://twitter.com/intent/tweet?url={base_url}/blog/{slug}&text={post['title']}" target="_blank">Share on Twitter</a>
                <a href="https://www.linkedin.com/shareArticle?mini=true&url={base_url}/blog/{slug}&title={post['title']}" target="_blank">Share on LinkedIn</a>
            </div>
        </footer>
    </article>
</body>
</html>
        """
        return HTMLResponse(content=html)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.post("/admin/posts")
async def create_blog_post(
    title: str = Form(...),
    content_json: str = Form(...),  # JSON string from Editor.js
    excerpt: Optional[str] = Form(None),
    featured_image: Optional[str] = Form(None),
    meta_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    meta_keywords: Optional[str] = Form(None),
    focus_keyword: Optional[str] = Form(None),
    canonical_url: Optional[str] = Form(None),
    og_image: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    status: str = Form("draft"),
    scheduled_at: Optional[str] = Form(None),  # ISO format
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Create new blog post (admin only)"""
    try:
        # Parse content_json
        try:
            content_data = json.loads(content_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid content JSON")
        
        # Create slug from title
        slug = re.sub(r'[^\w\s-]', '', title.lower()).strip()
        slug = re.sub(r'[-\s]+', '-', slug)
        
        # Ensure unique slug
        existing = await conn.fetchrow("SELECT id FROM blog_posts WHERE slug = $1", slug)
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:8]}"
        
        # Process tags
        tag_list = [t.strip() for t in tags.split(',')] if tags else []
        
        # Auto-generate excerpt if not provided
        if not excerpt:
            full_text = ' '.join([b['data']['text'] for b in content_data.get('blocks', []) if 'text' in b['data']])
            excerpt = full_text[:200] + "..." if len(full_text) > 200 else full_text
        
        # Auto-generate meta if not provided
        if not meta_title:
            meta_title = title[:70]
        if not meta_description:
            meta_description = excerpt[:160]
        
        published_at = None
        scheduled_time = None
        if status == 'published':
            published_at = datetime.utcnow()
        elif status == 'scheduled':
            if not scheduled_at:
                raise HTTPException(status_code=400, detail="Scheduled date required")
            scheduled_time = datetime.fromisoformat(scheduled_at)
            if scheduled_time <= datetime.utcnow():
                status = 'published'
                published_at = scheduled_time
            else:
                published_at = None
        
        # Calculate reading time
        reading_time = calculate_reading_time(content_data)
        
        # Calculate SEO score
        seo_score, suggestions = calculate_seo_score(content_data, title, meta_description, focus_keyword)
        
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        post_id = await conn.fetchval("""
            INSERT INTO blog_posts 
            (title, slug, content_json, excerpt, featured_image, meta_title, meta_description,
             meta_keywords, focus_keyword, canonical_url, og_image, author_id, category, tags, status, 
             published_at, scheduled_at, reading_time, seo_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
            RETURNING id
        """,
            title, slug, json.dumps(content_data), excerpt, featured_image, meta_title, meta_description,
            meta_keywords, focus_keyword, canonical_url, og_image, user["id"], category, tag_list, status, 
            published_at, scheduled_time, reading_time, seo_score
        )
        
        return {
            "success": True,
            "post_id": post_id,
            "slug": slug,
            "seo_suggestions": suggestions,
            "message": "Post created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.put("/admin/posts/{post_id}")
async def update_blog_post(
    post_id: int,
    title: Optional[str] = Form(None),
    content_json: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    featured_image: Optional[str] = Form(None),
    meta_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    meta_keywords: Optional[str] = Form(None),
    focus_keyword: Optional[str] = Form(None),
    canonical_url: Optional[str] = Form(None),
    og_image: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    scheduled_at: Optional[str] = Form(None),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Update blog post (admin only)"""
    try:
        # Build update dynamically
        updates = []
        params = []
        
        content_data = None
        if content_json:
            try:
                content_data = json.loads(content_json)
                updates.append("content_json = $" + str(len(params)+1))
                params.append(json.dumps(content_data))
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid content JSON")
        
        if title:
            updates.append("title = $" + str(len(params)+1))
            params.append(title)
            # Update slug if title changes
            new_slug = re.sub(r'[^\w\s-]', '', title.lower()).strip()
            new_slug = re.sub(r'[-\s]+', '-', new_slug)
            # Ensure unique
            existing = await conn.fetchrow("SELECT id FROM blog_posts WHERE slug = $1 AND id != $2", new_slug, post_id)
            if existing:
                new_slug = f"{new_slug}-{uuid.uuid4().hex[:8]}"
            updates.append("slug = $" + str(len(params)+1))
            params.append(new_slug)
        if excerpt:
            updates.append("excerpt = $" + str(len(params)+1))
            params.append(excerpt)
        if featured_image:
            updates.append("featured_image = $" + str(len(params)+1))
            params.append(featured_image)
        if meta_title:
            updates.append("meta_title = $" + str(len(params)+1))
            params.append(meta_title)
        if meta_description:
            updates.append("meta_description = $" + str(len(params)+1))
            params.append(meta_description)
        if meta_keywords:
            updates.append("meta_keywords = $" + str(len(params)+1))
            params.append(meta_keywords)
        if focus_keyword:
            updates.append("focus_keyword = $" + str(len(params)+1))
            params.append(focus_keyword)
        if canonical_url:
            updates.append("canonical_url = $" + str(len(params)+1))
            params.append(canonical_url)
        if og_image:
            updates.append("og_image = $" + str(len(params)+1))
            params.append(og_image)
        if category:
            updates.append("category = $" + str(len(params)+1))
            params.append(category)
        if tags:
            updates.append("tags = $" + str(len(params)+1))
            params.append([t.strip() for t in tags.split(',')])
        if status:
            updates.append("status = $" + str(len(params)+1))
            params.append(status)
            if status == 'published':
                updates.append("published_at = $" + str(len(params)+1))
                params.append(datetime.utcnow())
                updates.append("scheduled_at = NULL")
            elif status == 'scheduled':
                if not scheduled_at:
                    raise HTTPException(status_code=400, detail="Scheduled date required")
                scheduled_time = datetime.fromisoformat(scheduled_at)
                updates.append("scheduled_at = $" + str(len(params)+1))
                params.append(scheduled_time)
                updates.append("published_at = NULL")
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        updates.append("updated_at = $" + str(len(params)+1))
        params.append(datetime.utcnow())
        
        # Recalculate reading time and SEO if content updated
        if content_data:
            reading_time = calculate_reading_time(content_data)
            updates.append("reading_time = $" + str(len(params)+1))
            params.append(reading_time)
            
            seo_score, _ = calculate_seo_score(content_data, title or '', meta_description or '', focus_keyword or '')
            updates.append("seo_score = $" + str(len(params)+1))
            params.append(seo_score)
        
        params.append(post_id)
        
        await conn.execute(f"""
            UPDATE blog_posts SET {', '.join(updates)} WHERE id = ${len(params)}
        """, *params)
        
        return {"success": True, "message": "Post updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.delete("/admin/posts/{post_id}")
async def delete_blog_post(
    post_id: int,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Delete blog post (admin only)"""
    try:
        await conn.execute("DELETE FROM blog_posts WHERE id = $1", post_id)
        return {"success": True, "message": "Post deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.post("/admin/ai-generate")
async def ai_generate_post(
    topic: str = Form(...),
    keywords: str = Form(None),
    audience: str = Form("traders"),
    tone: str = Form("professional"),
    current_user: str = Depends(get_current_admin)
):
    """AI blog writer for admin"""
    try:
        generated = generate_blog_content(topic, keywords, audience, tone)
        generated['ai_generated'] = True
        return generated
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.post("/admin/seo-score")
async def get_seo_score(
    data: Dict = Body(...),
    current_user: str = Depends(get_current_admin)
):
    """Calculate SEO score for post"""
    try:
        content_json = data.get('content_json', {})
        title = data.get('title', '')
        meta_description = data.get('meta_description', '')
        focus_keyword = data.get('focus_keyword', '')
        
        score, suggestions = calculate_seo_score(content_json, title, meta_description, focus_keyword)
        return {"score": score, "suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.post("/admin/link-suggestions")
async def get_internal_link_suggestions(
    data: Dict = Body(...),
    conn=Depends(get_db),
    current_user: str = Depends(get_current_admin)
):
    """Get internal linking suggestions"""
    try:
        content_json = data.get('content_json', {})
        suggestions = await get_link_suggestions(content_json, conn)
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
