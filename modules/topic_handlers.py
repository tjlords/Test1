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
    
    async def topic_upload_start(self, client, message: Message):
        """Start topic upload process"""
        user_id = message.from_user.id
        
        await message.reply_text(
            "🤖 **Topic Upload Mode**\n\n"
            "Please send me the **Group/Chat ID** where you want to upload videos with topics.\n\n"
            "**How to get Chat ID:**\n"
            "• Use `/id` command in your group (if bot is admin)\n"
            "• Or send the Chat ID directly\n"
            "• Format: `-1001234567890`\n\n"
            "Type /cancel to cancel this operation."
        )
        
        user_states[user_id] = {'step': 'awaiting_chat_id'}
        
        # Set up temporary handlers for topic upload session
        @self.bot.on_message(filters.text & filters.private & ~filters.command)
        async def temp_text_handler(client, msg):
            if msg.from_user.id == user_id:
                await self.handle_text_message(client, msg)
        
        @self.bot.on_message(filters.document & filters.private)
        async def temp_doc_handler(client, msg):
            if msg.from_user.id == user_id:
                await self.handle_txt_file(client, msg)
        
        # Store the temporary handlers so we can remove them later
        user_states[user_id]['temp_handlers'] = {
            'text': temp_text_handler,
            'document': temp_doc_handler
        }
    
    async def handle_text_message(self, client, message: Message):
        """Handle text messages during topic upload process"""
        user_id = message.from_user.id
        text = message.text.strip()
        
        if user_id not in user_states:
            return
        
        state = user_states[user_id]
        
        if state['step'] == 'awaiting_chat_id':
            # Check if it's a valid chat ID format
            if self.is_valid_chat_id(text):
                await self.verify_and_proceed(message, text, user_id)
            else:
                await message.reply_text(
                    "❌ **Invalid Chat ID format!**\n\n"
                    "Please send a valid Chat ID in this format:\n"
                    "`-1001234567890`\n\n"
                    "Make sure:\n"
                    "• It starts with `-100`\n"
                    "• It contains only numbers\n"
                    "• It's the correct group ID\n\n"
                    "You can get it by using `/id` in your group."
                )
    
    def is_valid_chat_id(self, text: str):
        """Check if the text is a valid chat ID format"""
        if text.startswith('-100') and text[4:].isdigit():
            return True
        return False
    
    async def verify_and_proceed(self, message: Message, chat_id: str, user_id: int):
        """Verify chat access and proceed to next step"""
        try:
            await message.reply_text("🔍 **Verifying chat access...**")
            
            # Initialize topic uploader for verification
            topic_uploader = TopicUploader(self.bot, chat_id)
            success, chat_title, is_forum = await topic_uploader.test_connection()
            topic_uploader.close()
            
            if success:
                if is_forum:
                    user_states[user_id] = {
                        'step': 'awaiting_txt_file',
                        'chat_id': chat_id,
                        'chat_title': chat_title,
                        'temp_handlers': user_states[user_id].get('temp_handlers', {})
                    }
                    
                    await message.reply_text(
                        f"✅ **Chat Verified Successfully!**\n\n"
                        f"**Group:** {chat_title}\n"
                        f"**Chat ID:** `{chat_id}`\n"
                        f"**Topics Support:** ✅ Enabled\n\n"
                        "📁 **Now please send me the TXT file** containing your video links in this format:\n\n"
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
                    await self.cleanup_user_state(user_id)
            else:
                await message.reply_text(
                    "❌ **Chat Access Failed**\n\n"
                    "**Please ensure:**\n"
                    "• The bot is added to the group\n"
                    "• The bot has **admin permissions**\n"
                    "• The Chat ID is correct\n"
                    "• The group has **topics enabled**\n\n"
                    "**Get the correct Chat ID:**\n"
                    "1. Add bot to group as admin\n"
                    "2. Use `/id` command in the group\n"
                    "3. Send me the ID shown\n\n"
                    "Try again with /topicupload"
                )
                await self.cleanup_user_state(user_id)
                
        except Exception as e:
            logger.error(f"Error verifying chat: {e}")
            await message.reply_text(
                f"❌ **Error verifying chat:** `{str(e)}`\n\n"
                "Please check:\n"
                "• Bot is admin in the group\n"
                "• Chat ID is correct\n"
                "• Try again with /topicupload"
            )
            await self.cleanup_user_state(user_id)
    
    async def handle_txt_file(self, client, message: Message):
        """Handle uploaded TXT file for topic upload"""
        user_id = message.from_user.id
        
        if user_id not in user_states or user_states[user_id]['step'] != 'awaiting_txt_file':
            # This is a normal TXT file upload, let it pass through to your existing handler
            return
        
        # Check if it's a txt file
        if not message.document or not message.document.file_name.endswith('.txt'):
            await message.reply_text("❌ Please send a .txt file")
            return
        
        try:
            # Download TXT file to temporary file
            temp_file_path = await message.download(in_memory=False)
            
            state = user_states[user_id]
            chat_id = state['chat_id']
            chat_title = state['chat_title']
            
            await message.reply_text(
                f"📁 **File Received!**\n\n"
                f"**Group:** {chat_title}\n"
                f"**Starting topic upload process...**\n\n"
                "⏳ **This may take a while depending on file size...**"
            )
            
            # Process the file asynchronously to avoid timeout
            asyncio.create_task(self.process_topic_upload(message, temp_file_path, chat_id, user_id))
            
        except Exception as e:
            logger.error(f"Error processing TXT file: {e}")
            await message.reply_text("❌ Error processing the file. Please try again.")
            await self.cleanup_user_state(user_id)
    
    async def process_topic_upload(self, message: Message, file_path: str, chat_id: str, user_id: int):
        """Process the TXT file and upload videos to topics"""
        try:
            topic_uploader = TopicUploader(self.bot, chat_id)
            
            # Read and parse the file
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
            
            # Filter valid lines
            valid_lines = []
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    valid_lines.append((line_num, line))
            
            total_lines = len(valid_lines)
            
            if total_lines == 0:
                await message.reply_text("❌ No valid lines found in the TXT file!")
                return
            
            await message.reply_text(f"📊 **Found {total_lines} videos to process...**")
            
            processed = 0
            success_count = 0
            
            for line_num, line in valid_lines:
                processed += 1
                status_msg = await message.reply_text(f"🔄 **Processing {processed}/{total_lines}**\n`{line}`")
                
                # Parse the line
                topic_name, video_name, video_url = topic_uploader.parse_input_line(line)
                
                if not all([topic_name, video_name, video_url]):
                    await message.reply_text(f"❌ **Line {line_num}: Invalid format**\n`{line}`")
                    await status_msg.delete()
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
                                    f"• **Video:** {video_name}\n"
                                    f"• **Topic:** {topic_name}\n"
                                    f"• **Status:** Uploaded ✅"
                                )
                            else:
                                await message.reply_text(f"❌ **Upload failed:** {video_name}")
                        else:
                            await message.reply_text(f"❌ **Topic creation failed:** {topic_name}")
                        
                        # Cleanup downloaded file
                        try:
                            if os.path.exists(video_path):
                                os.remove(video_path)
                        except Exception as e:
                            logger.error(f"Error cleaning up {video_path}: {e}")
                    else:
                        await message.reply_text(f"❌ **Download failed:** {video_name}")
                        
                except Exception as e:
                    logger.error(f"Error processing line {line_num}: {e}")
                    await message.reply_text(f"❌ **Error processing:** {video_name}\n`{str(e)}`")
                
                # Delete status message
                await status_msg.delete()
                await asyncio.sleep(1)  # Small delay between processes
            
            # Final summary
            await message.reply_text(
                f"🎉 **Topic Upload Complete!**\n\n"
                f"**Results:**\n"
                f"• **Total processed:** {processed}\n"
                f"• **Successful:** {success_count}\n"
                f"• **Failed:** {processed - success_count}\n\n"
                f"Check your group **{user_states[user_id]['chat_title']}** to see the topics and videos!"
            )
            
            topic_uploader.close()
            
        except Exception as e:
            logger.error(f"Error in topic upload process: {e}")
            await message.reply_text(f"❌ **Error during topic upload process:**\n`{str(e)}`")
        finally:
            # Cleanup
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except:
                pass
            await self.cleanup_user_state(user_id)
    
    async def cleanup_user_state(self, user_id: int):
        """Clean up user state and remove temporary handlers"""
        if user_id in user_states:
            # Remove temporary handlers if they exist
            temp_handlers = user_states[user_id].get('temp_handlers', {})
            # Note: In Pyrogram, we can't easily remove handlers once added
            # But they'll only trigger for the specific user ID, so it's safe
            del user_states[user_id]
    
    async def cancel_operation(self, client, message: Message):
        """Cancel any ongoing operation"""
        user_id = message.from_user.id
        if user_id in user_states:
            await self.cleanup_user_state(user_id)
            await message.reply_text("❌ Topic upload operation cancelled.")
        else:
            await message.reply_text("No active topic upload operation to cancel.")