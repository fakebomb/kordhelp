import os
import sqlite3
import shutil
import re
import json
from datetime import datetime, timedelta
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.carousel import Carousel
from kivy.utils import platform
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock

try:
    from pysqlcipher3 import dbapi2 as sqlcipher
except ImportError:
    sqlcipher = None

# Додаємо Android API для відкриття URL
if platform == 'android':
    from jnius import autoclass
    Intent = autoclass('android.content.Intent')
    Uri = autoclass('android.net.Uri')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')

# Ключ для шифрування
ENCRYPTION_KEY = "mysecretkey123"
DB_PASSWORD = "dbpass789"

# Функції для шифрування/дешифрування зображень
def encrypt_file(src_path, dest_path, key=ENCRYPTION_KEY):
    with open(src_path, 'rb') as f:
        data = f.read()
    key_bytes = key.encode('utf-8')
    encrypted_data = bytearray(data)
    for i in range(len(data)):
        encrypted_data[i] = data[i] ^ key_bytes[i % len(key_bytes)]
    with open(dest_path, 'wb') as f:
        f.write(encrypted_data)

def decrypt_file(src_path, key=ENCRYPTION_KEY):
    with open(src_path, 'rb') as f:
        data = f.read()
    key_bytes = key.encode('utf-8')
    decrypted_data = bytearray(data)
    for i in range(len(data)):
        decrypted_data[i] = data[i] ^ key_bytes[i % len(key_bytes)]
    return bytes(decrypted_data)

# Шлях до проєкту
class Paths:
    def __init__(self):
        self.app = App.get_running_app()
        self.BASE_PATH = self.app.user_data_dir if platform == 'android' else r"C:\Users\Ghost\Documents\MyCatalogApp"
        self.PRODUCTS_PATH = os.path.join(self.BASE_PATH, "Products")
        self.ICONS_PATH = os.path.join(self.BASE_PATH, "icons")
        self.IMAGES_PATH = os.path.join(self.BASE_PATH, "images")
        os.makedirs(self.BASE_PATH, exist_ok=True)
        os.makedirs(self.PRODUCTS_PATH, exist_ok=True)
        os.makedirs(self.ICONS_PATH, exist_ok=True)
        os.makedirs(self.IMAGES_PATH, exist_ok=True)

# Збереження та завантаження налаштувань теми
def save_theme(theme):
    paths = Paths()
    settings_path = os.path.join(paths.BASE_PATH, 'settings.json')
    settings = {'theme': theme}
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f)

def load_theme():
    paths = Paths()
    settings_path = os.path.join(paths.BASE_PATH, 'settings.json')
    if os.path.exists(settings_path):
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            return settings.get('theme', 'day')
    return 'day'

# Функція перетворення кольору для нічного режиму
def transform_color(day_color, theme, is_background=False):
    r, g, b, a = day_color
    if theme == 'night':
        if is_background:
            return (0.2, 0, 0, a)  # #330000 для фону
        brightness = (r + g + b) / 3
        if brightness > 0.5:
            return (1.0, 0.0, 0.0, a)
        else:
            return (0.0, 0.0, 0.0, a)
    return (r, g, b, a)

# Ініціалізація бази даних і сканування папок
def init_db():
    paths = Paths()
    db_path = os.path.join(paths.BASE_PATH, 'knowledge_base.db')
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Очистити папку images перед повторним скануванням, але залишити папку icons
    if os.path.exists(paths.IMAGES_PATH):
        shutil.rmtree(paths.IMAGES_PATH)
    os.makedirs(paths.IMAGES_PATH, exist_ok=True)
    
    if not os.path.exists(paths.ICONS_PATH):
        os.makedirs(paths.ICONS_PATH, exist_ok=True)
    
    if sqlcipher:
        conn = sqlcipher.connect(db_path)
        c = conn.cursor()
        c.execute(f"PRAGMA key='{DB_PASSWORD}'")
    else:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        short_desc TEXT,
        full_desc TEXT,
        image_path TEXT,
        links TEXT,
        category TEXT,
        subcategory TEXT,
        tags TEXT,
        pdf_paths TEXT,
        screenshot_paths TEXT
    )''')
    
    categories = ['FPV', 'Mavic', 'Вибухотехніку']
    
    for category in categories:
        category_path = os.path.join(paths.PRODUCTS_PATH, category)
        if not os.path.exists(category_path):
            print(f"Категорія {category} не знайдена")
            continue
        
        if category == 'Mavic':
            subcategory = 'Товари'
            for item_folder in os.listdir(category_path):
                item_path = os.path.join(category_path, item_folder)
                if not os.path.isdir(item_path):
                    continue
                process_item(item_path, category, subcategory, c)
        else:
            for subfolder in os.listdir(category_path):
                subfolder_path = os.path.join(category_path, subfolder)
                if not os.path.isdir(subfolder_path):
                    continue
                subcategory = subfolder
                for item_folder in os.listdir(subfolder_path):
                    item_path = os.path.join(subfolder_path, item_folder)
                    if not os.path.isdir(item_path):
                        continue
                    process_item(item_path, category, subcategory, c)
    
    conn.commit()
    conn.close()

def process_item(item_path, category, subcategory, cursor):
    paths = Paths()
    name = 'Без назви'
    description = 'Опис відсутній'
    links = ''
    image_path = ''
    pdf_paths = []
    screenshot_paths = []
    
    name_file = os.path.join(item_path, 'name.txt')
    try:
        if os.path.exists(name_file):
            with open(name_file, 'r', encoding='utf-8') as f:
                name = f.read().strip()
    except Exception as e:
        print(f"Помилка читання name.txt у {item_path}: {e}")
    
    desc_file = os.path.join(item_path, 'description.txt')
    try:
        if os.path.exists(desc_file):
            with open(desc_file, 'r', encoding='utf-8') as f:
                description = f.read().strip()
    except Exception as e:
        print(f"Помилка читання description.txt у {item_path}: {e}")
    
    links_file = os.path.join(item_path, 'links.txt')
    try:
        if os.path.exists(links_file):
            with open(links_file, 'r', encoding='utf-8') as f:
                links = f.read().strip()
                print(f"Вміст links.txt у {item_path}: {links}")
    except Exception as e:
        print(f"Помилка читання links.txt у {item_path}: {e}")
    
    for ext in ['.jpg', '.png']:
        img_file = os.path.join(item_path, f'image{ext}')
        if os.path.exists(img_file):
            try:
                unique_name = f"{category}_{subcategory}_{os.path.basename(item_path)}_main{ext}"
                dest_img = os.path.join(paths.IMAGES_PATH, unique_name)
                encrypt_file(img_file, dest_img)
                image_path = f'images/{unique_name}'
                print(f"Скопійовано та зашифровано зображення: {img_file} -> {dest_img}")
            except Exception as e:
                print(f"Помилка копіювання зображення {img_file}: {e}")
    
    for file in os.listdir(item_path):
        if file.endswith('.pdf'):
            pdf_paths.append(os.path.join(item_path, file))
    
    screenshots_dir = os.path.join(item_path, 'screenshots')
    if os.path.exists(screenshots_dir):
        for file in os.listdir(screenshots_dir):
            if file.lower().endswith(('.jpg', '.png')):
                try:
                    src_img = os.path.join(screenshots_dir, file)
                    unique_name = f"{category}_{subcategory}_{os.path.basename(item_path)}_screenshot_{file}"
                    dest_img = os.path.join(paths.IMAGES_PATH, unique_name)
                    encrypt_file(src_img, dest_img)
                    screenshot_paths.append(f'images/{unique_name}')
                    print(f"Скопійовано та зашифровано скріншот: {src_img} -> {dest_img}")
                except Exception as e:
                    print(f"Помилка копіювання скріншота {src_img}: {e}")
    
    short_desc = description[:20] + '...' if len(description) > 20 else description
    tags = ','.join([name.lower(), subcategory.lower()])
    
    try:
        cursor.execute('''INSERT OR IGNORE INTO items 
            (name, short_desc, full_desc, image_path, links, category, subcategory, tags, pdf_paths, screenshot_paths) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, short_desc, description, image_path, links, category, subcategory, tags, ';'.join(pdf_paths), ';'.join(screenshot_paths)))
        print(f"Додано товар: {name} (Категорія: {category}, Підкатегорія: {subcategory})")
    except Exception as e:
        print(f"Помилка збереження в базу для {item_path}: {e}")

# Екран авторизації
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'login'
        self.attempts = 3
        self.lockout_time = None
        self.load_attempts()
        print("Ініціалізація LoginScreen")
    
    def load_attempts(self):
        paths = Paths()
        attempts_file = os.path.join(paths.BASE_PATH, 'login_attempts.json')
        if os.path.exists(attempts_file):
            with open(attempts_file, 'r') as f:
                data = json.load(f)
                self.attempts = data.get('attempts', 3)
                lockout_str = data.get('lockout_time', None)
                if lockout_str:
                    self.lockout_time = datetime.fromisoformat(lockout_str)
    
    def save_attempts(self):
        paths = Paths()
        attempts_file = os.path.join(paths.BASE_PATH, 'login_attempts.json')
        data = {
            'attempts': self.attempts,
            'lockout_time': self.lockout_time.isoformat() if self.lockout_time else None
        }
        with open(attempts_file, 'w') as f:
            json.dump(data, f)
    
    def check_password(self, password):
        current_time = datetime.now()
        
        if self.lockout_time:
            if current_time < self.lockout_time:
                remaining = (self.lockout_time - current_time).seconds // 60
                self.ids.message_label.text = f"Заблоковано! Спробуйте через {remaining} хв."
                return
            else:
                self.attempts = 3
                self.lockout_time = None
        
        if self.attempts <= 0:
            self.lockout_time = current_time + timedelta(hours=1)
            self.save_attempts()
            self.ids.message_label.text = "Спроби закінчилися! Заблоковано на 1 годину."
            return
        
        if password == 'wertop785':
            self.manager.current = 'main'
            self.attempts = 3
            self.lockout_time = None
            self.save_attempts()
        else:
            self.attempts -= 1
            self.save_attempts()
            if self.attempts > 0:
                self.ids.message_label.text = f"В доступі відмовлено! Залишилося спроб: {self.attempts}"
            else:
                self.lockout_time = current_time + timedelta(hours=1)
                self.save_attempts()
                self.ids.message_label.text = "Спроби закінчилися! Заблоковано на 1 годину."

# Базовий клас для екранів із підтримкою теми
class ThemeScreen(Screen):
    day_background = None

    def update_theme(self):
        app = App.get_running_app()
        theme = app.theme
        if self.day_background and self.canvas.before.children:
            for instruction in self.canvas.before.children:
                if hasattr(instruction, 'rgba'):
                    instruction.rgba = transform_color(self.day_background, theme, is_background=True)
                    break

# Головний екран із категоріями
class MainScreen(ThemeScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'main'
        self.day_background = (0.1, 0.1, 0.1, 1)
        print("Ініціалізація MainScreen")
    
    def go_to_subcategories(self, category):
        try:
            print(f"Перехід до підкатегорій для {category}")
            subcategories_screen = self.manager.get_screen('subcategories')
            subcategories_screen.category = category
            self.manager.current = 'subcategories'
        except Exception as e:
            print(f"Помилка переходу до підкатегорій: {e}")
    
    def update_theme(self):
        app = App.get_running_app()
        theme = app.theme
        super().update_theme()
        
        container = self.ids.categories_container
        day_btn_bg = (0.2, 0.4, 0.8, 1)
        day_text = (1, 1, 1, 1)
        for btn in container.children:
            if isinstance(btn, Button):
                btn.background_color = transform_color(day_btn_bg, theme)
                btn.color = transform_color(day_text, theme)
            elif isinstance(btn, Label):
                btn.color = transform_color(day_text, theme)
        if hasattr(self.ids, 'theme_btn'):
            self.ids.theme_btn.source = 'icons/night_mode.png' if theme == 'day' else 'icons/day_mode.png'
        if hasattr(self.ids, 'exit_btn'):
            self.ids.exit_btn.source = 'icons/day_exit.png' if theme == 'day' else 'icons/night_exit.png'
        if hasattr(self.ids, 'title_label'):
            self.ids.title_label.text = 'Категорії' if theme == 'day' else 'Категорії (Нічний режим)'
            self.ids.title_label.color = transform_color(day_text, theme)

# Екран підкатегорій
class SubcategoriesScreen(ThemeScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'subcategories'
        self.category = ''
        self.day_background = (0.15, 0.15, 0.15, 1)
        print("Ініціалізація SubcategoriesScreen")
    
    def on_enter(self):
        print(f"Завантаження підкатегорій для {self.category}")
        try:
            container = self.ids.subcategories_container
            container.clear_widgets()
        except AttributeError as e:
            print(f"Помилка доступу до subcategories_container: {e}")
            return
        
        paths = Paths()
        if sqlcipher:
            conn = sqlcipher.connect(os.path.join(paths.BASE_PATH, 'knowledge_base.db'))
            c = conn.cursor()
            c.execute(f"PRAGMA key='{DB_PASSWORD}'")
        else:
            conn = sqlite3.connect(os.path.join(paths.BASE_PATH, 'knowledge_base.db'))
            c = conn.cursor()
        c.execute("SELECT DISTINCT subcategory FROM items WHERE category = ?", (self.category,))
        subcategories = [row[0] for row in c.fetchall()]
        conn.close()
        
        if not subcategories:
            print(f"Підкатегорії для {self.category} відсутні")
            container.add_widget(Label(text='Підкатегорії відсутні', size_hint_y=None, height=50))
        else:
            print(f"Знайдено підкатегорії: {subcategories}")
            for subcategory in subcategories:
                btn = Button(text=subcategory, size_hint_y=None, height=50)
                btn.bind(on_press=lambda x, s=subcategory: self.go_to_items(s))
                container.add_widget(btn)
        self.update_theme()
    
    def go_to_items(self, subcategory):
        try:
            print(f"Перехід до товарів для {self.category}/{subcategory}")
            items_screen = self.manager.get_screen('items')
            items_screen.category = self.category
            items_screen.subcategory = subcategory
            self.manager.current = 'items'
        except Exception as e:
            print(f"Помилка переходу до товарів: {e}")
    
    def go_back(self):
        try:
            self.manager.current = 'main'
        except Exception as e:
            print(f"Помилка повернення на головний екран: {e}")
    
    def update_theme(self):
        app = App.get_running_app()
        theme = app.theme
        super().update_theme()
        
        container = self.ids.subcategories_container
        day_btn_bg = (0.2, 0.4, 0.8, 1)
        day_text = (1, 1, 1, 1)
        for child in container.children:
            if isinstance(child, Button):
                child.background_color = transform_color(day_btn_bg, theme)
                child.color = transform_color(day_text, theme)
            elif isinstance(child, Label):
                child.color = transform_color(day_text, theme)
        if hasattr(self.ids, 'back_btn'):
            self.ids.back_btn.background_color = transform_color(day_btn_bg, theme)
            self.ids.back_btn.color = transform_color(day_text, theme)

# Екран списку товарів
class ItemsScreen(ThemeScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'items'
        self.category = ''
        self.subcategory = ''
        self.day_background = (0.15, 0.15, 0.15, 1)
        print("Ініціалізація ItemsScreen")
    
    def on_enter(self):
        print(f"Завантаження товарів для {self.category}/{self.subcategory}")
        self.update_items()
        self.update_theme()
    
    def update_items(self, search_text=''):
        try:
            container = self.ids.items_container
            container.clear_widgets()
        except AttributeError as e:
            print(f"Помилка доступу до items_container: {e}")
            return
        
        paths = Paths()
        if sqlcipher:
            conn = sqlcipher.connect(os.path.join(paths.BASE_PATH, 'knowledge_base.db'))
            c = conn.cursor()
            c.execute(f"PRAGMA key='{DB_PASSWORD}'")
        else:
            conn = sqlite3.connect(os.path.join(paths.BASE_PATH, 'knowledge_base.db'))
            c = conn.cursor()
        query = "SELECT id, name, short_desc FROM items WHERE category = ? AND subcategory = ?"
        params = [self.category, self.subcategory]
        
        if search_text:
            query += " AND (name LIKE ? OR tags LIKE ?)"
            params.extend([f'%{search_text}%', f'%{search_text}%'])
        
        c.execute(query, params)
        items = c.fetchall()
        conn.close()
        
        if not items:
            print(f"Товари для {self.category}/{self.subcategory} відсутні")
            container.add_widget(Label(text='Товари відсутні', size_hint_y=None, height=50))
        else:
            print(f"Знайдено товари: {[item[1] for item in items]}")
            for item in items:
                item_id, name, short_desc = item
                btn = Button(text=f'{name}\n{short_desc}', size_hint_y=None, height=80)
                btn.bind(on_press=lambda x, i=item_id: self.go_to_item(i))
                container.add_widget(btn)
    
    def on_search(self, instance, value):
        self.update_items(value)
    
    def go_to_item(self, item_id):
        try:
            print(f"Перехід до картки товару {item_id}")
            item_screen = self.manager.get_screen('item')
            item_screen.item_id = item_id
            self.manager.current = 'item'
        except Exception as e:
            print(f"Помилка переходу до картки товару: {e}")
    
    def go_back(self):
        try:
            self.manager.current = 'subcategories'
        except Exception as e:
            print(f"Помилка повернення на екран підкатегорій: {e}")
    
    def update_theme(self):
        app = App.get_running_app()
        theme = app.theme
        super().update_theme()
        
        container = self.ids.items_container
        day_btn_bg = (0.2, 0.4, 0.8, 1)
        day_text = (1, 1, 1, 1)
        day_input_bg = (0.2, 0.2, 0.2, 1)
        day_input_fg = (1, 1, 1, 1)
        for child in container.children:
            if isinstance(child, Button):
                child.background_color = transform_color(day_btn_bg, theme)
                child.color = transform_color(day_text, theme)
            elif isinstance(child, Label):
                child.color = transform_color(day_text, theme)
        if hasattr(self.ids, 'search_input'):
            self.ids.search_input.background_color = transform_color(day_input_bg, theme)
            self.ids.search_input.foreground_color = transform_color(day_input_fg, theme)
        if hasattr(self.ids, 'back_btn'):
            self.ids.back_btn.background_color = transform_color(day_btn_bg, theme)
            self.ids.back_btn.color = transform_color(day_text, theme)

# Екран картки товару
class ItemScreen(ThemeScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'item'
        self.item_id = None
        self.copy_label = None
        self.day_background = (0.15, 0.15, 0.15, 1)
        print("Ініціалізація ItemScreen")
    
    def on_enter(self):
        print(f"Завантаження картки товару {self.item_id}")
        try:
            carousel = self.ids.carousel
            pdf_container = self.ids.pdf_container
            links_container = self.ids.links_container
            carousel.clear_widgets()
            pdf_container.clear_widgets()
            links_container.clear_widgets()
        except AttributeError as e:
            print(f"Помилка доступу до carousel, pdf_container або links_container: {e}")
            return
        
        paths = Paths()
        if sqlcipher:
            conn = sqlcipher.connect(os.path.join(paths.BASE_PATH, 'knowledge_base.db'))
            c = conn.cursor()
            c.execute(f"PRAGMA key='{DB_PASSWORD}'")
        else:
            conn = sqlite3.connect(os.path.join(paths.BASE_PATH, 'knowledge_base.db'))
            c = conn.cursor()
        c.execute("SELECT name, short_desc, full_desc, image_path, links, tags, pdf_paths, screenshot_paths FROM items WHERE id = ?", (self.item_id,))
        item = c.fetchone()
        conn.close()
        
        if item:
            name, short_desc, full_desc, image_path, links, tags, pdf_paths, screenshot_paths = item
            try:
                self.ids.name_label.text = name
                self.ids.short_desc_label.text = short_desc
                self.ids.full_desc_label.text = full_desc
            except AttributeError as e:
                print(f"Помилка доступу до текстових міток: {e}")
                return
            
            if image_path and os.path.exists(image_path):
                print(f"Додано основне зображення: {image_path}")
                temp_path = image_path + '.temp'
                with open(temp_path, 'wb') as f:
                    f.write(decrypt_file(image_path))
                carousel.add_widget(Image(source=temp_path))
                os.remove(temp_path)
            else:
                placeholder_path = os.path.join(paths.IMAGES_PATH, 'placeholder.png')
                if os.path.exists(placeholder_path):
                    print("Додано placeholder.png")
                    temp_path = placeholder_path + '.temp'
                    with open(temp_path, 'wb') as f:
                        f.write(decrypt_file(placeholder_path))
                    carousel.add_widget(Image(source=temp_path))
                    os.remove(temp_path)
                else:
                    print("placeholder.png не знайдено")
            
            if screenshot_paths:
                for screenshot in screenshot_paths.split(';'):
                    if os.path.exists(screenshot):
                        print(f"Додано скріншот: {screenshot}")
                        temp_path = screenshot + '.temp'
                        with open(temp_path, 'wb') as f:
                            f.write(decrypt_file(screenshot))
                        carousel.add_widget(Image(source=temp_path))
                        os.remove(temp_path)
                    else:
                        print(f"Скріншот не знайдено: {screenshot}")
            else:
                print("Скріншоти відсутні")
            
            if pdf_paths:
                for pdf in pdf_paths.split(';'):
                    if os.path.exists(pdf):
                        print(f"Додано PDF: {pdf}")
                        btn = Button(text=os.path.basename(pdf), size_hint_y=None, height=40)
                        btn.bind(on_press=lambda x, p=pdf: self.open_pdf(p))
                        pdf_container.add_widget(btn)
            
            if screenshot_paths:
                screenshot_btn = Button(
                    text='Переглянути скріншоти',
                    size_hint_y=None,
                    height=40,
                    background_normal='',
                    background_color=(0, 0, 0, 0)
                )
                screenshot_btn.bind(on_press=lambda x: self.go_to_screenshots(screenshot_paths.split(';')))
                pdf_container.add_widget(screenshot_btn)
            else:
                print("Скріншоти відсутні для кнопки")
            
            if links:
                link_items = links.split('\n')
                for link in link_items:
                    link = link.strip()
                    if not link:
                        continue
                    
                    link_type, display_text = self.detect_link_type(link)
                    print(f"Розпізнано посилання: {link} як {link_type} ({display_text})")
                    btn_text = f'{display_text}: {link}' if link_type != 'other' else link
                    print(f"Текст кнопки: {btn_text}")
                    
                    if link_type in ['email', 'phone', 'other']:
                        btn = Button(
                            text=btn_text,
                            size_hint_y=None,
                            height=30,
                            color=(1, 1, 1, 1),
                            background_normal='',
                            background_color=(0, 0, 0, 0)
                        )
                        btn.bind(on_press=lambda x, t=link: self.copy_to_clipboard(t))
                        links_container.add_widget(btn)
                    else:
                        btn = Button(
                            text=btn_text,
                            font_size=14,
                            color=(1, 1, 1, 1),
                            size_hint_y=None,
                            height=30,
                            background_normal='',
                            background_color=(0, 0, 0, 0)
                        )
                        btn.bind(on_press=lambda x, url=link: self.open_url(url))
                        links_container.add_widget(btn)
            else:
                print("Посилання відсутні")
        self.update_theme()
    
    def go_to_screenshots(self, screenshot_paths):
        try:
            print(f"Перехід до скріншотів: {screenshot_paths}")
            screenshots_screen = self.manager.get_screen('screenshots')
            screenshots_screen.screenshot_paths = screenshot_paths
            self.manager.current = 'screenshots'
        except Exception as e:
            print(f"Помилка переходу до скріншотів: {e}")
    
    def detect_link_type(self, link):
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        phone_pattern = r'\+?\d{1,4}[\s-]?\d{1,4}[\s-]?\d{1,4}[\s-]?\d{1,4}'
        google_form_pattern = r'forms\.gle|docs\.google\.com/forms'
        url_pattern = r'https?://[^\s]+'
        
        if re.search(email_pattern, link):
            return 'email', 'Email'
        elif re.search(phone_pattern, link):
            return 'phone', 'Телефон'
        elif re.search(google_form_pattern, link):
            return 'google_form', 'Форма заповнення'
        elif re.search(url_pattern, link):
            domain = re.search(r'https?://(?:www\.)?([^\s/]+)', link)
            if domain:
                site_name = domain.group(1).split('.')[0].capitalize()
                return 'website', site_name
            return 'website', 'Вебсайт'
        else:
            return 'other', 'Інше'
    
    def copy_to_clipboard(self, text):
        Clipboard.copy(text)
        print(f"Скопійовано: {text}")
        
        if self.copy_label:
            self.copy_label.text = ''
        self.copy_label = Label(
            text='Скопійовано',
            font_size=14,
            color=(0.8, 0.8, 0.8, 1),
            size_hint_y=None,
            height=30,
            text_size=(self.width - 20, None)
        )
        self.ids.links_container.add_widget(self.copy_label)
        
        Clock.schedule_once(self.clear_copy_label, 1.5)
    
    def clear_copy_label(self, dt):
        if self.copy_label:
            self.ids.links_container.remove_widget(self.copy_label)
            self.copy_label = None
    
    def open_url(self, url):
        try:
            if platform == 'android':
                intent = Intent(Intent.ACTION_VIEW)
                intent.setData(Uri.parse(url))
                intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                PythonActivity.mActivity.startActivity(intent)
                print(f"Відкрито URL на Android: {url}")
            else:
                print(f"Відкриття URL не підтримується на цій платформі: {url}")
        except Exception as e:
            print(f"Помилка відкриття URL {url}: {e}")

    def open_pdf(self, pdf_path):
        if platform == 'android':
            try:
                from jnius import autoclass
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                File = autoclass('java.io.File')
                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(Uri.fromFile(File(pdf_path)), 'application/pdf')
                intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                autoclass('org.kivy.android.PythonActivity').mActivity.startActivity(intent)
            except Exception as e:
                print(f"Помилка відкриття PDF: {e}")
        else:
            print(f"Відкриття PDF не підтримується на цій платформі: {pdf_path}")
    
    def go_back(self):
        try:
            self.manager.current = 'items'
        except Exception as e:
            print(f"Помилка повернення на екран товарів: {e}")
    
    def update_theme(self):
        app = App.get_running_app()
        theme = app.theme
        super().update_theme()
        
        day_text = (1, 1, 1, 1)
        day_label_color = (0.8, 0.8, 0.8, 1)
        day_btn_bg = (0.2, 0.4, 0.8, 1)
        if hasattr(self.ids, 'name_label'):
            self.ids.name_label.color = transform_color(day_text, theme)
        if hasattr(self.ids, 'short_desc_label'):
            self.ids.short_desc_label.color = transform_color(day_label_color, theme)
        if hasattr(self.ids, 'full_desc_label'):
            self.ids.full_desc_label.color = transform_color(day_text, theme)
        
        for container in [self.ids.links_container, self.ids.pdf_container]:
            for child in container.children:
                if isinstance(child, Button):
                    if container == self.ids.links_container:
                        child.background_color = transform_color(day_btn_bg, theme)
                    else:
                        child.background_color = transform_color(day_btn_bg, theme)
                    child.color = transform_color(day_text, theme)
                elif isinstance(child, Label):
                    child.color = transform_color(day_label_color, theme)
        
        if hasattr(self.ids, 'back_btn'):
            self.ids.back_btn.background_color = transform_color(day_btn_bg, theme)
            self.ids.back_btn.color = transform_color(day_text, theme)

# Екран перегляду скріншотів
class ScreenshotsScreen(ThemeScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'screenshots'
        self.screenshot_paths = []
        self.is_zoomed = False
        self.day_background = (0.15, 0.15, 0.15, 1)
        print("Ініціалізація ScreenshotsScreen")
    
    def on_enter(self):
        print(f"Завантаження скріншотів: {self.screenshot_paths}")
        try:
            carousel = self.ids.screenshots_carousel
            carousel.clear_widgets()
            for path in self.screenshot_paths:
                if os.path.exists(path):
                    temp_path = path + '.temp'
                    with open(temp_path, 'wb') as f:
                        f.write(decrypt_file(path))
                    img = Image(source=temp_path)
                    img.bind(on_touch_down=self.on_image_touch)
                    carousel.add_widget(img)
                    os.remove(temp_path)
                else:
                    print(f"Зображення {path} не знайдено")
        except AttributeError as e:
            print(f"Помилка доступу до screenshots_carousel: {e}")
        self.update_theme()
    
    def on_image_touch(self, instance, touch):
        if instance.collide_point(*touch.pos) and touch.button == 'left':
            self.is_zoomed = not self.is_zoomed
            carousel = self.ids.screenshots_carousel
            if self.is_zoomed:
                carousel.size_hint_y = 0.8
            else:
                carousel.size_hint_y = 0.4
            carousel.height = self.height * carousel.size_hint_y
    
    def go_back(self):
        try:
            self.manager.current = 'item'
        except Exception as e:
            print(f"Помилка повернення на екран товару: {e}")
    
    def update_theme(self):
        app = App.get_running_app()
        theme = app.theme
        super().update_theme()
        
        day_btn_bg = (0.2, 0.4, 0.8, 1)
        day_text = (1, 1, 1, 1)
        if hasattr(self.ids, 'back_btn'):
            self.ids.back_btn.background_color = transform_color(day_btn_bg, theme)
            self.ids.back_btn.color = transform_color(day_text, theme)

# Головний застосунок
class KnowledgeBaseApp(App):
    def build(self):
        print("Ініціалізація ScreenManager")
        self.theme = load_theme()
        self.sm = ScreenManager()
        
        login_screen = LoginScreen()
        main_screen = MainScreen()
        subcategories_screen = SubcategoriesScreen()
        items_screen = ItemsScreen()
        item_screen = ItemScreen()
        screenshots_screen = ScreenshotsScreen()
        
        self.sm.add_widget(login_screen)
        self.sm.add_widget(main_screen)
        self.sm.add_widget(subcategories_screen)
        self.sm.add_widget(items_screen)
        self.sm.add_widget(item_screen)
        self.sm.add_widget(screenshots_screen)
        
        print(f"Додано екрани: {self.sm.screen_names}")
        
        init_db()
        
        for screen in self.sm.screens:
            if screen.name != 'login':
                screen.update_theme()
        
        return self.sm
    
    def toggle_theme(self):
        self.theme = 'night' if self.theme == 'day' else 'day'
        save_theme(self.theme)
        print(f"Переключено тему на: {self.theme}")
        for screen in self.sm.screens:
            if screen.name != 'login':
                screen.update_theme()

if __name__ == '__main__':
    try:
        KnowledgeBaseApp().run()
    except Exception as e:
        print(f"Помилка запуску застосунку: {e}")
