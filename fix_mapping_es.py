import asyncio
from elasticsearch import AsyncElasticsearch
from service.data.data_loader_elastic_search import get_shared_index_mapping, ACCESSORIES_INDEX
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_elasticsearch_mapping():
    """Fix mapping của Elasticsearch index"""
    
    # Kết nối Elasticsearch
    es_host = os.getenv("ELASTICSEARCH_HOST", "localhost")
    es_port = os.getenv("ELASTICSEARCH_PORT", "9200")
    es_url = f"http://{es_host}:{es_port}"
    
    es_client = AsyncElasticsearch([es_url])
    
    try:
        print("🔧 Bắt đầu fix mapping Elasticsearch...")
        
        # Kiểm tra index có tồn tại không
        index_exists = await es_client.indices.exists(index=ACCESSORIES_INDEX)
        
        if index_exists:
            print(f"🗑️ Xóa index cũ '{ACCESSORIES_INDEX}'...")
            await es_client.indices.delete(index=ACCESSORIES_INDEX)
            print(f"✅ Đã xóa index '{ACCESSORIES_INDEX}'")
        
        # Tạo lại index với mapping đúng
        print(f"🛠️ Tạo lại index '{ACCESSORIES_INDEX}' với mapping đúng...")
        mapping = get_shared_index_mapping("accessory")
        
        # In ra mapping để kiểm tra
        print("📋 Mapping mới:")
        import json
        print(json.dumps(mapping, indent=2, ensure_ascii=False))
        
        await es_client.indices.create(index=ACCESSORIES_INDEX, mappings=mapping)
        print(f"✅ Đã tạo thành công index '{ACCESSORIES_INDEX}' với mapping đúng")
        
        # Kiểm tra mapping đã được áp dụng
        print("🔍 Kiểm tra mapping đã được áp dụng...")
        mapping_info = await es_client.indices.get_mapping(index=ACCESSORIES_INDEX)
        print("📋 Mapping hiện tại:")
        print(json.dumps(mapping_info[ACCESSORIES_INDEX]['mappings'], indent=2, ensure_ascii=False))
        
        print("✅ Fix mapping thành công!")
        
    except Exception as e:
        print(f"❌ Lỗi khi fix mapping: {e}")
        raise
    finally:
        await es_client.close()

if __name__ == "__main__":
    asyncio.run(fix_elasticsearch_mapping())
