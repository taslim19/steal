# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.errors import BadRequest, FloodWait
from shared_client import app
from plugins.start import subscribe as sub
from utils.custom_filters import login_in_progress
import asyncio
import re

# Store user conversation state
FORWARD_STATE = {}

async def parse_group_topic(input_text):
    """
    Parse group_id/topic_id format
    Examples:
    - "-1001234567890/123" -> group_id: -1001234567890, topic_id: 123
    - "-1001234567890" -> group_id: -1001234567890, topic_id: None
    """
    parts = input_text.strip().split('/')
    if len(parts) == 2:
        try:
            group_id = int(parts[0])
            topic_id = int(parts[1])
            return group_id, topic_id
        except ValueError:
            return None, None
    elif len(parts) == 1:
        try:
            group_id = int(parts[0])
            return group_id, None
        except ValueError:
            return None, None
    return None, None

async def parse_message_range(input_text):
    """
    Parse message range format
    Examples:
    - "1-100" -> from_id: 1, to_id: 100
    - "100" -> from_id: 100, to_id: 100 (single message)
    - "all" -> from_id: None, to_id: None (all messages)
    """
    input_text = input_text.strip().lower()
    if input_text == 'all':
        return None, None
    
    if '-' in input_text:
        parts = input_text.split('-')
        if len(parts) == 2:
            try:
                from_id = int(parts[0])
                to_id = int(parts[1])
                return from_id, to_id
            except ValueError:
                return None, None
    else:
        try:
            msg_id = int(input_text)
            return msg_id, msg_id
        except ValueError:
            return None, None
    
    return None, None

@app.on_message(filters.command("forward") & filters.private)
async def forward_command(client: app, message: Message):
    """Start the forward command process"""
    user_id = message.from_user.id
    
    # Check force subscription
    if await sub(client, message) == 1:
        return
    
    # Initialize conversation state
    FORWARD_STATE[user_id] = {'step': 'source_group'}
    
    await message.reply_text(
        "📤 **Forward Messages from Forum Topic**\n\n"
        "Send me the source group ID with topic ID in this format:\n"
        "`-1001234567890/123`\n\n"
        "Where:\n"
        "- `-1001234567890` is the group ID\n"
        "- `123` is the topic ID (message_thread_id)\n\n"
        "Or just send group ID if you want to forward from the main chat:\n"
        "`-1001234567890`\n\n"
        "Send /cancel to cancel this operation."
    )

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_forward(client: app, message: Message):
    """Cancel the forward operation"""
    user_id = message.from_user.id
    if user_id in FORWARD_STATE:
        del FORWARD_STATE[user_id]
        await message.reply_text("✅ Forward operation cancelled.")
    else:
        await message.reply_text("No active forward operation to cancel.")

@app.on_message(
    filters.text & 
    filters.private & 
    ~login_in_progress & 
    ~filters.command(['start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 
                     'pay', 'redeem', 'gencode', 'single', 'generate', 'keyinfo', 
                     'encrypt', 'decrypt', 'keys', 'setbot', 'rembot', 'forward'])
)
async def handle_forward_input(client: app, message: Message):
    """Handle multi-step input for forward command"""
    user_id = message.from_user.id
    
    if user_id not in FORWARD_STATE:
        return
    
    step = FORWARD_STATE[user_id].get('step')
    
    if step == 'source_group':
        # Parse source group and topic
        group_id, topic_id = await parse_group_topic(message.text)
        
        if group_id is None:
            await message.reply_text(
                "❌ Invalid format. Please send group ID with topic ID:\n"
                "`-1001234567890/123`\n\n"
                "Or just group ID:\n"
                "`-1001234567890`"
            )
            return
        
        FORWARD_STATE[user_id].update({
            'source_group': group_id,
            'topic_id': topic_id,
            'step': 'destination'
        })
        
        topic_info = f" (Topic ID: {topic_id})" if topic_id else ""
        await message.reply_text(
            f"✅ Source group set: `{group_id}`{topic_info}\n\n"
            "Now send me the destination channel/group ID:\n"
            "`-1001234567890`\n\n"
            "Send /cancel to cancel."
        )
    
    elif step == 'destination':
        # Parse destination channel
        try:
            dest_id = int(message.text.strip())
        except ValueError:
            await message.reply_text(
                "❌ Invalid channel ID. Please send a valid channel/group ID:\n"
                "`-1001234567890`"
            )
            return
        
        FORWARD_STATE[user_id].update({
            'destination': dest_id,
            'step': 'message_range'
        })
        
        await message.reply_text(
            f"✅ Destination set: `{dest_id}`\n\n"
            "Now send me the message range:\n\n"
            "**Options:**\n"
            "• `all` - Forward all messages from the topic\n"
            "• `1-100` - Forward messages from ID 1 to 100\n"
            "• `50` - Forward only message ID 50\n\n"
            "Send /cancel to cancel."
        )
    
    elif step == 'message_range':
        # Parse message range
        from_id, to_id = await parse_message_range(message.text)
        
        if from_id is None and to_id is None and message.text.strip().lower() != 'all':
            await message.reply_text(
                "❌ Invalid format. Please send:\n"
                "• `all` - for all messages\n"
                "• `1-100` - for range\n"
                "• `50` - for single message"
            )
            return
        
        # Get all stored data
        source_group = FORWARD_STATE[user_id]['source_group']
        topic_id = FORWARD_STATE[user_id].get('topic_id')
        destination = FORWARD_STATE[user_id]['destination']
        
        # Start forwarding
        status_msg = await message.reply_text("🔄 Starting forward process...")
        
        try:
            # Verify we can access source group
            try:
                source_chat = await client.get_chat(source_group)
            except Exception as e:
                await status_msg.edit_text(
                    f"❌ Cannot access source group: {str(e)[:100]}\n\n"
                    "Make sure the bot is added to the group and has permission."
                )
                del FORWARD_STATE[user_id]
                return
            
            # Verify we can access destination
            try:
                dest_chat = await client.get_chat(destination)
            except Exception as e:
                await status_msg.edit_text(
                    f"❌ Cannot access destination: {str(e)[:100]}\n\n"
                    "Make sure the bot is added to the channel/group and has permission."
                )
                del FORWARD_STATE[user_id]
                return
            
            # Determine message IDs to forward
            if message.text.strip().lower() == 'all':
                # Get all messages from the topic
                await status_msg.edit_text(
                    "⚠️ Forwarding all messages from topic...\n"
                    "This may take a while. Processing..."
                )
                
                forwarded_count = 0
                failed_count = 0
                last_message_id = None
                
                try:
                    # Get messages from the topic
                    # If topic_id is set, we need to filter messages by message_thread_id
                    async for msg in client.get_chat_history(source_group, limit=1000):
                        # Check if message is in the topic (if topic_id is set)
                        if topic_id:
                            # Check message_thread_id attribute
                            msg_thread_id = getattr(msg, 'message_thread_id', None)
                            if msg_thread_id != topic_id:
                                continue
                        
                        try:
                            # Forward the message
                            await client.forward_messages(
                                chat_id=destination,
                                from_chat_id=source_group,
                                message_ids=msg.id
                            )
                            forwarded_count += 1
                            last_message_id = msg.id
                            
                            if forwarded_count % 10 == 0:
                                await status_msg.edit_text(
                                    f"🔄 Forwarded {forwarded_count} messages...\n"
                                    f"Last message ID: {msg.id}"
                                )
                            
                            # Small delay to avoid flood
                            await asyncio.sleep(0.5)
                            
                        except FloodWait as e:
                            await asyncio.sleep(e.value)
                            continue
                        except Exception as e:
                            failed_count += 1
                            print(f"Error forwarding message {msg.id}: {e}")
                            continue
                    
                    await status_msg.edit_text(
                        f"✅ Forward completed!\n\n"
                        f"📊 **Stats:**\n"
                        f"• Forwarded: {forwarded_count}\n"
                        f"• Failed: {failed_count}\n"
                        f"• Last message ID: {last_message_id if last_message_id else 'N/A'}"
                    )
                    
                except Exception as e:
                    await status_msg.edit_text(
                        f"❌ Error during forwarding: {str(e)[:200]}"
                    )
            else:
                # Forward specific range
                await status_msg.edit_text(
                    f"🔄 Forwarding messages {from_id} to {to_id}...\n"
                    "Processing..."
                )
                
                message_ids = list(range(from_id, to_id + 1))
                forwarded_count = 0
                failed_count = 0
                
                for msg_id in message_ids:
                    try:
                        # Get the message first to check if it's in the topic
                        if topic_id:
                            try:
                                msg = await client.get_messages(source_group, msg_id)
                                # Check if message belongs to the topic
                                msg_thread_id = getattr(msg, 'message_thread_id', None)
                                if msg_thread_id != topic_id:
                                    failed_count += 1
                                    continue
                            except Exception:
                                failed_count += 1
                                continue
                        
                        # Forward the message
                        await client.forward_messages(
                            chat_id=destination,
                            from_chat_id=source_group,
                            message_ids=msg_id
                        )
                        forwarded_count += 1
                        
                        if forwarded_count % 10 == 0:
                            await status_msg.edit_text(
                                f"🔄 Forwarded {forwarded_count}/{len(message_ids)} messages..."
                            )
                        
                        await asyncio.sleep(0.5)
                        
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                        continue
                    except BadRequest as e:
                        # Message might not exist or not accessible
                        failed_count += 1
                        print(f"Message {msg_id} not found or not accessible: {e}")
                        continue
                    except Exception as e:
                        failed_count += 1
                        print(f"Error forwarding message {msg_id}: {e}")
                        continue
                
                await status_msg.edit_text(
                    f"✅ Forward completed!\n\n"
                    f"📊 **Stats:**\n"
                    f"• Forwarded: {forwarded_count}\n"
                    f"• Failed: {failed_count}\n"
                    f"• Range: {from_id} to {to_id}"
                )
            
        except Exception as e:
            await status_msg.edit_text(
                f"❌ Error: {str(e)[:200]}"
            )
        finally:
            # Clean up state
            if user_id in FORWARD_STATE:
                del FORWARD_STATE[user_id]
