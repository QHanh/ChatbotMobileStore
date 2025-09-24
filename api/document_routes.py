from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Query, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from urllib.parse import quote, urljoin, urlparse
from sqlalchemy.orm import Session
from io import BytesIO
import xml.etree.ElementTree as ET
import requests
import json
import asyncio
from datetime import datetime
from typing import List, Set, Dict
import uuid

from service.data.data_loader_vector_db import (
    get_weaviate_client, 
    process_and_load_text, 
    process_and_load_file, 
    ensure_document_collection_exists,
    ensure_tenant_exists,
    DOCUMENT_CLASS_NAME
)
from service.models.schemas import DocumentInput, DocumentUrlInput
from database.database import get_db, Document
from weaviate.classes.query import Filter
from weaviate.classes.aggregate import GroupByAggregate
from typing import Optional
from service.utils.helpers import sanitize_for_weaviate, get_text_from_url

router = APIRouter()

# Global dictionary to store active crawl tasks
active_crawl_tasks: Dict[str, asyncio.Task] = {}
crawl_task_status: Dict[str, Dict] = {}

@router.post("/upload-text/{customer_id}")
async def upload_text(customer_id: str, doc_input: DocumentInput, db: Session = Depends(get_db)):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        ensure_tenant_exists(client, tenant_id)
        
        source_name = doc_input.source if doc_input.source else doc_input.text[:20]

        # Lưu nội dung gốc vào PostgreSQL
        new_document = Document(
            customer_id=customer_id,
            source_name=source_name,
            full_content=doc_input.text,
            content_type="text/plain"
        )
        db.add(new_document)
        db.commit()

        process_and_load_text(client, doc_input.text, source_name, tenant_id)
        
        return {"message": f"Văn bản từ nguồn '{source_name}' đã được xử lý và thêm vào tenant '{tenant_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Weaviate client is managed by app lifespan; do not close here
        client.close()
        pass

@router.post("/upload-file/{customer_id}")
async def upload_file(customer_id: str, file: UploadFile = File(...), source: Optional[str] = Form(None), db: Session = Depends(get_db)):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        ensure_tenant_exists(client, tenant_id)

        file_content = await file.read()
        source_name = source if source else file.filename
        file_name = quote(file.filename)
        
        # Lưu file gốc vào PostgreSQL
        new_document = Document(
            customer_id=customer_id,
            source_name=source_name,
            file_name=file_name,
            content_type=file.content_type,
            file_content=file_content
        )
        db.add(new_document)
        db.commit()

        process_and_load_file(client, file_content, source_name, file_name, tenant_id)
        
        return {"message": f"Tệp '{file.filename}' đã được xử lý và thêm vào tenant '{tenant_id}' với nguồn là '{source_name}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Weaviate client is managed by app lifespan; do not close here
        client.close()
        pass

@router.post("/upload-url/{customer_id}")
async def upload_url(customer_id: str, doc_input: DocumentUrlInput, db: Session = Depends(get_db)):
    client = None
    try:
        # Fetch text content from the URL
        try:
            text_content = get_text_from_url(doc_input.url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        ensure_tenant_exists(client, tenant_id)
        
        # Always add .url suffix, use custom source or URL as base
        base_name = doc_input.source.strip() if doc_input.source and doc_input.source.strip() else doc_input.url
        source_name = base_name + ".url"

        # Save the original content to PostgreSQL
        new_document = Document(
            customer_id=customer_id,
            source_name=source_name,
            full_content=text_content,
            content_type="text/plain"
        )
        db.add(new_document)
        db.commit()

        process_and_load_text(client, text_content, source_name, tenant_id)
        
        return {"message": f"Content from URL '{doc_input.url}' has been processed and added to tenant '{tenant_id}' as source '{source_name}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Weaviate client is managed by app lifespan; do not close here
        client.close()
        pass

def parse_sitemap(sitemap_url: str) -> List[str]:
    """Parse sitemap XML and extract URLs. Handles both sitemap index and regular sitemaps."""
    try:
        response = requests.get(sitemap_url, timeout=30)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        
        namespaces = {
            'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9'
        }
        
        urls = []
        
        sitemap_elements = root.findall('.//sitemap:sitemap', namespaces)
        if sitemap_elements:
            for sitemap_elem in sitemap_elements:
                loc_elem = sitemap_elem.find('sitemap:loc', namespaces)
                if loc_elem is not None and loc_elem.text:
                    sub_urls = parse_sitemap(loc_elem.text)
                    urls.extend(sub_urls)
        else:
            url_elements = root.findall('.//sitemap:url', namespaces)
            for url_elem in url_elements:
                loc_elem = url_elem.find('sitemap:loc', namespaces)
                if loc_elem is not None and loc_elem.text:
                    urls.append(loc_elem.text)
        
        return urls
    except Exception as e:
        print(f"Error parsing sitemap {sitemap_url}: {e}")
        return []

def parse_robots_txt(base_url: str) -> List[str]:
    """Parse robots.txt to extract sitemap URLs."""
    try:
        parsed_url = urlparse(base_url)
        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        robots_url = f"{base_domain}/robots.txt"
        
        response = requests.get(robots_url, timeout=30)
        response.raise_for_status()
        
        sitemap_urls = []
        for line in response.text.split('\n'):
            line = line.strip()
            if line.lower().startswith('sitemap:'):
                sitemap_url = line.split(':', 1)[1].strip()
                if sitemap_url:
                    sitemap_urls.append(sitemap_url)
        
        return sitemap_urls
    except Exception as e:
        print(f"Error parsing robots.txt for {base_url}: {e}")
        return []

def get_sitemap_urls(base_url: str) -> List[str]:
    """Get all URLs from website sitemap. First tries robots.txt, then common sitemap locations."""
    parsed_url = urlparse(base_url)
    base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    all_urls = []
    
    # Step 1: Try to get sitemap URLs from robots.txt
    print(f"🤖 Checking robots.txt for sitemap URLs...")
    robots_sitemaps = parse_robots_txt(base_url)
    
    if robots_sitemaps:
        print(f"✅ Found {len(robots_sitemaps)} sitemap(s) in robots.txt")
        for sitemap_url in robots_sitemaps:
            try:
                urls = parse_sitemap(sitemap_url)
                if urls:
                    all_urls.extend(urls)
            except Exception as e:
                print(f"Error parsing sitemap from robots.txt {sitemap_url}: {e}")
                continue
    
    # Step 2: If no URLs found from robots.txt, try common sitemap locations
    if not all_urls:
        print(f"🔍 No sitemaps found in robots.txt, trying common locations...")
        sitemap_locations = [
            f"{base_domain}/sitemap.xml",
            f"{base_domain}/sitemap_index.xml",
            f"{base_domain}/sitemaps.xml",
            f"{base_url.rstrip('/')}/sitemap.xml"
        ]
        
        for sitemap_url in sitemap_locations:
            try:
                urls = parse_sitemap(sitemap_url)
                if urls:
                    print(f"✅ Found sitemap at: {sitemap_url}")
                    all_urls.extend(urls)
                    break
            except:
                continue
    
    # Remove duplicates
    seen = set()
    unique_urls = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls

async def crawl_url_content(url: str) -> tuple[str, str]:
    """Crawl content from a single URL. Returns (url, content)."""
    try:
        content = get_text_from_url(url)
        return url, content
    except Exception as e:
        print(f"Error crawling {url}: {e}")
        return url, ""

@router.post("/upload-sitemap/{customer_id}")
async def upload_sitemap(customer_id: str, website_url: str = Form(...), source: Optional[str] = Form(None), db: Session = Depends(get_db)):
    """
    Crawl website sitemap and upload all found URLs as documents.
    Streams progress in real-time.
    Returns task_id for cancellation support.
    """
    # Generate unique task ID
    task_id = str(uuid.uuid4())
    
    async def generate_progress():
        client = None
        try:
            tenant_id = sanitize_for_weaviate(customer_id)
            client = get_weaviate_client()
            ensure_document_collection_exists(client)
            ensure_tenant_exists(client, tenant_id)
            
            # Initialize task status
            crawl_task_status[task_id] = {
                'status': 'running',
                'customer_id': customer_id,
                'website_url': website_url,
                'start_time': datetime.now().isoformat(),
                'progress': 0,
                'total_urls': 0,
                'success_count': 0,
                'failed_count': 0
            }
            
            # Step 1: Get sitemap URLs
            yield f"data: {json.dumps({'status': 'discovering', 'task_id': task_id, 'message': f'🔍 Đang tìm sitemap cho {website_url}...'})}\n\n"
            
            urls = get_sitemap_urls(website_url)
            total_urls = len(urls)
            
            if total_urls == 0:
                yield f"data: {json.dumps({'status': 'error', 'message': '❌ Không tìm thấy sitemap hoặc sitemap trống'})}\n\n"
                return
            
            yield f"data: {json.dumps({'status': 'found', 'message': f'✅ Tìm thấy {total_urls} URLs trong sitemap', 'total_urls': total_urls})}\n\n"
            
            # Step 2: Crawl each URL and collect all content
            processed_count = 0
            success_count = 0
            failed_count = 0
            all_crawled_content = []  # Store all successful crawls
            
            # Determine source name once
            if source:
                source_name = source + '.url'
            else:
                parsed_website = urlparse(website_url)
                domain_name = parsed_website.netloc.replace('www.', '')
                source_name = f"sitemap_{domain_name}.url"
            
            for i, url in enumerate(urls, 1):
                # Check if task was cancelled
                if task_id in crawl_task_status and crawl_task_status[task_id]['status'] == 'cancelled':
                    yield f"data: {json.dumps({'status': 'cancelled', 'message': '🛑 Crawl đã bị dừng bởi người dùng'})}\n\n"
                    return
                
                try:
                    # Update progress
                    crawl_task_status[task_id].update({
                        'progress': i,
                        'total_urls': total_urls,
                        'current_url': url
                    })
                    
                    yield f"data: {json.dumps({'status': 'crawling', 'task_id': task_id, 'current_url': url, 'progress': i, 'total': total_urls, 'message': f'🔄 Đang crawl ({i}/{total_urls}): {url}'})}\n\n"
                    
                    # Crawl content
                    _, content = await crawl_url_content(url)
                    
                    if content.strip():
                        # Store content with URL info for later aggregation
                        content_with_url = f"URL: {url}\n\n{content}"
                        all_crawled_content.append(content_with_url)
                        
                        # Still process and load to vector DB individually for better search
                        enhanced_content = f"Trang web: {url}\nNội dung:\n{content}"
                        process_and_load_text(client, enhanced_content, source_name, tenant_id)
                        
                        success_count += 1
                        crawl_task_status[task_id]['success_count'] = success_count
                        yield f"data: {json.dumps({'status': 'success', 'task_id': task_id, 'current_url': url, 'progress': i, 'total': total_urls, 'success_count': success_count, 'message': f'✅ Thành công ({i}/{total_urls}): {url}'})}\n\n"
                    else:
                        failed_count += 1
                        crawl_task_status[task_id]['failed_count'] = failed_count
                        yield f"data: {json.dumps({'status': 'failed', 'task_id': task_id, 'current_url': url, 'progress': i, 'total': total_urls, 'failed_count': failed_count, 'message': f'⚠️ Không có nội dung ({i}/{total_urls}): {url}'})}\n\n"
                
                except Exception as e:
                    failed_count += 1
                    crawl_task_status[task_id]['failed_count'] = failed_count
                    yield f"data: {json.dumps({'status': 'failed', 'task_id': task_id, 'current_url': url, 'progress': i, 'total': total_urls, 'failed_count': failed_count, 'error': str(e), 'message': f'❌ Lỗi ({i}/{total_urls}): {url} - {str(e)}'})}\n\n"
                
                processed_count += 1
                
                # Small delay to prevent overwhelming the server
                await asyncio.sleep(0.1)
            
            # Step 3: Save all content as ONE record in PostgreSQL
            if all_crawled_content:
                # Combine all content with separators
                combined_content = f"SITEMAP CRAWL SUMMARY\n"
                combined_content += f"Website: {website_url}\n"
                combined_content += f"Total URLs crawled: {success_count}\n"
                combined_content += f"Crawl date: {datetime.now().isoformat()}\n"
                combined_content += f"\n{'='*80}\n\n"
                combined_content += "\n\n" + "="*80 + "\n\n".join(all_crawled_content)
                
                # Save single record to PostgreSQL
                new_document = Document(
                    customer_id=customer_id,
                    source_name=source_name,
                    full_content=combined_content,
                    content_type="text/html"
                )
                db.add(new_document)
                
                yield f"data: {json.dumps({'status': 'saving', 'message': f'💾 Đang lưu tổng hợp {success_count} URLs vào database...'})}\n\n"
            
            # Commit all changes
            db.commit()
            
            # Final summary
            crawl_task_status[task_id]['status'] = 'completed'
            crawl_task_status[task_id]['end_time'] = datetime.now().isoformat()
            yield f"data: {json.dumps({'status': 'completed', 'task_id': task_id, 'total_urls': total_urls, 'success_count': success_count, 'failed_count': failed_count, 'message': f'🎉 Hoàn thành! Đã crawl {success_count}/{total_urls} URLs thành công cho khách hàng {customer_id}'})}\n\n"
            
        except Exception as e:
            crawl_task_status[task_id]['status'] = 'error'
            crawl_task_status[task_id]['error'] = str(e)
            yield f"data: {json.dumps({'status': 'error', 'task_id': task_id, 'message': f'❌ Lỗi hệ thống: {str(e)}'})}\n\n"
        finally:
            if client:
                client.close()
            # Clean up task from active tasks
            if task_id in active_crawl_tasks:
                del active_crawl_tasks[task_id]
    
    # Store the task for potential cancellation
    task = asyncio.create_task(generate_progress().__anext__())
    active_crawl_tasks[task_id] = task
    
    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "X-Task-ID": task_id,  # Return task ID in header
        }
    )

@router.post("/cancel-crawl/{task_id}")
async def cancel_crawl(task_id: str):
    """
    Cancel an active crawl task.
    """
    if task_id not in crawl_task_status:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    if crawl_task_status[task_id]['status'] in ['completed', 'error', 'cancelled']:
        return {"message": f"Task {task_id} is already {crawl_task_status[task_id]['status']}", "task_id": task_id}
    
    # Mark task as cancelled
    crawl_task_status[task_id]['status'] = 'cancelled'
    crawl_task_status[task_id]['cancelled_at'] = datetime.now().isoformat()
    
    # Cancel the asyncio task if it exists
    if task_id in active_crawl_tasks:
        active_crawl_tasks[task_id].cancel()
        del active_crawl_tasks[task_id]
    
    return {"message": f"Task {task_id} has been cancelled", "task_id": task_id}

@router.get("/crawl-status/{task_id}")
async def get_crawl_status(task_id: str):
    """
    Get the status of a crawl task.
    """
    if task_id not in crawl_task_status:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return crawl_task_status[task_id]

@router.get("/active-crawls")
async def get_active_crawls():
    """
    Get all active crawl tasks.
    """
    active_tasks = {
        task_id: status for task_id, status in crawl_task_status.items()
        if status['status'] == 'running'
    }
    return {"active_tasks": active_tasks, "count": len(active_tasks)}

@router.get("/document-original/{customer_id}")
async def get_original_document(
    customer_id: str, 
    source: str = Query(..., description="Tên 'source' của tài liệu cần lấy."),
    db: Session = Depends(get_db)
):
    """
    Lấy lại nội dung gốc của một tài liệu (text hoặc file) đã được upload.
    """
    document = db.query(Document).filter(
        Document.customer_id == customer_id,
        Document.source_name == source
    ).order_by(Document.created_at.desc()).first()

    if not document:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài liệu với source '{source}' cho khách hàng '{customer_id}'.")

    if document.file_content:
        # Trả về file với header hỗ trợ Unicode theo RFC 5987
        filename = document.file_name or "download"
        encoded = quote(filename)
        content_disposition = f"attachment; filename*=UTF-8''{encoded}"
        return StreamingResponse(
            BytesIO(document.file_content),
            media_type=document.content_type,
            headers={"Content-Disposition": content_disposition}
        )
    elif document.full_content:
        # Trả về text
        return JSONResponse(
            content={
                "customer_id": document.customer_id,
                "source_name": document.source_name,
                "content": document.full_content,
                "created_at": document.created_at.isoformat()
            }
        )
    else:
        raise HTTPException(status_code=404, detail="Tài liệu không có nội dung.")

@router.get("/documents/{customer_id}")
async def list_documents(customer_id: str, limit: int = 100, offset: int = 0):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id not in tenants:
            return {"items": [], "count": 0}
            
        tenant_collection = collection.with_tenant(tenant_id)
        
        # Bỏ return_properties để đảm bảo tất cả thuộc tính được trả về
        result = tenant_collection.query.fetch_objects(limit=limit, offset=offset)
        
        items = [{"id": obj.uuid, "text": obj.properties.get("text"), "source": obj.properties.get("source")} for obj in result.objects]
        return {"items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Weaviate client is managed by app lifespan; do not close here
        client.close()
        pass

@router.get("/sources/{customer_id}")
async def list_document_sources(customer_id: str):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id not in tenants:
            return {"sources": []}
        
        tenant_collection = collection.with_tenant(tenant_id)
        
        # Sử dụng aggregation để lấy các source duy nhất một cách hiệu quả
        result = tenant_collection.aggregate.over_all(
            group_by=GroupByAggregate(prop="source", limit=1000)
        )
        
        sources = sorted([group.grouped_by.value for group in result.groups])
        return {"sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Weaviate client is managed by app lifespan; do not close here
        client.close()
        pass

@router.delete("/sources/{customer_id}")
async def delete_document_by_source(customer_id: str, source: str = Query(..., description="Tên 'source' của tài liệu cần xóa.")):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id not in tenants:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy tenant: {tenant_id}")
            
        tenant_collection = collection.with_tenant(tenant_id)
        result = tenant_collection.data.delete_many(where=Filter.by_property("source").equal(source))
        
        if result.failed > 0:
            raise HTTPException(status_code=500, detail=f"Xóa tài liệu thất bại với {result.failed} lỗi.")
        return {"message": f"Đã xóa thành công {result.successful} chunk của tài liệu '{source}' từ tenant '{tenant_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Weaviate client is managed by app lifespan; do not close here
        client.close()
        pass

@router.delete("/documents/{customer_id}")
async def delete_all_documents(customer_id: str, db: Session = Depends(get_db)):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id in tenants:
            collection.tenants.remove([tenant_id])
            
        # Xóa cả trong PostgreSQL
        db.query(Document).filter(Document.customer_id == customer_id).delete()
        db.commit()
            
        return {"message": f"Đã xóa thành công toàn bộ dữ liệu (tenant và bản ghi DB) của khách hàng '{customer_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()