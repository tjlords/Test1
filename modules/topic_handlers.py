import os
import tempfile
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
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
        """Setup topic-related command handlers"""
        @self.bot.on_message(filters.command("topicupload") & filters.private)
        async def topic_upload_start(client, message):
            await self.topic_upload_start(client, message)
        
        @self.bot.on_message(filters.command("cancel") & filters.private)
        async def cancel_operation(client, message):
            await self.cancel_operation(client, message)
        
        @self.bot.on_message(filters.document & filters.private)
        async def handle_document(client, message):
            await self.handle_txt_file(client, message)
        
        @self.bot.on_message(filters.text & filters.private & ~filters.command)
        async def handle_text_message(client, message):
            await self.handle_text_message(client, message)
    
    async def topic_upload_start(self, client, message: Message):
        """Start topic upload process"""
        user_id = message.from_user.id
        
        await message.reply_text(
            "🤖 **Topic Upload Mode**\n\n"
            "Please send me the **Group/Chat ID** where you want to upload videos with topics.\n\n"
            "**How to get Chat ID:**\n"
            "1. Add @RawDataBot to your group\n"
            "2. Send any message in the group\n"
            "3. Forward that message to me\n"
            "4. I'll extract the Chat ID automatically\n\n"
            "Or send the Chat ID directly (format: -1001234567890)\n\n"
            "Type /cancel to cancel this operation."
        )
        
        user_states[user_id] = {'step': 'awaiting_chat_id'}
    
    async def handle_text_message(self, client, message: Message):
        """Handle text messages during topic upload process"""
        user_id = message.from_user.id
        text = message.text.strip()
        
        if user_id not in user_states:
            return
        
        state = user_states[user_id]
        
        if state['step'] == 'awaiting_chat_id':
            # Try to extract chat ID from forwarded message or use directly
            chat_id = await self.extract_chat_id(message, text)
            
            if chat_id:
                await self.verify_and_proceed(message, chat_id, user_id)
            else:
                await message.reply_text(
                    "❌ Invalid Chat ID format.\n"
                    "Please send a valid Chat ID (format: -1001234567890) or forward a message from the group."
                )
    
    async def extract_chat_id(self, message: Message, text: str):
        """Extract chat ID from text or forwarded message"""
        # Check if it's a forwarded message
        if message.forward_from_chat:
            return str(message.forward_from_chat.id)
        
        # Check if it's a direct chat ID
        if text.startswith('-100') and text[1:].isdigit():
            return text
        
        # Try to extract from forwarded message text
        if "chat" in text.lower() and "id" in text.lower():
            import re
            patterns = [
                r'id[:\s]*(-?\d+)',
                r'chat[:\s]*(-?\d+)',
                r'(-100\d+)'
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
        
        return None
    
    async def verify_and_proceed(self, message: Message, chat_id: str, user_id: int):
        """Verify chat access and proceed to next step"""
        try:
            # Initialize topic uploader for verification
            topic_uploader = TopicUploader(self.bot, chat_id)
            success, chat_title, is_forum = await topic_uploader.test_connection()
            topic_uploader.close()
            
            if success:
                if is_forum:
                    user_states[user_id] = {
                        'step': 'awaiting_txt_file',
                        'chat_id': chat_id,
                        'chat_title': chat_title
                    }
                    
                    await message.reply_text(
                        f"✅ **Chat Verified Successfully!**\n\n"
                        f"**Group:** {chat_title}\n"
                        f"**Chat ID:** {chat_id}\n"
                        f"**Topics Support:** ✅ Enabled\n\n"
                        "Now please send me the **TXT file** containing your video links in this format:\n\n"
                        "```\n"
                        "[TopicName] - Video Name : URL\n"
                        "[Tense-1] - Tense Lesson 1 : https://example.com/video1.m3u8\n"
                        "[Math] - Algebra Basics : https://example.com/video2.m3u8\n"
                        "```\n\n"
                        "I'll download and upload each video to its respective topic!"
                    )
                else:
                    await message.reply_text(
                        f"❌ **Topics Not Enabled**\n\n"
                        f"The group **{chat_title}** doesn't have topics enabled.\n\n"
                        "**To enable topics:**\n"
                        "1. Go to group settings\n"
                        "2. Find 'Topics' option\n"
                        "3. Enable 'Topics'\n"
                        "4. Try again with /topicupload"
                    )
                    del user_states[user_id]
            else:
                await message.reply_text(
                    "❌ **Chat Access Failed**\n\n"
                    "Please ensure:\n"
                    "• The bot is added to the group\n"
                    "• The bot has admin permissions\n"
                    "• The Chat ID is correct\n\n"
                    "Try again with /topicupload"
                )
                del user_states[user_id]
                
        except Exception as e:
            logger.error(f"Error verifying chat: {e}")
            await message.reply_text("❌ Error verifying chat. Please try again.")
            del user_states[user_id]
    
    async def handle_txt_file(self, client, message: Message):
        """Handle uploaded TXT file for topic upload"""
        user_id = message.from_user.id
        
        if user_id not in user_states or user_states[user_id]['step'] != 'awaiting_txt_file':
            return
        
        # Check if it's a txt file
        if not message.document or not message.document.file_name.endswith('.txt'):
            return
        
        try:
            # Download TXT file to temporary file
            temp_file_path = await message.download(in_memory=False)
            
            state = user_states[user_id]
            chat_id = state['chat_id']
            chat_title = state['chat_title']
            
            await message.reply_text(
                f"📁 **File Received!**\n\n"
                f"Starting topic upload process for **{chat_title}**...\n"
                f"I'll now download and upload videos to their respective topics.\n\n"
                "⏳ This may take a while..."
            )
            
            # Process the file asynchronously to avoid timeout
            asyncio.create_task(self.process_topic_upload(message, temp_file_path, chat_id, user_id))
            
        except Exception as e:
            logger.error(f"Error processing TXT file: {e}")
            await message.reply_text("❌ Error processing the file. Please try again.")
            if user_id in user_states:
                del user_states[user_id]
    
    async def process_topic_upload(self, message: Message, file_path: str, chat_id: str, user_id: int):
        """Process the TXT file and upload videos to topics"""
        try:
            topic_uploader = TopicUploader(self.bot, chat_id)
            
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
            
            total_lines = len([line for line in lines if line.strip() and not line.startswith('#')])
            processed = 0
            success_count = 0
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                processed += 1
                status_msg = await message.reply_text(f"🔄 Processing {processed}/{total_lines}: `{line}`")
                
                topic_name, video_name, video_url = topic_uploader.parse_input_line(line)
                
                if not all([topic_name, video_name, video_url]):
                    await message.reply_text(f"❌ Line {line_num}: Invalid format")
                    continue
                
                try:
                    # Use your existing download function
                    logger.info(f"Downloading: {video_name} from {video_url}")
                    video_path = await self.download_function(video_url, video_name)
                    
                    if video_path and os.path.exists(video_path):
                        # Upload to topic
                        topic_id = await topic_uploader.get_or_create_topic(topic_name)
                        if topic_id:
                            success = await topic_uploader.upload_video_to_topic(topic_id, video_path, video_name)
                            if success:
                                success_count += 1
                                await message.reply_text(
                                    f"✅ **Success!**\n"
                                    f"• Video: {video_name}\n"
                                    f"• Topic: {topic_name}\n"
                                    f"• Status: Uploaded ✅"
                                )
                            else:
                                await message.reply_text(f"❌ Upload failed: {video_name}")
                        else:
                            await message.reply_text(f"❌ Topic creation failed: {topic_name}")
                        
                        # Cleanup downloaded file
                        try:
                            if os.path.exists(video_path):
                                os.remove(video_path)
                        except Exception as e:
                            logger.error(f"Error cleaning up {video_path}: {e}")
                    else:
                        await message.reply_text(f"❌ Download failed: {video_name}")
                        
                except Exception as e:
                    logger.error(f"Error processing line {line_num}: {e}")
                    await message.reply_text(f"❌ Error processing: {video_name}")
                
                # Delete status message
                await status_msg.delete()
            
            # Final summary
            await message.reply_text(
                f"🎉 **Topic Upload Complete!**\n\n"
                f"**Results:**\n"
                f"• Total processed: {processed}\n"
                f"• Successful: {success_count}\n"
                f"• Failed: {processed - success_count}\n\n"
                f"Check your group **{user_states[user_id]['chat_title']}** to see the topics and videos!"
            )
            
            topic_uploader.close()
            
        except Exception as e:
            logger.error(f"Error in topic upload process: {e}")
            await message.reply_text("❌ Error during topic upload process.")
        finally:
            # Cleanup
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except:
                pass
            if user_id in user_states:
                del user_states[user_id]
    
    async def cancel_operation(self, client, message: Message):
        """Cancel any ongoing operation"""
        user_id = message.from_user.id
        if user_id in user_states:
            del user_states[user_id]
            await message.reply_text("❌ Operation cancelled.")
        else:
            await message.reply_text("No active operation to cancel.")