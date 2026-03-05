# blog_routes.py
from fastapi import APIRouter, Depends, HTTPException, Form, Query, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List, Dict
from datetime import datetime
import json
import re
import uuid

# Import from dependencies (not main) to avoid circular import
from dependencies import get_db, get_current_admin, get_current_user

# Import AI tools
from ai_blog_tools import generate_blog_content, calculate_seo_score, get_link_suggestions, calculate_reading_time

blog_router = APIRouter(tags=["blog"])

# Helper to render JSON content to HTML for server-side rendering
def render_content_blocks(blocks: List[dict]) -> str:
    html = ""
    for block in blocks:
        block_type = block.get('type')
        data = block.get('data')
        
        if block_type == 'header':
            level = data.get('level', 1)
            html += f"<h{level} class='blog-heading'>{data.get('text', '')}</h{level}>\n"
        elif block_type == 'paragraph':
            text = data.get('text', '')
            # Convert URLs to links
            text = re.sub(r'(https?://\S+)', r'<a href="\1" target="_blank">\1</a>', text)
            html += f"<p class='blog-paragraph'>{text}</p>\n"
        elif block_type == 'list':
            style = data.get('style')
            items = data.get('items', [])
            tag = 'ul' if style == 'unordered' else 'ol'
            html += f"<{tag} class='blog-list'>\n"
            for item in items:
                html += f"<li>{item}</li>\n"
            html += f"</{tag}>\n"
        elif block_type == 'quote':
            html += f"<blockquote class='blog-quote'>\n"
            html += f"<p>{data.get('text', '')}</p>\n"
            if data.get('caption'):
                html += f"<cite>{data['caption']}</cite>\n"
            html += f"</blockquote>\n"
        elif block_type == 'table':
            content = data.get('content', [])
            html += "<table class='blog-table'>\n"
            for i, row in enumerate(content):
                html += "<tr>\n"
                tag = 'th' if i == 0 else 'td'
                for cell in row:
                    html += f"<{tag}>{cell}</{tag}>\n"
                html += "</tr>\n"
            html += "</table>\n"
        elif block_type == 'code':
            html += f"<pre class='blog-code'><code>{data.get('code', '')}</code></pre>\n"
        elif block_type == 'image':
            url = data.get('file', {}).get('url', '')
            caption = data.get('caption', '')
            alt = data.get('alt', caption) or caption
            html += f"<figure class='blog-figure'>\n"
            html += f"<img src=\"{url}\" alt=\"{alt}\" class='blog-image' />\n"
            if caption:
                html += f"<figcaption>{caption}</figcaption>\n"
            html += f"</figure>\n"
        elif block_type == 'embed':
            url = data.get('embed', '')
            html += f"<div class='blog-embed'>\n"
            html += f"<iframe src=\"{url}\" width=\"100%\" height=\"400\" frameborder=\"0\" allowfullscreen></iframe>\n"
            html += f"</div>\n"
        elif block_type == 'delimiter':
            html += "<hr class='blog-divider' />\n"
        elif block_type == 'tradingview':
            symbol = data.get('symbol', 'FX:EURUSD')
            html += f"<div class='tradingview-widget-container'>\n"
            html += f"<iframe src=\"https://s.tradingview.com/widgetembed/?frameElementId=tradingview_{uuid.uuid4().hex[:8]}&symbol={symbol}&interval=D&hidesidetoolbar=1&symboledit=1&saveimage=1&toolbarbg=f1f3f6&studies=[]&hideideas=1&theme=light&style=1&timezone=exchange&studies_overrides={{}}&overrides={{}}&enabled_features=[]&disabled_features=[]&locale=en&utm_source=pipways.com&utm_medium=widget&utm_campaign=chart&utm_term={symbol}\" width=\"100%\" height=\"500\" frameborder=\"0\" allowfullscreen></iframe>\n"
            html += f"</div>\n"
    
    return html

# Helper to generate Article schema
def generate_article_schema(post: dict, base_url: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post['title'],
        "author": {
            "@type": "Person",
            "name": post.get('author_name', 'Pipways Team')
        },
        "datePublished": post['published_at'].isoformat() if post['published_at'] else None,
        "dateModified": post['updated_at'].isoformat() if post.get('updated_at') else None,
        "image": post['featured_image'],
        "publisher": {
            "@type": "Organization",
            "name": "Pipways",
            "logo": {
                "@type": "ImageObject",
                "url": f"{base_url}/logo.png"
            }
        },
        "url": f"{base_url}/blog/{post['slug']}",
        "description": post['meta_description'] or post['excerpt'],
        "keywords": post['meta_keywords'],
        "articleSection": post['category'],
        "wordCount": post.get('word_count', 0)
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
            SELECT 
                p.id, p.title, p.slug, p.excerpt, p.featured_image, p.category, p.tags,
                p.meta_title, p.meta_description, p.published_at, p.view_count, 
                p.created_at, p.reading_time, p.seo_score, p.ai_generated,
                u.name as author_name
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
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
            SELECT p.*, u.name as author_name 
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE p.slug = $1 AND p.status = 'published'
            AND (p.published_at <= NOW() OR p.published_at IS NULL)
        """, slug)

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Increment view count
        await conn.execute("""
            UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1
        """, post['id'])
        
        # Get related posts
        related = await conn.fetch("""
            SELECT id, title, slug, featured_image, excerpt, category
            FROM blog_posts
            WHERE status = 'published' 
            AND id != $1
            AND (category = $2 OR $3 = ANY(tags))
            ORDER BY published_at DESC
            LIMIT 3
        """, post['id'], post['category'], post['category'])
        
        result = dict(post)
        result['related_posts'] = [dict(r) for r in related]
        
        return result
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
            SELECT p.*, u.name as author_name 
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE p.slug = $1 AND p.status = 'published'
            AND (p.published_at <= NOW() OR p.published_at IS NULL)
        """, slug)

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Handle scheduled posts that should be published now
        if post['status'] == 'scheduled' and post['scheduled_at'] and post['scheduled_at'] <= datetime.utcnow():
            await conn.execute("""
                UPDATE blog_posts SET status = 'published', published_at = $1 WHERE id = $2
            """, post['scheduled_at'], post['id'])
            post = await conn.fetchrow("""
                SELECT p.*, u.name as author_name 
                FROM blog_posts p
                LEFT JOIN users u ON p.author_id = u.id
                WHERE p.id = $1
            """, post['id'])
        
        # Increment view count
        await conn.execute("UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1", post['id'])
        
        # Get related posts
        related = await conn.fetch("""
            SELECT id, title, slug, featured_image, excerpt, category
            FROM blog_posts
            WHERE status = 'published' 
            AND id != $1
            AND (category = $2 OR $3 = ANY(tags))
            ORDER BY published_at DESC
            LIMIT 3
        """, post['id'], post['category'], post['category'])
        
        base_url = str(request.base_url).rstrip('/')
        content_blocks = post['content_json'].get('blocks', []) if post['content_json'] else []
        content_html = render_content_blocks(content_blocks)
        schema = generate_article_schema(dict(post), base_url)
        
        # Calculate word count
        word_count = sum(
            len(block.get('data', {}).get('text', '').split())
            for block in content_blocks
            if block.get('type') in ['paragraph', 'header']
        )
        
        # Generate related posts HTML
        related_html = ""
        for rel in related:
            related_html += f"""
            <article class="related-post">
                <a href="/blog/{rel['slug']}">
                    <img src="{rel['featured_image'] or '/default-image.jpg'}" alt="{rel['title']}">
                    <h3>{rel['title']}</h3>
                    <p>{rel['excerpt'] or ''}</p>
                </a>
            </article>
            """
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{post['meta_title'] or post['title']}</title>
    <meta name="description" content="{post['meta_description'] or post['excerpt'] or ''}">
    <meta name="keywords" content="{post['meta_keywords'] or ''}">
    <link rel="canonical" href="{post['canonical_url'] or f'{base_url}/blog/{slug}'}">
    
    <!-- Open Graph -->
    <meta property="og:title" content="{post['meta_title'] or post['title']}">
    <meta property="og:description" content="{post['meta_description'] or post['excerpt'] or ''}">
    <meta property="og:image" content="{post['og_image'] or post['featured_image'] or ''}">
    <meta property="og:url" content="{base_url}/blog/{slug}">
    <meta property="og:type" content="article">
    
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{post['meta_title'] or post['title']}">
    <meta name="twitter:description" content="{post['meta_description'] or post['excerpt'] or ''}">
    <meta name="twitter:image" content="{post['og_image'] or post['featured_image'] or ''}">
    
    <!-- Schema.org JSON-LD -->
    <script type="application/ld+json">
    {json.dumps(schema, default=str)}
    </script>
    
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
        .blog-header {{ margin-bottom: 30px; }}
        .blog-title {{ font-size: 2.5em; margin-bottom: 10px; }}
        .blog-meta {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
        .blog-meta span {{ margin-right: 15px; }}
        .featured-image {{ width: 100%; max-height: 400px; object-fit: cover; border-radius: 8px; margin-bottom: 30px; }}
        .blog-content {{ font-size: 1.1em; }}
        .blog-heading {{ margin-top: 40px; margin-bottom: 20px; }}
        .blog-paragraph {{ margin-bottom: 20px; }}
        .blog-list {{ margin-bottom: 20px; }}
        .blog-quote {{ border-left: 4px solid #007bff; padding-left: 20px; margin: 20px 0; font-style: italic; }}
        .blog-figure {{ margin: 30px 0; }}
        .blog-image {{ max-width: 100%; border-radius: 8px; }}
        .tags {{ margin-top: 30px; }}
        .tag {{ display: inline-block; background: #f0f0f0; padding: 5px 15px; border-radius: 20px; margin-right: 10px; margin-bottom: 10px; font-size: 0.9em; }}
        .social-share {{ margin-top: 40px; padding-top: 30px; border-top: 1px solid #eee; }}
        .share-buttons {{ display: flex; gap: 10px; margin-top: 15px; }}
        .share-btn {{ padding: 10px 20px; border-radius: 5px; text-decoration: none; color: white; }}
        .share-twitter {{ background: #1da1f2; }}
        .share-linkedin {{ background: #0077b5; }}
        .share-facebook {{ background: #4267B2; }}
        .related-posts {{ margin-top: 50px; padding-top: 30px; border-top: 2px solid #eee; }}
        .related-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-top: 20px; }}
        .related-post {{ border: 1px solid #eee; border-radius: 8px; overflow: hidden; }}
        .related-post img {{ width: 100%; height: 150px; object-fit: cover; }}
        .related-post h3 {{ padding: 15px; margin: 0; font-size: 1.1em; }}
        .related-post p {{ padding: 0 15px 15px; margin: 0; color: #666; font-size: 0.9em; }}
        .reading-time {{ color: #007bff; }}
        @media (max-width: 600px) {{ .blog-title {{ font-size: 1.8em; }} }}
    </style>
</head>
<body>
    <article>
        <header class="blog-header">
            <h1 class="blog-title">{post['title']}</h1>
            <div class="blog-meta">
                <span>By {post.get('author_name', 'Pipways Team')}</span>
                <span>{post['published_at'].strftime('%B %d, %Y') if post['published_at'] else 'Draft'}</span>
                <span class="reading-time">{post['reading_time'] or 5} min read</span>
                <span>{post['view_count'] or 0} views</span>
            </div>
            {f'<img src="{post["featured_image"]}" alt="{post["title"]}" class="featured-image">' if post['featured_image'] else ''}
        </header>
        
        <div class="blog-content">
            {content_html}
        </div>
        
        <div class="tags">
            <strong>Tags:</strong>
            {''.join([f'<span class="tag">{tag}</span>' for tag in (post['tags'] or [])])}
        </div>
        
        <div class="social-share">
            <h3>Share this article</h3>
            <div class="share-buttons">
                <a href="https://twitter.com/intent/tweet?url={base_url}/blog/{slug}&text={post['title']}" target="_blank" class="share-btn share-twitter">Twitter</a>
                <a href="https://www.linkedin.com/shareArticle?mini=true&url={base_url}/blog/{slug}&title={post['title']}" target="_blank" class="share-btn share-linkedin">LinkedIn</a>
                <a href="https://www.facebook.com/sharer/sharer.php?u={base_url}/blog/{slug}" target="_blank" class="share-btn share-facebook">Facebook</a>
            </div>
        </div>
    </article>
    
    <section class="related-posts">
        <h2>Related Articles</h2>
        <div class="related-grid">
            {related_html}
        </div>
    </section>
</body>
</html>"""
        return HTMLResponse(content=html)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.post("/admin/posts")
async def create_blog_post(
    title: str = Form(...),
    content_json: str = Form(...),
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
    scheduled_at: Optional[str] = Form(None),
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
            full_text = ' '.join([
                b.get('data', {}).get('text', '') 
                for b in content_data.get('blocks', []) 
                if 'text' in b.get('data', {})
            ])
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
            scheduled_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            if scheduled_time <= datetime.utcnow():
                status = 'published'
                published_at = scheduled_time
        
        # Calculate reading time
        reading_time = calculate_reading_time(content_data)
        
        # Calculate SEO score
        seo_score, suggestions = calculate_seo_score(content_data, title, meta_description, focus_keyword)
        
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        post_id = await conn.fetchval("""
            INSERT INTO blog_posts 
            (title, slug, content_json, excerpt, featured_image, meta_title, meta_description,
             meta_keywords, focus_keyword, canonical_url, og_image, author_id, category, tags, status, 
             published_at, scheduled_at, reading_time, seo_score, content)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
            RETURNING id
        """,
            title, slug, json.dumps(content_data), excerpt, featured_image, meta_title, meta_description,
            meta_keywords, focus_keyword, canonical_url, og_image, user["id"], category, tag_list, status, 
            published_at, scheduled_time, reading_time, seo_score,
            json.dumps(content_data)  # Store JSON in content field for backward compatibility
        )
        
        return {
            "success": True,
            "post_id": post_id,
            "slug": slug,
            "seo_score": seo_score,
            "seo_suggestions": suggestions,
            "reading_time": reading_time,
            "message": "Post created successfully"
        }
    except HTTPException:
        raise
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
                # Also update content field for backward compatibility
                updates.append("content = $" + str(len(params)+1))
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
                scheduled_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
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
            
            # Get current title and meta for SEO calculation
            current = await conn.fetchrow("SELECT title, meta_description, focus_keyword FROM blog_posts WHERE id = $1", post_id)
            seo_score, _ = calculate_seo_score(
                content_data, 
                title or current['title'] or '', 
                meta_description or current['meta_description'] or '', 
                focus_keyword or current['focus_keyword'] or ''
            )
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

@blog_router.get("/admin/posts")
async def list_admin_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """List all posts for admin with filtering"""
    try:
        offset = (page - 1) * per_page
        params = []
        where_clauses = []

        if status:
            where_clauses.append(f"status = ${len(params)+1}")
            params.append(status)
        
        if search:
            where_clauses.append(f"(title ILIKE ${len(params)+1} OR slug ILIKE ${len(params)+1})")
            params.append(f"%{search}%")
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        posts = await conn.fetch(f"""
            SELECT 
                p.id, p.title, p.slug, p.status, p.category, 
                p.published_at, p.scheduled_at, p.view_count,
                p.seo_score, p.reading_time, p.ai_generated,
                p.created_at, p.updated_at,
                u.name as author_name
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ${len(params)+1} OFFSET ${len(params)+2}
        """, *params, per_page, offset)
        
        count = await conn.fetchrow(f"""
            SELECT COUNT(*) as total FROM blog_posts WHERE {where_sql}
        """, *params)
        
        return {
            "posts": [dict(p) for p in posts],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": count['total'] if count else 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.get("/admin/posts/{post_id}")
async def get_admin_post_detail(
    post_id: int,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Get full post details for admin editing"""
    try:
        post = await conn.fetchrow("""
            SELECT p.*, u.name as author_name 
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE p.id = $1
        """, post_id)

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Get link suggestions
        content_json = post['content_json'] if post['content_json'] else {}
        link_suggestions = await get_link_suggestions(content_json, conn)
        
        result = dict(post)
        result['link_suggestions'] = link_suggestions
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.post("/admin/ai-generate")
async def ai_generate_blog_content(
    topic: str = Form(...),
    keywords: Optional[str] = Form(None),
    audience: str = Form("beginner"),
    tone: str = Form("professional"),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Generate AI blog content"""
    try:
        content = generate_blog_content(topic, keywords, audience, tone)
        return {
            "success": True,
            "content": content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.post("/admin/analyze-seo")
async def analyze_seo_endpoint(
    content_json: str = Form(...),
    title: str = Form(...),
    meta_description: Optional[str] = Form(""),
    focus_keyword: Optional[str] = Form(""),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Analyze SEO score for content"""
    try:
        data = json.loads(content_json)
        score, suggestions = calculate_seo_score(data, title, meta_description, focus_keyword)
        return {
            "success": True,
            "seo_score": score,
            "suggestions": suggestions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.get("/admin/link-suggestions")
async def get_internal_link_suggestions(
    content_json: str = Query(...),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Get internal link suggestions based on content"""
    try:
        data = json.loads(content_json)
        suggestions = await get_link_suggestions(data, conn)
        return {
            "success": True,
            "suggestions": suggestions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.get("/categories")
async def get_blog_categories(conn=Depends(get_db)):
    """Get all blog categories"""
    try:
        categories = await conn.fetch("SELECT * FROM blog_categories ORDER BY name")
        return [dict(c) for c in categories]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@blog_router.get("/tags")
async def get_blog_tags(conn=Depends(get_db)):
    """Get all unique tags"""
    try:
        result = await conn.fetch("SELECT DISTINCT unnest(tags) as tag FROM blog_posts WHERE status = 'published'")
        return [r['tag'] for r in result if r['tag']]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
