import os
import json
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TPE2, TYER, TCON
from mutagen import File
from pydub import AudioSegment
from pydub.silence import trim_silence
from PIL import Image, ImageDraw, ImageFont
import subprocess
import re
import tempfile
import shutil

# تنظیمات لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# توکن ربات را اینجا قرار دهید
BOT_TOKEN = "7906827162:AAGWZAC4gjuNZbqC_FOvY7R1qBy_G07SUj4"

# مسیر فایل‌های پیکربندی
CONFIG_FILE = "macro_configs.json"
DEFAULT_COVER = "default_cover.jpg"
AUDIO_SIGNATURE = "signature.mp3"

class MusicBot:
    def __init__(self):
        self.configs = self.load_configs()
        
    def load_configs(self):
        """بارگیری تنظیمات از فایل"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_configs(self):
        """ذخیره تنظیمات در فایل"""
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.configs, f, ensure_ascii=False, indent=2)
    
    def get_user_config(self, user_id):
        """دریافت تنظیمات کاربر"""
        return self.configs.get(str(user_id), {
            'title': '{original_title}',
            'artist': '{original_artist}',
            'album': '{original_album}',
            'year': '{original_year}',
            'genre': '{original_genre}',
            'apply_cover': True,
            'watermark_text': '',
            'watermark_image': None,
            'remove_urls': True,
            'trim_silence': True,
            'add_signature': True,
            'create_demo': True
        })
    
    def set_user_config(self, user_id, config):
        """تنظیم پیکربندی کاربر"""
        self.configs[str(user_id)] = config
        self.save_configs()

# ایجاد نمونه ربات
music_bot = MusicBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع"""
    keyboard = [
        [InlineKeyboardButton("🎵 تنظیم ماکرو", callback_data="setup_macro")],
        [InlineKeyboardButton("📋 مشاهده تنظیمات فعلی", callback_data="view_config")],
        [InlineKeyboardButton("❓ راهنما", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🎵 خوش آمدید به ربات پردازش موزیک! 

این ربات می‌تواند:
• تگ‌های موزیک را ویرایش کند
• کاور پیشفرض اعمال کند
• فرمت را به MP3 تبدیل کند
• واترمارک اضافه کند
• URL ها را حذف کند
• دو بیت ریت (320 و 64) ایجاد کند
• دمو صوتی (30 ثانیه) بسازد
• سکوت ابتدا و انتها را حذف کند
• امضای صوتی اضافه کند

لطفاً ابتدا ماکرو خود را تنظیم کنید.
    """
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های اینلاین"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "setup_macro":
        await setup_macro_start(query, context)
    elif query.data == "view_config":
        await view_config(query, context)
    elif query.data == "help":
        await show_help(query, context)
    elif query.data.startswith("config_"):
        await handle_config_option(query, context)

async def setup_macro_start(query, context):
    """شروع تنظیم ماکرو"""
    user_id = query.from_user.id
    config = music_bot.get_user_config(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📝 عنوان موزیک", callback_data="config_title")],
        [InlineKeyboardButton("🎤 نام هنرمند", callback_data="config_artist")],
        [InlineKeyboardButton("💿 نام آلبوم", callback_data="config_album")],
        [InlineKeyboardButton("📅 سال انتشار", callback_data="config_year")],
        [InlineKeyboardButton("🎭 ژانر", callback_data="config_genre")],
        [InlineKeyboardButton("🖼️ تنظیمات کاور", callback_data="config_cover")],
        [InlineKeyboardButton("💧 تنظیمات واترمارک", callback_data="config_watermark")],
        [InlineKeyboardButton("✅ ذخیره و تمام", callback_data="save_config")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """
🔧 تنظیم ماکرو موزیک

متغیرهای قابل استفاده:
• {original_title} - عنوان اصلی
• {original_artist} - هنرمند اصلی  
• {original_album} - آلبوم اصلی
• {original_year} - سال اصلی
• {original_genre} - ژانر اصلی
• {user_name} - نام کاربری شما
• {channel_name} - نام کانال (اختیاری)

گزینه مورد نظر را انتخاب کنید:
    """
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def handle_config_option(query, context):
    """مدیریت انتخاب گزینه‌های تنظیمات"""
    user_id = query.from_user.id
    option = query.data.replace("config_", "")
    
    context.user_data['config_option'] = option
    context.user_data['user_id'] = user_id
    
    prompts = {
        'title': 'عنوان جدید موزیک را وارد کنید (از متغیرها استفاده کنید):',
        'artist': 'نام هنرمند جدید را وارد کنید:',
        'album': 'نام آلبوم جدید را وارد کنید:',
        'year': 'سال انتشار را وارد کنید:',
        'genre': 'ژانر موزیک را وارد کنید:',
        'cover': 'کاور پیشفرض جدید را ارسال کنید (عکس):',
        'watermark': 'متن واترمارک را وارد کنید (یا عکس واترمارک ارسال کنید):'
    }
    
    await query.edit_message_text(prompts.get(option, 'مقدار را وارد کنید:'))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت پیام‌های متنی"""
    if 'config_option' in context.user_data:
        await handle_config_input(update, context)
    else:
        await update.message.reply_text("لطفاً ابتدا از منوی اصلی، ماکرو را تنظیم کنید.")

async def handle_config_input(update: Update, context):
    """مدیریت ورودی تنظیمات"""
    user_id = context.user_data['user_id']
    option = context.user_data['config_option']
    value = update.message.text
    
    config = music_bot.get_user_config(user_id)
    config[option] = value
    music_bot.set_user_config(user_id, config)
    
    await update.message.reply_text(f"✅ {option} با موفقیت تنظیم شد!")
    
    # پاک کردن اطلاعات موقت
    del context.user_data['config_option']
    del context.user_data['user_id']

async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت فایل‌های صوتی"""
    user_id = update.message.from_user.id
    config = music_bot.get_user_config(user_id)
    
    if not config:
        await update.message.reply_text("❌ لطفاً ابتدا ماکرو را تنظیم کنید.")
        return
    
    await update.message.reply_text("🔄 در حال پردازش موزیک...")
    
    try:
        # دانلود فایل
        audio_file = await update.message.audio.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
            await audio_file.download_to_drive(temp_file.name)
            original_path = temp_file.name
        
        # پردازش موزیک
        processed_files = await process_audio(original_path, config, user_id)
        
        # ارسال نتایج
        await send_results(update, processed_files)
        
        # پاک‌سازی فایل‌های موقت
        cleanup_temp_files([original_path] + list(processed_files.values()))
        
    except Exception as e:
        logger.error(f"خطا در پردازش صوت: {e}")
        await update.message.reply_text(f"❌ خطا در پردازش: {str(e)}")

async def process_audio(input_path, config, user_id):
    """پردازش کامل فایل صوتی"""
    results = {}
    
    try:
        # بارگیری فایل صوتی
        audio = AudioSegment.from_file(input_path)
        
        # تبدیل به MP3 در صورت نیاز
        if not input_path.lower().endswith('.mp3'):
            mp3_path = input_path.replace(os.path.splitext(input_path)[1], '.mp3')
            audio.export(mp3_path, format="mp3", bitrate="320k")
            input_path = mp3_path
        
        # حذف سکوت از ابتدا و انتها
        if config.get('trim_silence', True):
            audio = trim_silence(audio)
        
        # اضافه کردن امضای صوتی
        if config.get('add_signature', True) and os.path.exists(AUDIO_SIGNATURE):
            signature = AudioSegment.from_file(AUDIO_SIGNATURE)
            audio = signature.overlay(audio)
        
        # ایجاد نسخه 320 کیلوبیت
        high_quality_path = tempfile.mktemp(suffix='_320k.mp3')
        audio.export(high_quality_path, format="mp3", bitrate="320k")
        results['high_quality'] = high_quality_path
        
        # ایجاد نسخه 64 کیلوبیت
        low_quality_path = tempfile.mktemp(suffix='_64k.mp3')
        audio.export(low_quality_path, format="mp3", bitrate="64k")
        
        # ایجاد دمو (ثانیه 30 تا 60)
        if config.get('create_demo', True):
            demo_audio = AudioSegment.from_file(low_quality_path)
            if len(demo_audio) > 60000:  # اگر بیشتر از 60 ثانیه باشد
                demo_audio = demo_audio[30000:60000]  # ثانیه 30 تا 60
            else:
                demo_audio = demo_audio[:30000]  # 30 ثانیه اول
            
            demo_path = tempfile.mktemp(suffix='_demo.ogg')
            demo_audio.export(demo_path, format="ogg")
            results['demo'] = demo_path
        
        # اعمال تگ‌ها و کاور
        await apply_tags_and_cover(high_quality_path, config, user_id)
        await apply_tags_and_cover(low_quality_path, config, user_id)
        
        results['low_quality'] = low_quality_path
        
        return results
        
    except Exception as e:
        logger.error(f"خطا در پردازش صوت: {e}")
        raise e

async def apply_tags_and_cover(audio_path, config, user_id):
    """اعمال تگ‌ها و کاور"""
    try:
        # بارگیری اطلاعات فعلی
        audiofile = MP3(audio_path, ID3=ID3)
        if audiofile.tags is None:
            audiofile.add_tags()
        
        # دریافت تگ‌های اصلی
        original_tags = {
            'original_title': str(audiofile.tags.get('TIT2', '')),
            'original_artist': str(audiofile.tags.get('TPE1', '')),
            'original_album': str(audiofile.tags.get('TALB', '')),
            'original_year': str(audiofile.tags.get('TYER', '')),
            'original_genre': str(audiofile.tags.get('TCON', '')),
            'user_name': f"@user_{user_id}",
            'channel_name': config.get('channel_name', '')
        }
        
        # حذف URL ها از تگ‌های قدیمی
        if config.get('remove_urls', True):
            for tag_name in ['TIT2', 'TPE1', 'TALB', 'TPE2']:
                if tag_name in audiofile.tags:
                    old_value = str(audiofile.tags[tag_name])
                    new_value = remove_urls_and_usernames(old_value)
                    original_tags[f'original_{tag_name.lower().replace("tpe1", "artist").replace("tit2", "title").replace("talb", "album")}'] = new_value
        
        # اعمال تگ‌های جدید
        new_title = format_template(config.get('title', '{original_title}'), original_tags)
        new_artist = format_template(config.get('artist', '{original_artist}'), original_tags)
        new_album = format_template(config.get('album', '{original_album}'), original_tags)
        new_year = format_template(config.get('year', '{original_year}'), original_tags)
        new_genre = format_template(config.get('genre', '{original_genre}'), original_tags)
        
        audiofile.tags['TIT2'] = TIT2(encoding=3, text=new_title)
        audiofile.tags['TPE1'] = TPE1(encoding=3, text=new_artist)
        audiofile.tags['TALB'] = TALB(encoding=3, text=new_album)
        audiofile.tags['TYER'] = TYER(encoding=3, text=new_year)
        audiofile.tags['TCON'] = TCON(encoding=3, text=new_genre)
        
        # اعمال کاور
        if config.get('apply_cover', True) and os.path.exists(DEFAULT_COVER):
            cover_path = DEFAULT_COVER
            
            # اعمال واترمارک در صورت نیاز
            if config.get('watermark_text') or config.get('watermark_image'):
                cover_path = await apply_watermark(DEFAULT_COVER, config)
            
            with open(cover_path, 'rb') as albumart:
                audiofile.tags['APIC'] = APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc=u'Cover',
                    data=albumart.read()
                )
        
        audiofile.save()
        
    except Exception as e:
        logger.error(f"خطا در اعمال تگ‌ها: {e}")

async def apply_watermark(image_path, config):
    """اعمال واترمارک بر روی تصویر"""
    try:
        img = Image.open(image_path)
        
        if config.get('watermark_text'):
            # واترمارک متنی
            draw = ImageDraw.Draw(img)
            # استفاده از فونت پیشفرض
            try:
                font = ImageFont.truetype("arial.ttf", 40)
            except:
                font = ImageFont.load_default()
            
            text = config['watermark_text']
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # محاسبه موقعیت مرکز پایین
            x = (img.width - text_width) // 2
            y = img.height - text_height - 20
            
            # رسم سایه
            draw.text((x+2, y+2), text, font=font, fill=(0, 0, 0, 128))
            # رسم متن اصلی
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        
        # ذخیره تصویر واترمارک شده
        watermarked_path = tempfile.mktemp(suffix='_watermarked.jpg')
        img.save(watermarked_path, 'JPEG')
        return watermarked_path
        
    except Exception as e:
        logger.error(f"خطا در اعمال واترمارک: {e}")
        return image_path

def remove_urls_and_usernames(text):
    """حذف URL ها و یوزرنیم‌ها از متن"""
    # حذف URL ها
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    # حذف یوزرنیم‌ها
    text = re.sub(r'@\w+', '', text)
    # حذف فضاهای اضافی
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def format_template(template, variables):
    """فرمت کردن الگو با متغیرها"""
    try:
        return template.format(**variables)
    except KeyError as e:
        logger.warning(f"متغیر ناشناخته: {e}")
        return template

async def send_results(update, files):
    """ارسال نتایج پردازش"""
    try:
        # ارسال کاور با تگ‌ها
        await update.message.reply_text("✅ پردازش کامل شد!\n\n📸 کاور با تگ‌های جدید:")
        
        if os.path.exists(DEFAULT_COVER):
            with open(DEFAULT_COVER, 'rb') as cover:
                await update.message.reply_photo(cover, caption="🎵 کاور موزیک با تگ‌های جدید")
        
        # ارسال دمو
        if 'demo' in files and os.path.exists(files['demo']):
            await update.message.reply_text("🎧 نمونه 30 ثانیه‌ای:")
            with open(files['demo'], 'rb') as demo:
                await update.message.reply_voice(demo, caption="🎵 دمو موزیک (30 ثانیه)")
        
        # ارسال نسخه نهایی با کیفیت بالا
        if 'high_quality' in files and os.path.exists(files['high_quality']):
            await update.message.reply_text("🎵 موزیک نهایی (320 کیلوبیت):")
            with open(files['high_quality'], 'rb') as audio:
                await update.message.reply_audio(
                    audio,
                    caption="🎵 موزیک پردازش شده - کیفیت بالا (320k)",
                    title="Processed Audio"
                )
                
    except Exception as e:
        logger.error(f"خطا در ارسال نتایج: {e}")
        await update.message.reply_text(f"❌ خطا در ارسال: {str(e)}")

def cleanup_temp_files(file_paths):
    """پاک‌سازی فایل‌های موقت"""
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.warning(f"خطا در پاک‌سازی فایل {file_path}: {e}")

async def view_config(query, context):
    """نمایش تنظیمات فعلی"""
    user_id = query.from_user.id
    config = music_bot.get_user_config(user_id)
    
    config_text = f"""
📋 تنظیمات فعلی شما:

📝 عنوان: {config.get('title', 'تنظیم نشده')}
🎤 هنرمند: {config.get('artist', 'تنظیم نشده')}
💿 آلبوم: {config.get('album', 'تنظیم نشده')}
📅 سال: {config.get('year', 'تنظیم نشده')}
🎭 ژانر: {config.get('genre', 'تنظیم نشده')}

🖼️ کاور پیشفرض: {'✅ فعال' if config.get('apply_cover') else '❌ غیرفعال'}
💧 واترمارک: {config.get('watermark_text', 'تنظیم نشده')}
🔗 حذف URL: {'✅ فعال' if config.get('remove_urls') else '❌ غیرفعال'}
🔇 حذف سکوت: {'✅ فعال' if config.get('trim_silence') else '❌ غیرفعال'}
🎵 امضای صوتی: {'✅ فعال' if config.get('add_signature') else '❌ غیرفعال'}
🎧 ایجاد دمو: {'✅ فعال' if config.get('create_demo') else '❌ غیرفعال'}
    """
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(config_text, reply_markup=reply_markup)

async def show_help(query, context):
    """نمایش راهنما"""
    help_text = """
📖 راهنمای استفاده:

1️⃣ ابتدا با دکمه "تنظیم ماکرو" تنظیمات خود را انجام دهید
2️⃣ فایل صوتی خود را ارسال کنید
3️⃣ ربات موزیک را پردازش کرده و نتیجه را ارسال می‌کند

🔧 قابلیت‌ها:
• تغییر تگ‌های موزیک
• اعمال کاور پیشفرض
• تبدیل فرمت به MP3
• اضافه کردن واترمارک
• حذف URL و یوزرنیم‌ها
• ایجاد دو نسخه (320k و 64k)
• ساخت دمو 30 ثانیه‌ای
• حذف سکوت
• اضافه کردن امضای صوتی

📝 متغیرهای قابل استفاده:
{original_title} - عنوان اصلی
{original_artist} - هنرمند اصلی  
{original_album} - آلبوم اصلی
{user_name} - نام کاربری شما
    """
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(help_text, reply_markup=reply_markup)

def main():
    """اجرای اصلی ربات"""
    # ایجاد اپلیکیشن
    application = Application.builder().token(BOT_TOKEN).build()
    
    # اضافه کردن هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_handler(MessageHandler(filters.AUDIO, audio_handler))
    
    # شروع ربات
    print("🎵 ربات پردازش موزیک شروع شد...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
