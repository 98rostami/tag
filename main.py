import os
import asyncio
import tempfile
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import mutagen
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TCON
from mutagen.mp3 import MP3
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import telebot
from telebot.async_telebot import AsyncTeleBot
from telebot import types
import aiofiles
import re

# توکن ربات تلگرام
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
bot = AsyncTeleBot(BOT_TOKEN)

# مسیر فایل امضای صوتی
SIGNATURE_AUDIO_PATH = "signature.mp3"  # فایل امضای صوتی که باید در پوشه ربات باشد

# ذخیره اطلاعات کاربران
user_sessions = {}

class MusicEditor:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def extract_tags_and_cover(self, file_path):
        """استخراج تگ‌ها و کاور از فایل موزیک"""
        try:
            audio_file = mutagen.File(file_path)
            if audio_file is None:
                return {}, None
            
            tags = {}
            cover_data = None
            
            if hasattr(audio_file, 'tags') and audio_file.tags:
                # استخراج تگ‌های مختلف
                for key, value in audio_file.tags.items():
                    if isinstance(value, list):
                        value = value[0] if value else ""
                    tags[key] = str(value)
                
                # استخراج کاور
                if 'APIC:' in audio_file.tags:
                    cover_data = audio_file.tags['APIC:'].data
                elif hasattr(audio_file.tags, 'get'):
                    apic = audio_file.tags.get('APIC:')
                    if apic:
                        cover_data = apic.data
            
            return tags, cover_data
        except Exception as e:
            print(f"خطا در استخراج تگ‌ها: {e}")
            return {}, None
    
    def create_tag_image(self, tags, cover_data=None):
        """ایجاد تصویر نمایش تگ‌ها"""
        try:
            # ایجاد کانوس
            width, height = 800, 600
            if cover_data:
                # اگر کاور موجود است، از آن استفاده کن
                cover_img = Image.open(BytesIO(cover_data))
                cover_img = cover_img.resize((width, height))
                img = cover_img.copy()
            else:
                # کاور پیش‌فرض
                img = Image.new('RGB', (width, height), color='#1a1a1a')
            
            # اضافه کردن لایه شفاف برای متن
            overlay = Image.new('RGBA', (width, height), (0, 0, 0, 180))
            img = Image.alpha_composite(img.convert('RGBA'), overlay)
            
            draw = ImageDraw.Draw(img)
            
            # تنظیم فونت
            try:
                font_title = ImageFont.truetype("arial.ttf", 24)
                font_normal = ImageFont.truetype("arial.ttf", 18)
            except:
                font_title = ImageFont.load_default()
                font_normal = ImageFont.load_default()
            
            # نمایش تگ‌ها
            y_pos = 50
            for key, value in tags.items():
                if value and str(value).strip():
                    text = f"{key}: {value}"
                    draw.text((50, y_pos), text, fill='white', font=font_normal)
                    y_pos += 30
                    if y_pos > height - 100:
                        break
            
            # ذخیره تصویر
            output_path = os.path.join(self.temp_dir, "tags_display.png")
            img.convert('RGB').save(output_path)
            return output_path
        except Exception as e:
            print(f"خطا در ایجاد تصویر تگ‌ها: {e}")
            return None
    
    def clean_tags(self, tags):
        """پاک کردن یوزرنیم‌ها و URL‌ها از تگ‌ها"""
        cleaned_tags = {}
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        username_pattern = r'@[a-zA-Z0-9_]+'
        
        for key, value in tags.items():
            if isinstance(value, str):
                # حذف URL‌ها
                value = re.sub(url_pattern, '', value)
                # حذف یوزرنیم‌ها
                value = re.sub(username_pattern, '', value)
                # پاک کردن فضاهای اضافی
                value = ' '.join(value.split())
                # اضافه کردن یوزرنیم جدید
                if value.strip():
                    value += " @abar"
                else:
                    value = "@abar"
                cleaned_tags[key] = value
            else:
                cleaned_tags[key] = value
        
        return cleaned_tags
    
    def apply_tags_and_cover(self, audio_path, tags, cover_path=None):
        """اعمال تگ‌ها و کاور جدید به فایل"""
        try:
            audio_file = MP3(audio_path)
            
            # حذف تگ‌های قبلی
            if audio_file.tags:
                audio_file.tags.delete()
            
            # اضافه کردن تگ‌های جدید
            audio_file.tags = ID3()
            
            # پاک کردن و اعمال تگ‌ها
            cleaned_tags = self.clean_tags(tags)
            
            for key, value in cleaned_tags.items():
                if key.upper() == 'TIT2' or 'TITLE' in key.upper():
                    audio_file.tags.add(TIT2(encoding=3, text=value))
                elif key.upper() == 'TPE1' or 'ARTIST' in key.upper():
                    audio_file.tags.add(TPE1(encoding=3, text=value))
                elif key.upper() == 'TALB' or 'ALBUM' in key.upper():
                    audio_file.tags.add(TALB(encoding=3, text=value))
                elif key.upper() == 'TDRC' or 'DATE' in key.upper():
                    audio_file.tags.add(TDRC(encoding=3, text=value))
                elif key.upper() == 'TCON' or 'GENRE' in key.upper():
                    audio_file.tags.add(TCON(encoding=3, text=value))
            
            # اضافه کردن کاور
            if cover_path and os.path.exists(cover_path):
                with open(cover_path, 'rb') as cover_file:
                    cover_data = cover_file.read()
                    audio_file.tags.add(APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Cover',
                        data=cover_data
                    ))
            
            audio_file.save()
            return True
        except Exception as e:
            print(f"خطا در اعمال تگ‌ها: {e}")
            return False
    
    def create_bitrate_versions(self, input_path):
        """ایجاد نسخه‌های مختلف بیت‌ریت"""
        try:
            audio = AudioSegment.from_mp3(input_path)
            
            # نسخه 320 kbps
            output_320 = os.path.join(self.temp_dir, "320kbps.mp3")
            audio.export(output_320, format="mp3", bitrate="320k")
            
            # نسخه 64 kbps
            output_64 = os.path.join(self.temp_dir, "64kbps.mp3")
            audio.export(output_64, format="mp3", bitrate="64k")
            
            return output_320, output_64
        except Exception as e:
            print(f"خطا در ایجاد نسخه‌های بیت‌ریت: {e}")
            return None, None
    
    def create_voice_preview(self, audio_64_path):
        """ایجاد پیش‌نمایش صوتی (ثانیه 30 تا 60)"""
        try:
            audio = AudioSegment.from_mp3(audio_64_path)
            
            # برش ثانیه 30 تا 60
            start_time = 30 * 1000  # به میلی‌ثانیه
            end_time = 60 * 1000
            
            if len(audio) > end_time:
                preview = audio[start_time:end_time]
            else:
                # اگر موزیک کوتاه‌تر است
                preview = audio[start_time:] if len(audio) > start_time else audio
            
            output_path = os.path.join(self.temp_dir, "voice_preview.ogg")
            preview.export(output_path, format="ogg")
            
            return output_path
        except Exception as e:
            print(f"خطا در ایجاد پیش‌نمایش: {e}")
            return None
    
    def remove_silence(self, audio_path):
        """حذف سکوت از ابتدا و انتهای فایل"""
        try:
            audio = AudioSegment.from_mp3(audio_path)
            
            # تشخیص قسمت‌های غیرساکت
            nonsilent_ranges = detect_nonsilent(
                audio, 
                min_silence_len=1000,  # حداقل 1 ثانیه سکوت
                silence_thresh=-40     # آستانه سکوت
            )
            
            if nonsilent_ranges:
                start_trim = nonsilent_ranges[0][0]
                end_trim = nonsilent_ranges[-1][1]
                trimmed_audio = audio[start_trim:end_trim]
            else:
                trimmed_audio = audio
            
            output_path = os.path.join(self.temp_dir, "trimmed_audio.mp3")
            trimmed_audio.export(output_path, format="mp3")
            
            return output_path
        except Exception as e:
            print(f"خطا در حذف سکوت: {e}")
            return audio_path
    
    def add_signature(self, audio_path):
        """اضافه کردن امضای صوتی"""
        try:
            if not os.path.exists(SIGNATURE_AUDIO_PATH):
                print("فایل امضای صوتی یافت نشد")
                return audio_path
            
            main_audio = AudioSegment.from_mp3(audio_path)
            signature = AudioSegment.from_mp3(SIGNATURE_AUDIO_PATH)
            
            # ترکیب امضا با موزیک اصلی
            combined = signature.overlay(main_audio)
            
            output_path = os.path.join(self.temp_dir, "with_signature.mp3")
            combined.export(output_path, format="mp3")
            
            return output_path
        except Exception as e:
            print(f"خطا در اضافه کردن امضا: {e}")
            return audio_path

# دستورات ربات
@bot.message_handler(commands=['start'])
async def start_command(message):
    welcome_text = """🎵 خوش آمدید به ربات ویرایش موزیک!

برای شروع، لطفاً فایل موزیک خود را ارسال کنید.

قابلیت‌های ربات:
✅ استخراج و نمایش تگ‌ها
✅ اعمال کاور و تگ‌های جدید
✅ پاک کردن یوزرنیم‌ها و لینک‌ها
✅ ایجاد نسخه‌های 320 و 64 کیلوبیت
✅ ایجاد پیش‌نمایش صوتی
✅ حذف سکوت اضافی
✅ اضافه کردن امضای صوتی"""
    
    await bot.send_message(message.chat.id, welcome_text)

@bot.message_handler(content_types=['audio', 'document'])
async def handle_music(message):
    try:
        user_id = message.from_user.id
        
        # بررسی نوع فایل
        if message.content_type == 'audio':
            file_info = await bot.get_file(message.audio.file_id)
            file_name = message.audio.file_name or "music.mp3"
        elif message.content_type == 'document':
            if not message.document.mime_type.startswith('audio/'):
                await bot.reply_to(message, "❌ لطفاً فقط فایل‌های صوتی ارسال کنید.")
                return
            file_info = await bot.get_file(message.document.file_id)
            file_name = message.document.file_name or "music.mp3"
        
        # دانلود فایل
        downloaded_file = await bot.download_file(file_info.file_path)
        
        # ذخیره فایل موقت
        editor = MusicEditor()
        original_path = os.path.join(editor.temp_dir, file_name)
        
        with open(original_path, 'wb') as f:
            f.write(downloaded_file)
        
        # استخراج تگ‌ها و کاور
        tags, cover_data = editor.extract_tags_and_cover(original_path)
        
        # ایجاد تصویر نمایش تگ‌ها
        tags_image_path = editor.create_tag_image(tags, cover_data)
        
        if tags_image_path:
            with open(tags_image_path, 'rb') as photo:
                await bot.send_photo(
                    message.chat.id, 
                    photo, 
                    caption="🏷️ تگ‌های فعلی موزیک:\n\nلطفاً کاور جدید و تگ‌های مورد نظر خود را ارسال کنید."
                )
        
        # ذخیره اطلاعات جلسه کاربر
        user_sessions[user_id] = {
            'original_path': original_path,
            'original_tags': tags,
            'editor': editor,
            'step': 'waiting_for_new_content'
        }
        
    except Exception as e:
        await bot.reply_to(message, f"❌ خطا در پردازش فایل: {str(e)}")

@bot.message_handler(content_types=['photo'])
async def handle_cover(message):
    try:
        user_id = message.from_user.id
        
        if user_id not in user_sessions or user_sessions[user_id]['step'] != 'waiting_for_new_content':
            await bot.reply_to(message, "❌ ابتدا یک فایل موزیک ارسال کنید.")
            return
        
        # دانلود کاور جدید
        file_info = await bot.get_file(message.photo[-1].file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        
        cover_path = os.path.join(user_sessions[user_id]['editor'].temp_dir, "new_cover.jpg")
        with open(cover_path, 'wb') as f:
            f.write(downloaded_file)
        
        user_sessions[user_id]['new_cover'] = cover_path
        user_sessions[user_id]['step'] = 'waiting_for_tags'
        
        await bot.reply_to(message, "✅ کاور دریافت شد! حالا لطفاً تگ‌های جدید را به صورت متن ارسال کنید.\n\nمثال:\nTitle: نام آهنگ\nArtist: نام هنرمند\nAlbum: نام آلبوم")
        
    except Exception as e:
        await bot.reply_to(message, f"❌ خطا در دریافت کاور: {str(e)}")

@bot.message_handler(content_types=['text'])
async def handle_tags(message):
    try:
        user_id = message.from_user.id
        
        if user_id not in user_sessions or user_sessions[user_id]['step'] != 'waiting_for_tags':
            return
        
        # پارس کردن تگ‌های جدید
        new_tags = {}
        lines = message.text.split('\n')
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                new_tags[key.strip()] = value.strip()
        
        if not new_tags:
            await bot.reply_to(message, "❌ فرمت تگ‌ها صحیح نیست. لطفاً مثل این ارسال کنید:\nTitle: نام آهنگ\nArtist: نام هنرمند")
            return
        
        session = user_sessions[user_id]
        editor = session['editor']
        
        await bot.send_message(message.chat.id, "🔄 در حال پردازش... لطفاً صبر کنید.")
        
        # شروع پردازش
        original_path = session['original_path']
        
        # حذف سکوت
        trimmed_path = editor.remove_silence(original_path)
        
        # اضافه کردن امضا
        # with_signature_path = editor.add_signature(trimmed_path)
        
        # اعمال تگ‌ها و کاور جدید
        final_path = os.path.join(editor.temp_dir, "final_music.mp3")
        os.rename(trimmed_path, final_path)
        
        editor.apply_tags_and_cover(
            final_path, 
            new_tags, 
            session.get('new_cover')
        )
        
        # ایجاد نسخه‌های مختلف بیت‌ریت
        path_320, path_64 = editor.create_bitrate_versions(final_path)
        
        # ایجاد پیش‌نمایش صوتی
        voice_preview_path = editor.create_voice_preview(path_64)
        
        # ایجاد تصویر تگ‌های جدید
        final_tags, final_cover = editor.extract_tags_and_cover(final_path)
        tags_image_path = editor.create_tag_image(final_tags, final_cover)
        
        # ارسال نتایج
        if tags_image_path:
            with open(tags_image_path, 'rb') as photo:
                await bot.send_photo(
                    message.chat.id, 
                    photo, 
                    caption="🎵 تگ‌های جدید اعمال شد!"
                )
        
        # ارسال پیش‌نمایش صوتی
        if voice_preview_path:
            with open(voice_preview_path, 'rb') as voice:
                await bot.send_voice(
                    message.chat.id, 
                    voice, 
                    caption="🎧 پیش‌نمایش صوتی (ثانیه 30-60)"
                )
        
        # ارسال فایل نهایی
        if path_320:
            with open(path_320, 'rb') as audio:
                await bot.send_audio(
                    message.chat.id, 
                    audio, 
                    caption="🎵 موزیک ویرایش شده (320 kbps)"
                )
        
        # پاک کردن جلسه کاربر
        del user_sessions[user_id]
        
        await bot.send_message(message.chat.id, "✅ پردازش با موفقیت تکمیل شد!")
        
    except Exception as e:
        await bot.reply_to(message, f"❌ خطا در پردازش: {str(e)}")

# اجرای ربات
if __name__ == "__main__":
    print("🤖 ربات در حال اجرا...")
    asyncio.run(bot.polling())
