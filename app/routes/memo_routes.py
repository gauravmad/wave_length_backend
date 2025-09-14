# app/routes/memo_routes.py
import traceback
from datetime import datetime
from app.services.db import db
from flask import Blueprint, request, jsonify, Response
from bson import ObjectId
from app.memory.memory_service import MemoryService
from app.utility.performance_logger import PerformanceLogger
from app.models.users import get_user_by_id
import json
import time

memo_bp = Blueprint("memo", __name__)

@memo_bp.route("/test", methods=["GET"])
def test_endpoint():
    """Test endpoint to verify memo routes are working"""
    return jsonify({
        "success": True,
        "message": "Memo routes are working!",
        "timestamp": datetime.now().isoformat()
    }), 200

@memo_bp.route("/webhook/test", methods=["GET"])
def webhook_test():
    """Test endpoint to verify webhook routes are working"""
    try:
        # Test database connection
        user_count = db.users.count_documents({})
        character_count = db.characters.count_documents({})
        chat_count = db.chats.count_documents({})
        
        return jsonify({
            "success": True,
            "message": "Webhook routes are working!",
            "database_status": "connected",
            "stats": {
                "users": user_count,
                "characters": character_count,
                "chats": chat_count
            },
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Webhook routes working but database error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@memo_bp.route("/webhook/process-all-users-simple", methods=["POST"])
def webhook_process_all_users_simple():
    """Simple version of webhook without SSE for testing"""
    try:
        # Get request data
        data = request.get_json() or {}
        batch_size = data.get("batchSize", 50)
        sub_batch_size = data.get("subBatchSize", 10)
        max_users = data.get("maxUsers", 100)
        start_from_user = data.get("startFromUser", 1)
        
        # Test database connection
        user_count = db.users.count_documents({})
        
        if user_count == 0:
            return jsonify({
                "success": True,
                "message": "No users found in database",
                "stats": {
                    "total_users": 0,
                    "processed_users": 0,
                    "total_chats_processed": 0,
                    "total_chats_failed": 0,
                    "total_memories_created": 0
                }
            }), 200
        
        # Fetch users
        users_cursor = db.users.find({}).limit(max_users + start_from_user - 1)
        all_users = list(users_cursor)
        
        # Skip users before start_from_user
        if start_from_user > 1:
            users = all_users[start_from_user - 1:]
            skipped_users = start_from_user - 1
        else:
            users = all_users
            skipped_users = 0
        
        total_users = len(users)
        
        return jsonify({
            "success": True,
            "message": f"Found {total_users} users to process (skipped {skipped_users})",
            "config": {
                "batchSize": batch_size,
                "subBatchSize": sub_batch_size,
                "maxUsers": max_users,
                "startFromUser": start_from_user
            },
            "stats": {
                "total_users_in_db": user_count,
                "users_to_process": total_users,
                "skipped_users": skipped_users
            },
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@memo_bp.route("/process-all-chats-batches", methods=["POST"])
def process_all_chats_in_batches():
    """
    Automatically process ALL chats in batches (1-50, 51-100, 101-150, etc.) until all chats are processed
    
    Expected JSON payload:
    {
        "userId": "user123",
        "characterId": "char456",
        "batchSize": 50,      // optional, default 50 (chats per batch)
        "subBatchSize": 10    // optional, default 10 (for processing sub-batches)
    }
    """
    logger = PerformanceLogger()
    
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400
        
        user_id = data.get("userId")
        character_id = data.get("characterId")
        batch_size = data.get("batchSize", 50)  # Number of chats per batch
        sub_batch_size = data.get("subBatchSize", 10)  # Sub-batch size for processing
        
        # Validate required fields
        if not user_id or not character_id:
            return jsonify({
                "success": False,
                "error": "userId and characterId are required"
            }), 400
        
        logger.log_step("Validate request data")
        
        # Initialize memory service
        memory_service = MemoryService()
        
        # Build query for fetching chats
        query = {
            "userId": str(user_id), 
            "characterId": str(character_id)
        }
        
        # Get total count of chats
        total_chats = db.chats.count_documents(query)
        logger.log_step("Count total chats")
        
        if total_chats == 0:
            return jsonify({
                "success": True,
                "message": "No chats found for this user-character pair",
                "stats": {
                    "total_chats": 0,
                    "processed_chats": 0,
                    "batches_processed": 0
                }
            })
        
        # Calculate number of batches needed
        total_batches = (total_chats + batch_size - 1) // batch_size  # Ceiling division
        
        print(f"🚀 Starting automatic batch processing:")
        print(f"   📊 Total chats: {total_chats}")
        print(f"   📦 Batch size: {batch_size}")
        print(f"   🔄 Total batches: {total_batches}")
        print(f"   ⚙️  Sub-batch size: {sub_batch_size}")
        
        # Process all batches
        total_processed = 0
        total_failed = 0
        batch_results = []
        
        for batch_num in range(1, total_batches + 1):
            start_index = (batch_num - 1) * batch_size + 1
            end_index = min(batch_num * batch_size, total_chats)
            
            print(f"\n📦 Processing batch {batch_num}/{total_batches}: chats {start_index}-{end_index}")
            
            # Calculate actual range to fetch
            actual_start = start_index - 1  # Convert to 0-based index
            actual_count = end_index - actual_start
            
            # Fetch chats in this batch
            chats_cursor = db.chats.find(query).sort("timestamp", 1).skip(actual_start).limit(actual_count)
            chats = list(chats_cursor)
            
            if not chats:
                print(f"   ⚠️  No chats found in batch {batch_num}")
                continue
            
            # Process chats in sub-batches
            batch_processed = 0
            batch_failed = 0
            sub_batch_count = 0
            
            for i in range(0, len(chats), sub_batch_size):
                sub_batch = chats[i:i + sub_batch_size]
                sub_batch_results = _process_chat_batch(memory_service, user_id, character_id, sub_batch)
                batch_processed += sub_batch_results["processed"]
                batch_failed += sub_batch_results["failed"]
                sub_batch_count += 1
                
                print(f"   📋 Sub-batch {sub_batch_count}: {sub_batch_results['processed']} processed, {sub_batch_results['failed']} failed")
            
            # Update totals
            total_processed += batch_processed
            total_failed += batch_failed
            
            # Store batch results
            batch_result = {
                "batch_number": batch_num,
                "range": f"{start_index}-{end_index}",
                "chats_fetched": len(chats),
                "processed": batch_processed,
                "failed": batch_failed,
                "sub_batches": sub_batch_count
            }
            batch_results.append(batch_result)
            
            print(f"   ✅ Batch {batch_num} completed: {batch_processed} processed, {batch_failed} failed")
        
        # Get final memory stats
        final_stats = memory_service.get_memory_stats(user_id, character_id)
        logger.log_step("Get final memory stats")
        
        print(f"\n🎉 All batches completed!")
        print(f"   📊 Total processed: {total_processed}")
        print(f"   ❌ Total failed: {total_failed}")
        print(f"   💾 Total memories: {final_stats.get('total_memories', 0)}")
        
        return jsonify({
            "success": True,
            "message": f"Successfully processed all {total_chats} chats in {total_batches} batches",
            "stats": {
                "total_chats": total_chats,
                "total_batches": total_batches,
                "batch_size": batch_size,
                "sub_batch_size": sub_batch_size,
                "total_processed": total_processed,
                "total_failed": total_failed,
                "total_memories": final_stats.get("total_memories", 0)
            },
            "batch_results": batch_results
        }), 200
        
    except Exception as e:
        error_msg = f"Error processing all chats in batches: {str(e)}"
        print(f"❌ {error_msg}")
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500


@memo_bp.route("/process-batch-chats", methods=["POST"])
def process_batch_chats():
    """
    Process a specific batch of chats (1-50) and store them in Qdrant using Mem0
    
    Expected JSON payload:
    {
        "userId": "user123",
        "characterId": "char456",
        "startIndex": 1,     // optional, default 1
        "endIndex": 50,      // optional, default 50
        "batchSize": 10      // optional, default 10 (for processing sub-batches)
    }
    """
    logger = PerformanceLogger()
    
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400
        
        user_id = data.get("userId")
        character_id = data.get("characterId")
        start_index = data.get("startIndex", 1)
        end_index = data.get("endIndex", 50)
        batch_size = data.get("batchSize", 10)
        
        # Validate required fields
        if not user_id or not character_id:
            return jsonify({
                "success": False,
                "error": "userId and characterId are required"
            }), 400
        
        # Validate indices
        if start_index < 1 or end_index < start_index:
            return jsonify({
                "success": False,
                "error": "Invalid indices: startIndex must be >= 1 and endIndex must be >= startIndex"
            }), 400
        
        logger.log_step("Validate request data")
        
        # Initialize memory service
        memory_service = MemoryService()
        
        # Build query for fetching chats
        query = {
            "userId": str(user_id), 
            "characterId": str(character_id)
        }
        
        # Get total count of chats
        total_chats = db.chats.count_documents(query)
        logger.log_step("Count total chats")
        
        if total_chats == 0:
            return jsonify({
                "success": True,
                "message": "No chats found for this user-character pair",
                "stats": {
                    "total_chats": 0,
                    "processed_chats": 0,
                    "requested_range": f"{start_index}-{end_index}"
                }
            })
        
        # Calculate actual range to fetch
        actual_start = max(0, start_index - 1)  # Convert to 0-based index
        actual_end = min(total_chats, end_index)
        actual_count = actual_end - actual_start
        
        if actual_count <= 0:
            return jsonify({
                "success": True,
                "message": f"No chats in requested range {start_index}-{end_index}",
                "stats": {
                    "total_chats": total_chats,
                    "processed_chats": 0,
                    "requested_range": f"{start_index}-{end_index}"
                }
            })
        
        # Fetch chats in the specified range, ordered by timestamp (oldest first)
        chats_cursor = db.chats.find(query).sort("timestamp", 1).skip(actual_start).limit(actual_count)
        chats = list(chats_cursor)
        
        logger.log_step(f"Fetch {len(chats)} chats from range {start_index}-{end_index}")
        
        # Process chats in sub-batches
        processed_count = 0
        failed_count = 0
        batch_count = 0
        
        for i in range(0, len(chats), batch_size):
            batch = chats[i:i + batch_size]
            batch_results = _process_chat_batch(memory_service, user_id, character_id, batch)
            processed_count += batch_results["processed"]
            failed_count += batch_results["failed"]
            batch_count += 1
            
            print(f"📦 Processed sub-batch {batch_count}: {batch_results['processed']} successful, {batch_results['failed']} failed")
        
        # Get final memory stats
        final_stats = memory_service.get_memory_stats(user_id, character_id)
        logger.log_step("Get final memory stats")
        
        return jsonify({
            "success": True,
            "message": f"Successfully processed chats {start_index}-{end_index}",
            "stats": {
                "total_chats_in_db": total_chats,
                "requested_range": f"{start_index}-{end_index}",
                "chats_fetched": len(chats),
                "processed_chats": processed_count,
                "failed_chats": failed_count,
                "sub_batches_processed": batch_count,
                "total_memories": final_stats.get("total_memories", 0)
            }
        }), 200
        
    except Exception as e:
        error_msg = f"Error processing batch chats: {str(e)}"
        print(f"❌ {error_msg}")
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500


@memo_bp.route("/memory-stats", methods=["GET"])
def get_memory_stats():
    """
    Get memory statistics for a user-character pair
    
    Query parameters:
    - userId: User ID
    - characterId: Character ID
    """
    try:
        user_id = request.args.get('userId')
        character_id = request.args.get('characterId')
        
        if not user_id or not character_id:
            return jsonify({
                "success": False,
                "error": "userId and characterId are required"
            }), 400
        
        # Initialize memory service
        memory_service = MemoryService()
        
        # Get memory stats
        stats = memory_service.get_memory_stats(user_id, character_id)
        
        return jsonify({
            "success": True,
            "stats": stats
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@memo_bp.route("/search-memories", methods=["POST"])
def search_memories():
    """
    Search for relevant memories using a query
    
    Expected JSON payload:
    {
        "userId": "user123",
        "characterId": "char456",
        "query": "What did we discuss about AI?",
        "limit": 10  // optional, default 15
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400
        
        user_id = data.get("userId")
        character_id = data.get("characterId")
        query = data.get("query")
        limit = data.get("limit", 15)
        
        if not all([user_id, character_id, query]):
            return jsonify({
                "success": False,
                "error": "userId, characterId, and query are required"
            }), 400
        
        # Initialize memory service
        memory_service = MemoryService()
        
        # Search for relevant memories
        memories = memory_service.search_relevant_memories(user_id, character_id, query, limit)
        
        return jsonify({
            "success": True,
            "query": query,
            "memories": memories,
            "limit": limit
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@memo_bp.route("/recreate-collection", methods=["POST"])
def recreate_collection():
    """
    Recreate Qdrant collection with correct dimensions for Gemini embeddings (768 dimensions)
    This will delete the existing collection and create a new one.
    """
    try:
        print("🔄 Recreating Qdrant collection for Gemini embeddings...")
        
        # Initialize memory service
        memory_service = MemoryService()
        
        # Recreate collection
        memory_service.recreate_collection_for_gemini()
        
        return jsonify({
            "success": True,
            "message": "Successfully recreated Qdrant collection with 768 dimensions for Gemini embeddings",
            "collection_name": "chat_memories",
            "dimensions": 768,
            "embedding_model": "models/text-embedding-004"
        }), 200
        
    except Exception as e:
        error_msg = f"Error recreating collection: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500


@memo_bp.route("/fix-collection-dimensions", methods=["POST"])
def fix_collection_dimensions():
    """
    Fix Qdrant collection dimensions to match Gemini embedding model (768 dimensions)
    
    Expected JSON payload:
    {
        "userId": "user123",        // optional, for user-specific collection
        "characterId": "char456",   // optional, for character-specific collection
        "recreate": true            // optional, default true (recreate collection)
    }
    """
    try:
        data = request.get_json() or {}
        user_id = data.get("userId")
        character_id = data.get("characterId")
        recreate = data.get("recreate", True)
        
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        from app.config import Config
        
        print("🔧 Fixing Qdrant collection dimensions...")
        print(f"   📊 Target dimensions: 768 (Gemini text-embedding-004)")
        print(f"   🔄 Recreate collection: {recreate}")
        
        # Initialize Qdrant client
        if Config.QDRANT_API_KEY:
            client = QdrantClient(
                url=Config.QDRANT_URL,
                api_key=Config.QDRANT_API_KEY,
            )
        else:
            client = QdrantClient(url=Config.QDRANT_URL)
        
        collection_name = Config.MEM0_COLLECTION_NAME
        
        # Check if collection exists and get its current configuration
        try:
            collection_info = client.get_collection(collection_name)
            current_dim = collection_info.config.params.vectors.size
            print(f"   📏 Current collection dimensions: {current_dim}")
            
            if current_dim == 768:
                return jsonify({
                    "success": True,
                    "message": f"Collection '{collection_name}' already has correct dimensions (768)",
                    "current_dimensions": current_dim,
                    "target_dimensions": 768
                }), 200
            
            if recreate:
                # Delete existing collection
                client.delete_collection(collection_name)
                print(f"   🗑️ Deleted existing collection: {collection_name}")
                
                # Create new collection with correct dimensions
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                )
                print(f"   ✅ Created new collection with 768 dimensions: {collection_name}")
                
                return jsonify({
                    "success": True,
                    "message": f"Successfully recreated collection '{collection_name}' with 768 dimensions",
                    "previous_dimensions": current_dim,
                    "new_dimensions": 768,
                    "action": "recreated"
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "error": f"Collection has wrong dimensions ({current_dim}), but recreate is disabled",
                    "current_dimensions": current_dim,
                    "target_dimensions": 768,
                    "suggestion": "Set 'recreate': true to fix this"
                }), 400
                
        except Exception as e:
            if "doesn't exist" in str(e) or "not found" in str(e):
                # Collection doesn't exist, create it
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                )
                print(f"   ✅ Created new collection with 768 dimensions: {collection_name}")
                
                return jsonify({
                    "success": True,
                    "message": f"Created new collection '{collection_name}' with 768 dimensions",
                    "new_dimensions": 768,
                    "action": "created"
                }), 200
            else:
                raise e
        
    except Exception as e:
        error_msg = f"Error fixing collection dimensions: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500


@memo_bp.route("/add-memory", methods=["POST"])
def add_memory():
    """
    Add a single message to memory
    
    Expected JSON payload:
    {
        "userId": "user123",
        "characterId": "char456",
        "message": "Hello, how are you?",
        "sender": "user"  // or "ai"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 400
        
        user_id = data.get("userId")
        character_id = data.get("characterId")
        message = data.get("message")
        sender = data.get("sender")
        
        if not all([user_id, character_id, message, sender]):
            return jsonify({
                "success": False,
                "error": "userId, characterId, message, and sender are required"
            }), 400
        
        if sender not in ["user", "ai"]:
            return jsonify({
                "success": False,
                "error": "sender must be either 'user' or 'ai'"
            }), 400
        
        # Initialize memory service
        memory_service = MemoryService()
        
        # Add message to memory
        success = memory_service.add_message_to_memory(user_id, character_id, message, sender)
        
        if success:
            return jsonify({
                "success": True,
                "message": "Memory added successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to add memory"
            }), 500
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def _process_chat_batch(memory_service: MemoryService, user_id: str, character_id: str, batch: list) -> dict:
    """
    Process a batch of chats and add them to memory
    
    Args:
        memory_service: MemoryService instance
        user_id: User ID
        character_id: Character ID
        batch: List of chat documents
    
    Returns:
        dict: Results with processed and failed counts
    """
    processed = 0
    failed = 0
    
    for chat in batch:
        try:
            message = chat.get("message", "").strip()
            sender = chat.get("sender", "").strip()
            
            # Skip empty messages or invalid senders
            if not message or sender not in ["user", "ai"]:
                continue
            
            # Add to memory
            success = memory_service.add_message_to_memory(user_id, character_id, message, sender)
            
            if success:
                processed += 1
            else:
                failed += 1
                
        except Exception as e:
            print(f"❌ Error processing chat {chat.get('_id', 'unknown')}: {e}")
            failed += 1
    
    return {
        "processed": processed,
        "failed": failed
    }


def _process_user_character_batches(user_id: str, character_id: str, batch_size: int, sub_batch_size: int) -> dict:
    """
    Process all chats for a specific user-character pair using the existing working logic
    
    Args:
        user_id: User ID
        character_id: Character ID
        batch_size: Number of chats per batch
        sub_batch_size: Sub-batch size for processing
    
    Returns:
        dict: Results with processed, failed, and memory counts
    """
    try:
        # Initialize memory service
        memory_service = MemoryService()
        
        # Build query for fetching chats
        query = {
            "userId": str(user_id), 
            "characterId": str(character_id)
        }
        
        # Get total count of chats
        total_chats = db.chats.count_documents(query)
        
        if total_chats == 0:
            return {
                "total_processed": 0,
                "total_failed": 0,
                "total_memories": 0,
                "total_batches": 0
            }
        
        # Calculate number of batches needed
        total_batches = (total_chats + batch_size - 1) // batch_size
        
        # Process all batches
        total_processed = 0
        total_failed = 0
        
        for batch_num in range(1, total_batches + 1):
            start_index = (batch_num - 1) * batch_size + 1
            end_index = min(batch_num * batch_size, total_chats)
            
            # Calculate actual range to fetch
            actual_start = start_index - 1  # Convert to 0-based index
            actual_count = end_index - actual_start
            
            # Fetch chats in this batch
            chats_cursor = db.chats.find(query).sort("timestamp", 1).skip(actual_start).limit(actual_count)
            chats = list(chats_cursor)
            
            if not chats:
                continue
            
            # Process chats in sub-batches
            batch_processed = 0
            batch_failed = 0
            
            for i in range(0, len(chats), sub_batch_size):
                sub_batch = chats[i:i + sub_batch_size]
                sub_batch_results = _process_chat_batch(memory_service, user_id, character_id, sub_batch)
                batch_processed += sub_batch_results["processed"]
                batch_failed += sub_batch_results["failed"]
            
            total_processed += batch_processed
            total_failed += batch_failed
        
        # Get final memory stats
        final_stats = memory_service.get_memory_stats(user_id, character_id)
        
        return {
            "total_processed": total_processed,
            "total_failed": total_failed,
            "total_memories": final_stats.get("total_memories", 0),
            "total_batches": total_batches
        }
        
    except Exception as e:
        print(f"❌ Error processing user-character batches: {e}")
        return {
            "total_processed": 0,
            "total_failed": 0,
            "total_memories": 0,
            "total_batches": 0
        }


@memo_bp.route("/webhook/process-all-users", methods=["POST"])
def webhook_process_all_users():
    """
    Webhook endpoint to process ALL users in batches with real-time progress updates
    
    This endpoint will:
    1. Fetch all users from the database
    2. For each user, get all their characters
    3. Process all chats for each user-character pair in batches
    4. Send real-time progress updates via Server-Sent Events (SSE)
    
    Expected JSON payload:
    {
        "batchSize": 50,      // optional, default 50 (chats per batch)
        "subBatchSize": 10,   // optional, default 10 (for processing sub-batches)
        "maxUsers": 100,      // optional, default 100 (limit number of users to process)
        "startFromUser": 4    // optional, default 1 (start processing from this user index)
    }
    """
    
    # Get request data outside the generator function
    data = request.get_json() or {}
    batch_size = data.get("batchSize", 50)
    sub_batch_size = data.get("subBatchSize", 10)
    max_users = data.get("maxUsers", 100)
    start_from_user = data.get("startFromUser", 1)
    
    def generate_progress_updates():
        """Generator function for Server-Sent Events"""
        try:
            # Send initial status
            if start_from_user > 1:
                yield f"data: {json.dumps({'type': 'start', 'message': f'Starting batch processing from user {start_from_user}...', 'start_from_user': start_from_user, 'timestamp': datetime.now().isoformat()})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'start', 'message': 'Starting batch processing for all users...', 'timestamp': datetime.now().isoformat()})}\n\n"
            
            # Fetch all users
            yield f"data: {json.dumps({'type': 'fetch_users', 'message': 'Fetching all users from database...', 'timestamp': datetime.now().isoformat()})}\n\n"
            
            # Fetch all users and apply start_from_user offset
            users_cursor = db.users.find({}).limit(max_users + start_from_user - 1)
            all_users = list(users_cursor)
            
            # Skip users before start_from_user
            if start_from_user > 1:
                users = all_users[start_from_user - 1:]
                skipped_users = start_from_user - 1
            else:
                users = all_users
                skipped_users = 0
            
            total_users = len(users)
            total_all_users = len(all_users)
            
            if skipped_users > 0:
                yield f"data: {json.dumps({'type': 'users_fetched', 'message': f'Fetched {total_users} users (skipped first {skipped_users} users)', 'total_users': total_users, 'skipped_users': skipped_users, 'start_from_user': start_from_user, 'timestamp': datetime.now().isoformat()})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'users_fetched', 'message': f'Fetched {total_users} users', 'total_users': total_users, 'timestamp': datetime.now().isoformat()})}\n\n"
            
            if total_users == 0:
                yield f"data: {json.dumps({'type': 'complete', 'message': 'No users found in database', 'timestamp': datetime.now().isoformat()})}\n\n"
                return
            
            # Process each user using the existing working function
            total_processed_users = 0
            total_processed_chats = 0
            total_failed_chats = 0
            total_memories_created = 0
            
            # Hardcoded character ID
            hardcoded_character_id = "688210873496b5e441480d22"
            character_name = "Hardcoded Character"
            
            for user_index, user in enumerate(users, start_from_user):
                user_id = str(user.get("_id"))
                user_name = user.get("userName", "Unknown User")
                
                # Send user start status
                yield f"data: {json.dumps({'type': 'user_start', 'message': f'Processing user {user_index}/{total_all_users}: {user_name}', 'user_id': user_id, 'user_name': user_name, 'user_index': user_index, 'total_users': total_users, 'total_all_users': total_all_users, 'timestamp': datetime.now().isoformat()})}\n\n"
                
                # Process user with hardcoded character ID
                user_processed_chats = 0
                user_failed_chats = 0
                
                yield f"data: {json.dumps({'type': 'character_start', 'message': f'Processing with hardcoded character: {character_name}', 'user_id': user_id, 'user_name': user_name, 'character_id': hardcoded_character_id, 'character_name': character_name, 'timestamp': datetime.now().isoformat()})}\n\n"
                
                # Call the working API endpoint for this user-character pair
                try:
                    import requests
                    
                    # Call the working API endpoint
                    api_url = f"http://localhost:5000/api/memo/process-all-chats-batches"
                    payload = {
                        "userId": user_id,
                        "characterId": hardcoded_character_id,
                        "batchSize": batch_size,
                        "subBatchSize": sub_batch_size
                    }
                    
                    yield f"data: {json.dumps({'type': 'api_call', 'message': f'Calling API for {character_name}...', 'user_id': user_id, 'user_name': user_name, 'character_id': hardcoded_character_id, 'character_name': character_name, 'timestamp': datetime.now().isoformat()})}\n\n"
                    
                    # Make the API call
                    response = requests.post(api_url, json=payload, timeout=300)  # 5 minute timeout
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        character_processed = result.get("stats", {}).get("total_processed", 0)
                        character_failed = result.get("stats", {}).get("total_failed", 0)
                        character_memories = result.get("stats", {}).get("total_memories", 0)
                        batches_processed = result.get("stats", {}).get("total_batches", 0)
                        
                        # Send batch progress updates
                        for batch_num in range(1, batches_processed + 1):
                            yield f"data: {json.dumps({'type': 'batch_progress', 'message': f'Processed batch {batch_num}/{batches_processed} for {character_name}', 'user_id': user_id, 'user_name': user_name, 'character_id': hardcoded_character_id, 'character_name': character_name, 'batch_num': batch_num, 'total_batches': batches_processed, 'timestamp': datetime.now().isoformat()})}\n\n"
                            time.sleep(0.1)  # Small delay
                        
                        user_processed_chats += character_processed
                        user_failed_chats += character_failed
                        total_memories_created += character_memories
                        
                        # Send character completion status
                        yield f"data: {json.dumps({'type': 'character_complete', 'message': f'Completed character {character_name}: {character_processed} processed, {character_failed} failed, {character_memories} memories', 'user_id': user_id, 'user_name': user_name, 'character_id': hardcoded_character_id, 'character_name': character_name, 'processed': character_processed, 'failed': character_failed, 'memories': character_memories, 'timestamp': datetime.now().isoformat()})}\n\n"
                    else:
                        error_msg = f"API call failed for {character_name}: HTTP {response.status_code}"
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'user_id': user_id, 'user_name': user_name, 'character_id': hardcoded_character_id, 'character_name': character_name, 'timestamp': datetime.now().isoformat()})}\n\n"
                        continue
                    
                except requests.exceptions.Timeout:
                    error_msg = f"Timeout processing character {character_name}"
                    yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'user_id': user_id, 'user_name': user_name, 'character_id': hardcoded_character_id, 'character_name': character_name, 'timestamp': datetime.now().isoformat()})}\n\n"
                    continue
                except Exception as e:
                    error_msg = f"Error processing character {character_name}: {str(e)}"
                    yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'user_id': user_id, 'user_name': user_name, 'character_id': hardcoded_character_id, 'character_name': character_name, 'timestamp': datetime.now().isoformat()})}\n\n"
                    continue
                
                total_processed_chats += user_processed_chats
                total_failed_chats += user_failed_chats
                total_processed_users += 1
                
                # Send user completion status
                yield f"data: {json.dumps({'type': 'user_complete', 'message': f'Completed user {user_name}: {user_processed_chats} chats processed, {user_failed_chats} failed', 'user_id': user_id, 'user_name': user_name, 'processed': user_processed_chats, 'failed': user_failed_chats, 'user_index': user_index, 'total_users': total_users, 'total_all_users': total_all_users, 'timestamp': datetime.now().isoformat()})}\n\n"
            
            # Send final completion status
            yield f"data: {json.dumps({'type': 'complete', 'message': f'All users processed successfully!', 'summary': {'total_users': total_users, 'processed_users': total_processed_users, 'total_chats_processed': total_processed_chats, 'total_chats_failed': total_failed_chats, 'total_memories_created': total_memories_created, 'start_from_user': start_from_user, 'skipped_users': skipped_users}, 'timestamp': datetime.now().isoformat()})}\n\n"
            
        except Exception as e:
            error_msg = f"Error in webhook processing: {str(e)}"
            print(f"❌ {error_msg}")
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'timestamp': datetime.now().isoformat()})}\n\n"
    
    # Return Server-Sent Events response
    return Response(
        generate_progress_updates(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control'
        }
    )
