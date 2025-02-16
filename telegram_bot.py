import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.error import Conflict, NetworkError
import instaloader
import os
from dotenv import load_dotenv
import time
import random

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# List of user agents to rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1'
]

# Create an instance of Instaloader with custom settings
loader = instaloader.Instaloader(
    download_videos=True,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    download_pictures=False,
    post_metadata_txt_pattern='',
    max_connection_attempts=3,
    user_agent=random.choice(USER_AGENTS),
    request_timeout=30
)

def create_new_session():
    """Create a new session with rotating user agent"""
    loader.context._session.headers['User-Agent'] = random.choice(USER_AGENTS)
    time.sleep(2)  # Add delay between session creations

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    welcome_message = (
        "👋 Welcome to Instagram Video Downloader Bot!\n\n"
        "Just send me an Instagram video link and I'll download it for you.\n"
        "Note: This only works with public Instagram posts."
    )
    update.message.reply_text(welcome_message)

def extract_shortcode(url: str) -> str:
    """Extract the shortcode from an Instagram URL."""
    # Remove trailing slashes
    url = url.rstrip('/')
    # Split the URL and get the second to last part
    return url.split('/')[-2]

def download_video(update: Update, context: CallbackContext) -> None:
    """Download video from the provided Instagram link."""
    url = update.message.text
    chat_id = update.message.chat_id
    
    # Create downloads directory if it doesn't exist
    download_dir = f'downloads_{chat_id}'
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    
    try:
        update.message.reply_text('⏳ Processing your request...')
        
        # Extract the shortcode from the URL
        shortcode = extract_shortcode(url)
        
        # Create new session for this request
        create_new_session()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                post = instaloader.Post.from_shortcode(loader.context, shortcode)
                if not post.is_video:
                    update.message.reply_text('❌ This post does not contain a video.')
                    return
                
                time.sleep(2)  # Rate limiting delay
                loader.download_post(post, target=download_dir)
                break
            except instaloader.exceptions.InstaloaderException as e:
                if 'rate-limited' in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                    create_new_session()  # Try with new session
                    continue
                raise e
        
        # Find and send the video file
        video_found = False
        for file in os.listdir(download_dir):
            if file.endswith('.mp4'):
                video_found = True
                video_path = os.path.join(download_dir, file)
                try:
                    with open(video_path, 'rb') as video:
                        update.message.reply_video(
                            video=video,
                            caption='✅ Here\'s your video!'
                        )
                except Exception as e:
                    update.message.reply_text('❌ Video file too large to send via Telegram.')
                finally:
                    os.remove(video_path)
                break
        
        if not video_found:
            update.message.reply_text('❌ No video found in the post.')
        
        # Clean up directory
        for file in os.listdir(download_dir):
            file_path = os.path.join(download_dir, file)
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Error removing file {file_path}: {e}")
                
    except instaloader.exceptions.InstaloaderException as e:
        error_message = str(e).lower()
        if 'not found' in error_message:
            update.message.reply_text('❌ Post not found. Make sure the link is valid.')
        elif 'private' in error_message:
            update.message.reply_text('❌ This is a private post. I can only download public posts.')
        else:
            update.message.reply_text(
                f'❌ Error: Could not download the video. Make sure:\n'
                f'1. The link is valid\n'
                f'2. The post is public\n'
                f'3. The post contains a video'
            )
        logger.error(f"Instagram error: {str(e)}")
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        update.message.reply_text(
            '❌ Sorry, something went wrong while processing your request.'
        )

def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token
    updater = Updater(os.getenv('BOT_TOKEN'))

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command, 
        download_video
    ))

    # Add error handler
    dispatcher.add_error_handler(error_callback)

    # Start the Bot
    updater.start_polling(drop_pending_updates=True)
    logger.info("Bot started successfully!")

    # Run the bot until you send a signal to stop
    updater.idle()

def error_callback(update: Update, context: CallbackContext) -> None:
    """Error handler function"""
    try:
        raise context.error
    except Conflict:
        logger.warning('Conflict error - another instance is running')
    except NetworkError:
        logger.warning('Network error occurred')
    except Exception as e:
        logger.error(f'Update "{update}" caused error "{context.error}"')

if __name__ == '__main__':
    main() 