# app/routes/chat.py
import traceback
from datetime import datetime
from app.services.db import db
from flask import Blueprint, request, jsonify
from bson import ObjectId
from app.memory.memory_service import MemoryService
from app.services.db import db
from app.utility.performance_logger import PerformanceLogger
from app.models.users import get_user_by_id

chat_bp = Blueprint("chat", __name__)

# Delete Recents Chats
@chat_bp.route('/delete-recent-chats', methods=['DELETE'])
def delete_recent_chats():
    try:
        user_id = request.args.get('userId')
        character_id = request.args.get('characterId')
        count = int(request.args.get('count', 10))  # Default to 10 if not provided

        if not user_id or not character_id:
            return jsonify({"error": "Missing userId or characterId"}), 400

        query = {
            "userId": str(user_id),
            "characterId": str(character_id)
        }

        # Find the most recent N chat IDs
        recent_chats = list(db.chats.find(query).sort("timestamp", -1).limit(count))
        chat_ids_to_delete = [chat["_id"] for chat in recent_chats]

        result = db.chats.delete_many({"_id": {"$in": chat_ids_to_delete}})
        return jsonify({"deletedCount": result.deleted_count}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Delete Chat by ID
@chat_bp.route('/delete-chat/<chat_id>', methods=['DELETE'])
def delete_chat_by_id(chat_id):
    try:
        if not ObjectId.is_valid(chat_id):
            return jsonify({"error": "Invalid chat ID"}), 400

        result = db.chats.delete_one({"_id": ObjectId(chat_id)})

        if result.deleted_count == 0:
            return jsonify({"message": "Chat not found"}), 404

        return jsonify({"message": "Chat deleted successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@chat_bp.route('/get-chats/<user_id>', methods=['GET'])
def get_chats_by_user(user_id):
    try:
        # Check if user exists
        user = get_user_by_id(user_id)
        if not user:
            return jsonify({
                "success":False,
                "error": "User ID is invalid or user not found"
            }), 404

        # Query only by userId
        query = {"userId": str(user_id)}

        # Fetch chats sorted by timestamp (latest first)
        chats = list(db.chats.find(query).sort("timestamp", -1))

        # Convert ObjectId to string for JSON
        for chat in chats:
            chat["_id"] = str(chat["_id"])

        return jsonify({
            "success":True,
            "count": len(chats),
            "data": chats
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@chat_bp.route("/generate-summary", methods=["POST"])
def add_memory_of_all_chats_till_date():
    """
    Migrate all existing chats for a user-character pair to Mem0 memory system
    
    Expected JSON payload:
    {
        "userId": "user123",
        "characterId": "char456",
        "batchSize": 50,  // optional, default 50
        "maxChats": 1000  // optional, default no limit
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
        batch_size = data.get("batchSize", 50)  # Process in batches to avoid memory issues
        max_chats = data.get("maxChats")  # Optional limit
        
        # Validate required fields
        if not user_id or not character_id:
            return jsonify({
                "success": False,
                "error": "userId and characterId are required"
            }), 400
        
        logger.log_step("Validate request data")
        
        # Initialize memory service
        memory_service = MemoryService()
        
        # Check if memories already exist for this user-character pair
        existing_stats = memory_service.get_memory_stats(user_id, character_id)
        logger.log_step("Check existing memories")
        
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
                    "existing_memories": existing_stats.get("total_memories", 0)
                }
            })
        
        # Apply max_chats limit if specified
        limit = min(max_chats, total_chats) if max_chats else total_chats
        
        # Fetch chats ordered by timestamp (oldest first for chronological memory building)
        chats_cursor = db.chats.find(query).sort("timestamp", 1).limit(limit)
        
        # Process chats in batches
        processed_count = 0
        failed_count = 0
        batch_count = 0
        
        batch = []
        
        logger.log_step("Start processing chats")
        
        for chat in chats_cursor:
            batch.append(chat)
            
            # Process batch when it reaches batch_size
            if len(batch) >= batch_size:
                batch_results = _process_chat_batch(memory_service, user_id, character_id, batch)
                processed_count += batch_results["processed"]
                failed_count += batch_results["failed"]
                batch_count += 1
                
                print(f"📦 Processed batch {batch_count}: {batch_results['processed']} successful, {batch_results['failed']} failed")
                batch = []  # Reset batch
        
        # Process remaining chats in the last batch
        if batch:
            batch_results = _process_chat_batch(memory_service, user_id, character_id, batch)
            processed_count += batch_results["processed"]
            failed_count += batch_results["failed"]
            batch_count += 1
            print(f"📦 Processed final batch {batch_count}: {batch_results['processed']} successful, {batch_results['failed']} failed")
        
        logger.log_step("Complete chat processing")
        
        # Get updated memory stats
        final_stats = memory_service.get_memory_stats(user_id, character_id)
        logger.log_step("Get final memory stats")
        
        return jsonify({
            "success": True,
            "message": f"Successfully migrated chat history to memory system",
            "stats": {
                "total_chats_found": total_chats,
                "chats_processed": processed_count,
                "chats_failed": failed_count,
                "batches_processed": batch_count,
                "batch_size": batch_size,
                "initial_memories": existing_stats.get("total_memories", 0),
                "final_memories": final_stats.get("total_memories", 0),
                "new_memories_added": final_stats.get("total_memories", 0) - existing_stats.get("total_memories", 0)
            },
            "timings": logger.get_timings()
        })
    
    except Exception as e:
        traceback.print_exc()
        logger.log_step("Error handling")
        
        return jsonify({
            "success": False,
            "error": f"Failed to migrate chats to memory: {str(e)}",
            "timings": logger.get_timings()
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
        dict: Processing results with counts
    """
    processed = 0
    failed = 0
    
    for chat in batch:
        try:
            # Extract chat information
            message = chat.get("message", "")
            sender = chat.get("sender", "unknown")  # 'user' or 'ai'
            timestamp = chat.get("timestamp", datetime.utcnow())
            
            # Skip empty messages
            if not message.strip():
                continue
            
            # Normalize sender name
            sender_name = "User" if sender.lower() in ["user", "human"] else "AI"
            
            # Add to memory with historical timestamp
            success = memory_service.add_message_to_memory(
                user_id=user_id,
                character_id=character_id,
                message=message,
                sender=sender_name
            )
            
            if success:
                processed += 1
            else:
                failed += 1
                print(f"❌ Failed to add chat to memory: {chat.get('_id')}")
                
        except Exception as e:
            failed += 1
            print(f"❌ Error processing chat {chat.get('_id', 'unknown')}: {e}")
    
    return {
        "processed": processed,
        "failed": failed
    }


@chat_bp.route("/memory-stats", methods=["POST"])
def get_memory_stats():
    """
    Get memory statistics for a user-character pair
    
    Expected JSON payload:
    {
        "userId": "user123",
        "characterId": "char456"
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
        
        if not user_id or not character_id:
            return jsonify({
                "success": False,
                "error": "userId and characterId are required"
            }), 400
        
        # Initialize memory service and get stats
        memory_service = MemoryService()
        memory_stats = memory_service.get_memory_stats(user_id, character_id)
        
        # Get chat count from database for comparison
        chat_count = db.chats.count_documents({
            "userId": str(user_id),
            "characterId": str(character_id)
        })
        
        return jsonify({
            "success": True,
            "stats": {
                "total_memories": memory_stats.get("total_memories", 0),
                "user_identifier": memory_stats.get("user_identifier"),
                "total_chats_in_db": chat_count,
                "memory_coverage": f"{(memory_stats.get('total_memories', 0) / max(chat_count, 1) * 100):.1f}%"
            }
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to get memory stats: {str(e)}"
        }), 500


@chat_bp.route("/reset-memories", methods=["POST"])
def reset_user_memories():
    """
    Reset all memories for a user-character pair
    
    Expected JSON payload:
    {
        "userId": "user123",
        "characterId": "char456",
        "confirm": true
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
        confirm = data.get("confirm", False)
        
        if not user_id or not character_id:
            return jsonify({
                "success": False,
                "error": "userId and characterId are required"
            }), 400
        
        if not confirm:
            return jsonify({
                "success": False,
                "error": "Please set confirm=true to reset memories"
            }), 400
        
        # Initialize memory service and reset memories
        memory_service = MemoryService()
        
        # Get stats before reset
        initial_stats = memory_service.get_memory_stats(user_id, character_id)
        
        # Reset memories
        success = memory_service.reset_user_memories(user_id, character_id)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Successfully reset all memories for user {user_id} and character {character_id}",
                "stats": {
                    "memories_deleted": initial_stats.get("total_memories", 0)
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to reset memories"
            }), 500
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to reset memories: {str(e)}"
        }), 500


@chat_bp.route("/search-memories", methods=["POST"])
def search_user_memories():
    """
    Search memories for a user-character pair
    
    Expected JSON payload:
    {
        "userId": "user123",
        "characterId": "char456",
        "query": "pizza preferences",
        "limit": 10
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
        query = data.get("query", "")
        limit = data.get("limit", 10)
        
        if not user_id or not character_id:
            return jsonify({
                "success": False,
                "error": "userId and characterId are required"
            }), 400
        
        if not query.strip():
            return jsonify({
                "success": False,
                "error": "Query is required"
            }), 400
        
        # Initialize memory service and search
        memory_service = MemoryService()
        search_results = memory_service.search_relevant_memories(
            user_id, character_id, query, limit
        )
        
        return jsonify({
            "success": True,
            "query": query,
            "results": search_results,
            "limit": limit
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to search memories: {str(e)}"
        }), 500    

# Add this method to your MemoryService class in memory_service.py

def recreate_collection_for_gemini(self):
    """Recreate Qdrant collection with 768 dimensions for Gemini embeddings"""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams
    from app.config import Config
    
    client = QdrantClient(
        url=Config.QDRANT_URL,
        api_key=Config.QDRANT_API_KEY,
    )
    
    # Delete existing collection
    try:
        client.delete_collection(Config.MEM0_COLLECTION_NAME)
        print(f"🗑️ Deleted existing collection: {Config.MEM0_COLLECTION_NAME}")
    except Exception as e:
        print(f"Collection might not exist: {e}")
    
    # Create new collection with 768 dimensions (Gemini default)
    client.create_collection(
        collection_name=Config.MEM0_COLLECTION_NAME,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )
    print(f"✅ Created new collection with 768 dimensions: {Config.MEM0_COLLECTION_NAME}")

# Add this route to your chat.py to trigger the recreation
@chat_bp.route("/recreate-collection", methods=["POST"])
def recreate_qdrant_collection():
    """Recreate Qdrant collection with correct dimensions for Gemini"""
    try:
        memory_service = MemoryService()
        memory_service.recreate_collection_for_gemini()
        
        return jsonify({
            "success": True,
            "message": "Successfully recreated Qdrant collection with 768 dimensions for Gemini embeddings"
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to recreate collection: {str(e)}"
        }), 500
