import sqlite3
import re
import os
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TopicUploader:
    def __init__(self, bot_client, chat_id):
        self.bot = bot_client
        self.chat_id = chat_id
        self.setup_database()
    
    def setup_database(self):
        """Initialize database to store topic mappings"""
        self.conn = sqlite3.connect('telegram_topics.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS topic_mappings 
            (topic_name TEXT PRIMARY KEY, topic_id INTEGER)
        ''')
        self.conn.commit()
        logger.info("✅ Topic database setup completed")
    
    def parse_input_line(self, line):
        """
        Parse input line to extract topic name, video name and URL
        Format: [TopicName] - Video Name : URL
        """
        pattern = r'\[([^\]]+)\]\s*-\s*([^:]+)\s*:\s*(https?://[^\s]+)'
        match = re.match(pattern, line.strip())
        
        if match:
            topic_name = match.group(1).strip()
            video_name = match.group(2).strip()
            video_url = match.group(3).strip()
            return topic_name, video_name, video_url
        return None, None, None
    
    async def get_or_create_topic(self, topic_name):
        """Get existing topic or create new one using Pyrogram"""
        # Check database first
        self.cursor.execute('SELECT topic_id FROM topic_mappings WHERE topic_name = ?', (topic_name,))
        result = self.cursor.fetchone()
        
        if result:
            topic_id = result[0]
            logger.info(f"📁 Using existing topic: {topic_name} -> ID: {topic_id}")
            return topic_id
        
        # Create new topic using Pyrogram
        try:
            logger.info(f"🆕 Creating topic: {topic_name}")
            
            # Create forum topic
            result = await self.bot.create_forum_topic(
                chat_id=self.chat_id,
                title=topic_name
            )
            
            topic_id = result.message_thread_id
            
            # Store in database
            self.cursor.execute(
                'INSERT OR REPLACE INTO topic_mappings (topic_name, topic_id) VALUES (?, ?)',
                (topic_name, topic_id)
            )
            self.conn.commit()
            
            logger.info(f"✅ Created new topic: {topic_name} (ID: {topic_id})")
            return topic_id
            
        except Exception as e:
            logger.error(f"❌ Failed to create topic '{topic_name}': {e}")
            return None
    
    async def upload_video_to_topic(self, topic_id, video_path, caption):
        """Upload video to specific topic using Pyrogram"""
        try:
            logger.info(f"📤 Uploading to topic {topic_id}: {caption}")
            
            if not os.path.exists(video_path):
                logger.error(f"❌ Video file not found: {video_path}")
                return False
            
            file_size = os.path.getsize(video_path)
            logger.info(f"📊 File size: {file_size} bytes")
            
            # Upload video to specific topic
            await self.bot.send_video(
                chat_id=self.chat_id,
                video=video_path,
                caption=caption,
                message_thread_id=topic_id,
                supports_streaming=True
            )
            
            logger.info(f"✅ Successfully uploaded to topic {topic_id}")
            return True
                    
        except Exception as e:
            logger.error(f"❌ Error during upload: {e}")
            return False
    
    async def test_connection(self):
        """Test bot and chat connection"""
        try:
            # Test bot connection
            me = await self.bot.get_me()
            logger.info(f"✅ Bot connection successful: {me.first_name}")
            
            # Test chat access
            chat = await self.bot.get_chat(self.chat_id)
            is_forum = getattr(chat, 'is_forum', False)
            logger.info(f"✅ Chat access successful: {chat.title}")
            logger.info(f"✅ Forum topics enabled: {is_forum}")
            
            return True, chat.title, is_forum
            
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False, None, False
    
    def close(self):
        """Close database connection"""
        self.conn.close()
        logger.info("📦 Topic uploader closed")