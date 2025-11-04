from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Query, Depends, BackgroundTasks
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

 
from service.models.schemas import DocumentInput, DocumentUrlInput
from database.database import get_db, Document, SessionLocal
from typing import Optional
from service.utils.helpers import get_text_from_url
from service.graphrag.graphrag_service import (
    workspace_path_for_customer,
    ensure_workspace_initialized,
    export_documents,
    run_index,
    persist_output_to_db,
    configure_input_for_json,
    configure_cache_short_base,
)

router = APIRouter()

# Global dictionary to store active crawl tasks
active_crawl_tasks: Dict[str, asyncio.Task] = {}
crawl_task_status: Dict[str, Dict] = {}

def _reindex_graphrag_for_customer(customer_id: str):
    root = workspace_path_for_customer(customer_id)
    ensure_workspace_initialized(root)
    configure_cache_short_base(root)
    configure_input_for_json(root)
    db1 = SessionLocal()
    try:
        export_documents(db1, customer_id, root)
    finally:
        db1.close()
    ok = run_index(root, "fast")
    if ok:
        db2 = SessionLocal()
        try:
            persist_output_to_db(db2, customer_id, root, overwrite=True)
        finally:
            db2.close()

@router.post("/upload-text/{customer_id}")
async def upload_text(customer_id: str, doc_input: DocumentInput, db: Session = Depends(get_db), background: BackgroundTasks = None):
    try:
        source_name = doc_input.source if doc_input.source else doc_input.text[:20]
        new_document = Document(
            customer_id=customer_id,
            source_name=source_name,
            full_content=doc_input.text,
            content_type="text/plain"
        )
        db.add(new_document)
        db.commit()
        if background is not None:
            background.add_task(_reindex_graphrag_for_customer, customer_id)
        return {"message": f"Đã nhận văn bản '{source_name}'. Đang chạy GraphRAG để lập chỉ mục."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-file/{customer_id}")
async def upload_file(customer_id: str, file: UploadFile = File(...), source: Optional[str] = Form(None), db: Session = Depends(get_db), background: BackgroundTasks = None):
    try:
        file_content = await file.read()
        source_name = source if source else file.filename
        file_name = quote(file.filename)
        new_document = Document(
            customer_id=customer_id,
            source_name=source_name,
            file_name=file_name,
            content_type=file.content_type,
            file_content=file_content
        )
        db.add(new_document)
        db.commit()
        if background is not None:
            background.add_task(_reindex_graphrag_for_customer, customer_id)
        return {"message": f"Tệp '{file.filename}' đã được ghi nhận với nguồn '{source_name}'. Đang chạy GraphRAG để lập chỉ mục."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-url/{customer_id}")
async def upload_url(customer_id: str, doc_input: DocumentUrlInput, db: Session = Depends(get_db), background: BackgroundTasks = None):
    try:
        try:
            text_content = get_text_from_url(doc_input.url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        base_name = doc_input.source.strip() if doc_input.source and doc_input.source.strip() else doc_input.url
        source_name = base_name + ".url"
        new_document = Document(
            customer_id=customer_id,
            source_name=source_name,
            full_content=text_content,
            content_type="text/plain"
        )
        db.add(new_document)
        db.commit()
        if background is not None:
            background.add_task(_reindex_graphrag_for_customer, customer_id)
        return {"message": f"Đã nhận nội dung từ URL '{doc_input.url}' dưới nguồn '{source_name}'. Đang chạy GraphRAG để lập chỉ mục."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@router.post("/start-sitemap-crawl/{customer_id}")
async def start_sitemap_crawl(customer_id: str, website_url: str = Form(...), source: Optional[str] = Form(None)):
    """
    Start a sitemap crawl task and return task_id immediately.
    Use the task_id to get progress via /sitemap-progress/{task_id} or cancel via /cancel-crawl/{task_id}
    """
    # Generate unique task ID
    task_id = str(uuid.uuid4())
    
    # Initialize task status
    crawl_task_status[task_id] = {
        'status': 'initialized',
        'customer_id': customer_id,
        'website_url': website_url,
        'source': source,
        'start_time': datetime.now().isoformat(),
        'progress': 0,
        'total_urls': 0,
        'success_count': 0,
        'failed_count': 0
    }
    
    return {
        "task_id": task_id,
        "message": f"Crawl task created for {website_url}",
        "progress_url": f"/sitemap-progress/{task_id}",
        "cancel_url": f"/cancel-crawl/{task_id}",
        "status_url": f"/crawl-status/{task_id}"
    }

@router.get("/sitemap-progress/{task_id}")
async def get_sitemap_progress(task_id: str, db: Session = Depends(get_db)):
    """
    Stream progress for a specific crawl task.
    """
    if task_id not in crawl_task_status:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    task_info = crawl_task_status[task_id]
    customer_id = task_info['customer_id']
    website_url = task_info['website_url']
    source = task_info.get('source')
    
    async def generate_progress():
        client = None
        try:
            crawl_task_status[task_id].update({
                'status': 'running',
                'actual_start_time': datetime.now().isoformat()
            })
            
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
            
            # Create initial PostgreSQL record
            initial_content = f"SITEMAP CRAWL SUMMARY\n"
            initial_content += f"Website: {website_url}\n"
            initial_content += f"Total URLs to crawl: {total_urls}\n"
            initial_content += f"Crawl started: {datetime.now().isoformat()}\n"
            initial_content += f"Status: In Progress...\n"
            initial_content += f"\n{'='*80}\n\n"
            
            new_document = Document(
                customer_id=customer_id,
                source_name=source_name,
                full_content=initial_content,
                content_type="text/html"
            )
            db.add(new_document)
            db.commit()
            document_id = new_document.id
            
            for i, url in enumerate(urls, 1):
                if task_id in crawl_task_status and crawl_task_status[task_id]['status'] == 'cancelled':
                    cancelled_content = f"SITEMAP CRAWL SUMMARY\n"
                    cancelled_content += f"Website: {website_url}\n"
                    cancelled_content += f"Total URLs to crawl: {total_urls}\n"
                    cancelled_content += f"Crawl started: {datetime.now().isoformat()}\n"
                    cancelled_content += f"Status: CANCELLED by user\n"
                    cancelled_content += f"Success: {success_count}, Failed: {failed_count}\n"
                    cancelled_content += f"Cancelled at URL {i}/{total_urls}: {url if 'url' in locals() else 'N/A'}\n"
                    cancelled_content += f"Cancelled time: {datetime.now().isoformat()}\n"
                    cancelled_content += f"\n{'='*80}\n\n"
                    if all_crawled_content:
                        cancelled_content += "\n\n" + "="*80 + "\n\n".join(all_crawled_content)
                    
                    db.query(Document).filter(Document.id == document_id).update({
                        Document.full_content: cancelled_content
                    })
                    db.commit()
                    
                    yield f"data: {json.dumps({'status': 'cancelled', 'message': f'🛑 Crawl đã bị dừng bởi người dùng. Đã lưu {success_count} URLs thành công.'})}\n\n"
                    return
                
                try:
                    # Update progress
                    crawl_task_status[task_id].update({
                        'progress': i,
                        'total_urls': total_urls,
                        'current_url': url
                    })
                    
                    yield f"data: {json.dumps({'status': 'crawling', 'task_id': task_id, 'current_url': url, 'progress': i, 'total': total_urls, 'message': f'🔄 Đang crawl ({i}/{total_urls}): {url}'})}\n\n"
                    
                    _, content = await crawl_url_content(url)
                    
                    if content.strip():
                        content_with_url = f"URL: {url}\n\n{content}"
                        all_crawled_content.append(content_with_url)
                        
                        success_count += 1
                        crawl_task_status[task_id]['success_count'] = success_count
                        
                        updated_content = f"SITEMAP CRAWL SUMMARY\n"
                        updated_content += f"Website: {website_url}\n"
                        updated_content += f"Total URLs to crawl: {total_urls}\n"
                        updated_content += f"Crawl started: {datetime.now().isoformat()}\n"
                        updated_content += f"Status: In Progress... ({success_count}/{total_urls} completed)\n"
                        updated_content += f"Success: {success_count}, Failed: {failed_count}\n"
                        updated_content += f"\n{'='*80}\n\n"
                        updated_content += "\n\n" + "="*80 + "\n\n".join(all_crawled_content)
                        
                        db.query(Document).filter(Document.id == document_id).update({
                            Document.full_content: updated_content
                        })
                        db.commit()
                        
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
                
                await asyncio.sleep(0.1)
            
            final_content = f"SITEMAP CRAWL SUMMARY\n"
            final_content += f"Website: {website_url}\n"
            final_content += f"Total URLs crawled: {total_urls}\n"
            final_content += f"Crawl started: {datetime.now().isoformat()}\n"
            final_content += f"Status: COMPLETED\n"
            final_content += f"Success: {success_count}, Failed: {failed_count}\n"
            final_content += f"Crawl finished: {datetime.now().isoformat()}\n"
            final_content += f"\n{'='*80}\n\n"
            if all_crawled_content:
                final_content += "\n\n" + "="*80 + "\n\n".join(all_crawled_content)
            
            db.query(Document).filter(Document.id == document_id).update({
                Document.full_content: final_content
            })
            db.commit()
            
            yield f"data: {json.dumps({'status': 'saving', 'message': f'💾 Đã hoàn thành và lưu {success_count} URLs vào database'})}\n\n"
            
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(loop.run_in_executor(None, _reindex_graphrag_for_customer, customer_id))
                yield f"data: {json.dumps({'status': 'indexing', 'message': '🔁 Đang chạy GraphRAG để lập chỉ mục dữ liệu...'})}\n\n"
            except Exception:
                pass
            
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
            if task_id in active_crawl_tasks:
                del active_crawl_tasks[task_id]
    
    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "X-Task-ID": task_id,
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
async def list_documents(customer_id: str, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    try:
        docs = (
            db.query(Document)
            .filter(Document.customer_id == customer_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = [
            {"id": d.id, "text": d.full_content, "source": d.source_name}
            for d in docs
        ]
        return {"items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sources/{customer_id}")
async def list_document_sources(customer_id: str, db: Session = Depends(get_db)):
    try:
        rows = (
            db.query(Document.source_name)
            .filter(Document.customer_id == customer_id)
            .distinct()
            .all()
        )
        sources = sorted([r[0] for r in rows if r[0]])
        return {"sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/sources/{customer_id}")
async def delete_document_by_source(customer_id: str, source: str = Query(..., description="Tên 'source' của tài liệu cần xóa."), db: Session = Depends(get_db)):
    try:
        deleted = (
            db.query(Document)
            .filter(Document.customer_id == customer_id, Document.source_name == source)
            .delete(synchronize_session=False)
        )
        db.commit()
        return {"message": f"Đã xóa {deleted} tài liệu với source '{source}' cho khách hàng '{customer_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/documents/{customer_id}")
async def delete_all_documents(customer_id: str, db: Session = Depends(get_db)):
    try:
        db.query(Document).filter(Document.customer_id == customer_id).delete(synchronize_session=False)
        db.commit()
        return {"message": f"Đã xóa thành công toàn bộ tài liệu trong DB của khách hàng '{customer_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))