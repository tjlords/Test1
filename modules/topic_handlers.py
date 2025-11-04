import os
import tempfile
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import logging
from topicuploader import TopicUploader

logger = logging.getLogger(__name__)

# Store user states for topic upload
user_states = {}

class TopicHandlers:
    def __init__(self, bot_client, download_function):
        self.bot = bot_client
        self.download_function = download_function
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup only topic-related command handlers"""
        @self.bot.on_message(filters.command("topicupload") & filters.private)
        async def topic_upload_start(client, message):
            await self.topic_upload_start(client, message)
        
        @self.bot.on_message(filters.command("cancel") & filters.private)
        async def cancel_operation(client, message):
            await self.cancel_operation(client, message)
    
    async def topic_upload_start(self, client, message: Message):
        """Start topic upload process"""
        user_id = message.from_user.id
        
        await message.reply_text(
            "🤖 **Topic Upload Mode**\n\n"
            "Please send me the **Group/Chat ID** where you want to upload videos with topics.\n\n"
            "**Format:** `-1001234567890`\n\n"
            "Type /cancel to cancel."
        )
        
        user_states[user_id] = {'step': 'awaiting_chat_id'}
        
        # Set up temporary message handler for this user only
        @self.bot.on_message(filters.private & filters.text)
        async def temp_chat_id_handler(client, msg):
            if msg.from_user.id == user_id and not msg.text.startswith('/'):
                await self.handle_chat_id_input(client, msg)
        
        @self.bot.on_message(filters.private & filters.document)
        async def temp_txt_handler(client, msg):
            if msg.from_user.id == user_id:
                await self.handle_txt_file(client, msg)
        
        user_states[user_id]['handlers'] = [temp_chat_id_handler, temp_txt_handler]
    
    async def handle_chat_id_input(self, client, message: Message):
        """Handle chat ID input"""
        user_id = message.from_user.id
        text = message.text.strip()
        
        if user_id not in user_states:
            return
        
        if user_states[user_id]['step'] == 'awaiting_chat_id':
            if self.is_valid_chat_id(text):
                await self.process_chat_id(message, text, user_id)
            else:
                await message.reply_text("❌ Invalid format. Send: `-1001234567890`")
    
    def is_valid_chat_id(self, text: str):
        """Check if valid chat ID format"""
        return text.startswith('-100') and text[4:].isdigit()
    
    async def process_chat_id(self, message: Message, chat_id: str, user_id: int):
        """Process the chat ID"""
        try:
            await message.reply_text("🔍 Verifying group access...")
            
            # Try to send test message
            await self.bot.send_message(
                chat_id=chat_id,
                text="✅ **Bot Access Verified**\n\nReady to upload videos with topics!"
            )
            
            # Assume topics are enabled (skip the unreliable check)
            chat = await self.bot.get_chat(chat_id)
            
            user_states[user_id] = {
                'step': 'awaiting_txt_file',
                'chat_id': chat_id,
                'chat_title': chat.title
            }
            
            await message.reply_text(
                f"✅ **Ready to upload!**\n\n"
                f"**Group:** {chat.title}\n\n"
                "📁 **Send me the TXT file** with format:\n\n"
                "```\n"
                "[TopicName] - Video Name : URL\n"
                "[Tense-1] - Tense Lesson 1 : https://example.com/video1.m3u8\n"
                "```"
            )
                
        except Exception as e:
            logger.error(f"Group access error: {e}")
            await message.reply_text(
                f"❌ **Cannot access group!**\n\n"
                "Ensure:\n"
                "• Bot is admin in group\n"
                "• Chat ID is correct\n\n"
                "Error: " + str(e)
            )
            await self.cleanup_user_state(user_id)
    
    async def handle_txt_file(self, client, message: Message):
        """Handle TXT file for topic upload"""
        user_id = message.from_user.id
        
        if user_id not in user_states or user_states[user_id]['step'] != 'awaiting_txt_file':
            return  # Let normal handler process it
        
        if not message.document or not message.document.file_name.endswith('.txt'):
            await message.reply_text("❌ Please send a .txt file")
            return
        
        try:
            temp_file_path = await message.download(in_memory=False)
            state = user_states[user_id]
            
            await message.reply_text(
                f"📁 **Processing file for {state['chat_title']}...**\n\n"
                "⏳ Downloading and creating topics..."
            )
            
            await self.process_topic_upload(message, temp_file_path, state['chat_id'], user_id)
            
        except Exception as e:
            logger.error(f"File processing error: {e}")
            await message.reply_text("❌ Error processing file")
            await self.cleanup_user_state(user_id)
    
    async def process_topic_upload(self, message: Message, file_path: str, chat_id: str, user_id: int):
        """Process the TXT file"""
        try:
            topic_uploader = TopicUploader(self.bot, chat_id)
            
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
            
            valid_lines = []
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    valid_lines.append((line_num, line))
            
            total = len(valid_lines)
            if total == 0:
                await message.reply_text("❌ No valid lines found!")
                return
            
            success_count = 0
            
            for line_num, line in valid_lines:
                status_msg = await message.reply_text(f"🔄 Processing {line_num}/{total}")
                
                topic_name, video_name, video_url = topic_uploader.parse_input_line(line)
                
                if not all([topic_name, video_name, video_url]):
                    await message.reply_text(f"❌ Line {line_num}: Invalid format")
                    await status_msg.delete()
                    continue
                
                try:
                    video_path = await self.download_function(video_url, video_name)
                    
                    if video_path and os.path.exists(video_path):
                        topic_id = await topic_uploader.get_or_create_topic(topic_name)
                        if topic_id:
                            success = await topic_uploader.upload_video_to_topic(topic_id, video_path, video_name)
                            if success:
                                success_count += 1
                                await message.reply_text(f"✅ Uploaded to '{topic_name}'")
                        
                        try:
                            if os.path.exists(video_path):
                                os.remove(video_path)
                        except:
                            pass
                    
                except Exception as e:
                    logger.error(f"Line {line_num} error: {e}")
                
                await status_msg.delete()
                await asyncio.sleep(1)
            
            await message.reply_text(
                f"🎉 **Complete!**\n\n"
                f"**Success:** {success_count}/{total}\n"
                f"Check your group for topics!"
            )
            
            topic_uploader.close()
            
        except Exception as e:
            logger.error(f"Upload process error: {e}")
            await message.reply_text(f"❌ Upload failed: {str(e)}")
        finally:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except:
                pass
            await self.cleanup_user_state(user_id)
    
    async def cleanup_user_state(self, user_id: int):
        """Clean up user state"""
        if user_id in user_states:
            del user_states[user_id]
    
    async def cancel_operation(self, client, message: Message):
        """Cancel operation"""
        user_id = message.from_user.id
        if user_id in user_states:
            await self.cleanup_user_state(user_id)
            await message.reply_text("❌ Cancelled")