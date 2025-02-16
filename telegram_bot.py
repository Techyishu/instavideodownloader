import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.error import Conflict, NetworkError
import instaloader
import os
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Create an instance of Instaloader
loader = instaloader.Instaloader()

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
        
        # Download the post
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        loader.download_post(post, target=download_dir)
        
        # Find the video file
        for file in os.listdir(download_dir):
            if file.endswith('.mp4'):
                video_path = os.path.join(download_dir, file)
                # Send the video
                with open(video_path, 'rb') as video:
                    update.message.reply_video(
                        video=video,
                        caption='✅ Here\'s your video!'
                    )
                # Clean up
                os.remove(video_path)
                break
        
        # Clean up other files
        for file in os.listdir(download_dir):
            file_path = os.path.join(download_dir, file)
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Error removing file {file_path}: {e}")
                
    except instaloader.exceptions.InstaloaderException as e:
        update.message.reply_text(
            f'❌ Error: Could not download the video. Make sure:\n'
            f'1. The link is valid\n'
            f'2. The post is public\n'
            f'3. The post contains a video\n\n'
            f'Technical details: {str(e)}'
        )
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        update.message.reply_text(
            '❌ Sorry, something went wrong while processing your request.'
        )

def main() -> None:
    """Start the bot."""
    while True:
        try:
            # Get token from environment variable
            bot_token = os.getenv('BOT_TOKEN')
            if not bot_token:
                raise ValueError("No BOT_TOKEN found in environment variables")
            
            # Create the Updater and pass it your bot's token
            updater = Updater(bot_token)

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
            break  # If we get here, the bot was stopped cleanly
            
        except Conflict as e:
            logger.error(f"Conflict error: {e}")
            logger.info("Waiting for other instance to release the bot...")
            time.sleep(10)  # Wait before retrying
            continue
            
        except NetworkError as e:
            logger.error(f"Network error: {e}")
            time.sleep(5)  # Wait before retrying
            continue
            
        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            raise e

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