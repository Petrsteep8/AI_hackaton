from dotenv import load_dotenv
from telebot import TeleBot, types
import os
import random
import sqlite3
import requests

from tg_bot.data import *

load_dotenv()
token = os.getenv('TOKEN')
bot = TeleBot(token)
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')


class YandexGPTAssistant:
    def __init__(self):
        self.url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {YANDEX_API_KEY}"
        }
    
    def generate_response(self, user_message, mbti_type):
        prompt = {
            "modelUri": "gpt://b1gspidht685rdgfcrjf/yandexgpt-lite",
            "completionOptions": {
                "stream": False,
                "temperature": 0.6,
                "maxTokens": 2000
            },
            "messages": [
                {
                    "role": "system",
                    "text": f"""Ты психологический помощник с типом личности {mbti_type}.
                    Характеристика: {personality_types.get(mbti_type, '')}
                    Стиль общения: {mbti_greetings.get(mbti_type, '')}"""
                },
                {
                    "role": "user",
                    "text": user_message
                }
            ]
        }
        
        try:
            response = requests.post(self.url, headers=self.headers, json=prompt)
            response.raise_for_status()
            return response.json()['result']['alternatives'][0]['message']['text']
        except Exception as e:
            print(f"YandexGPT Error: {e}")
            return "Извините, произошла ошибка обработки запроса."

ai = YandexGPTAssistant()


def init_db():
    conn = sqlite3.connect("personality_test.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            mbti_answers TEXT,
            archetype_answer TEXT,
            current_question INTEGER DEFAULT 0,
            test_completed BOOLEAN DEFAULT FALSE
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@bot.message_handler(commands=['start'])
def start_test(message):
    user_id = message.chat.id
    chat = message.chat
    chat_id = chat.id
    name = message.chat.first_name
    random.shuffle(URL_arr)
    random_picture = random.choice(URL_arr)
    bot.send_photo(chat_id, random_picture)
    bot.send_message(
        chat_id=chat_id,
        text=f'Привет, {name}, я Example_bot!\nПройдите опрос, чтобы я мог составить тебе полноценного AI-персонажа.'
    )
    conn = sqlite3.connect("personality_test.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, mbti_answers, archetype_answer, current_question) VALUES (?, ?, ?, ?)", 
                   (user_id, "", "", 0))
    conn.commit()
    conn.close()
    ask_question(user_id, 0)


def ask_question(user_id, question_index):
    try:
        if question_index < len(mbti_questions):
            question = mbti_questions[question_index]
        else:
            question = archetype_question[0]
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for option in question["options"]:
            markup.add(types.KeyboardButton(option))
        bot.send_message(user_id, question["text"], reply_markup=markup)
    
    except Exception as e:
        print(f"Ошибка в ask_question: {e}")
        bot.send_message(user_id, "Произошла ошибка. Пожалуйста, попробуйте снова (/start).")


@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    user_id = message.chat.id
    conn = sqlite3.connect("personality_test.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT mbti_answers, current_question, test_completed FROM users WHERE user_id=?", (user_id,))
        data = cursor.fetchone()
        if not data:
            bot.send_message(user_id, "Пожалуйста, начните тест (/start)")
            return
        mbti_answers, current_question, test_completed = data
        if not test_completed and current_question <= len(mbti_questions):
            handle_answer(message, conn)
        else:
            handle_ai_message(message, conn)
            
    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(user_id, "Произошла ошибка обработки сообщения")
        
    finally:
        conn.close()


def handle_answer(message, conn):
    user_id = message.chat.id
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT mbti_answers, archetype_answer, current_question FROM users WHERE user_id = ?", (user_id,))
        data = cursor.fetchone()
        if not data:
            bot.send_message(user_id, "Пожалуйста, начните тест снова (/start).")
            return
        mbti_answers, archetype_answer, current_question = data

        if current_question < len(mbti_questions):
            question = mbti_questions[current_question]
            if message.text not in question["options"]:
                bot.send_message(user_id, "Пожалуйста, выберите один из предложенных вариантов.")
                return
            answer_letter = message.text.split(",")[1].strip()[0]
            new_mbti_answers = mbti_answers + answer_letter
            new_question = current_question + 1
            cursor.execute("UPDATE users SET mbti_answers = ?, current_question = ? WHERE user_id = ?", 
                         (new_mbti_answers, new_question, user_id))
            conn.commit()
            ask_question(user_id, new_question)
        
        else:
            if not any(message.text.startswith(letter) for letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]):
                return
            archetype_key = message.text[0]
            archetype_desc = answers_archetype.get(archetype_key, "Архетип не определён.")
            image_path = f"archetypes_pictures/{archetype_key}.jpg"
            cursor.execute("UPDATE users SET archetype_answer = ? WHERE user_id = ?", 
                         (archetype_key, user_id))
            conn.commit()
            result_message = ""
            if len(mbti_answers) == 4:
                mbti_type = personality_types.get(mbti_answers, "Тип не определён")
                result_message += f"Ваш тип личности: {mbti_answers}\n{mbti_type}\n\n"
            result_message += f"Ваш архетип: {archetype_desc}"

            try:
                with open(image_path, 'rb') as photo:
                    bot.send_photo(user_id, photo)
            except FileNotFoundError:
                print(f"Изображение для архетипа {archetype_key} не найдено")
                bot.send_message(user_id, "Изображение вашего архетипа временно недоступно")

            bot.send_message(user_id, result_message, reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(user_id, mbti_greetings[mbti_answers])
            cursor.execute(
                "UPDATE users SET test_completed = TRUE WHERE user_id = ?",
                (message.chat.id,)
            )
            conn.commit()
    
    except Exception as e:
        print(f"Ошибка в handle_answer: {e}")
        bot.send_message(user_id, "Произошла ошибка обработки вашего ответа.")
    
    finally:
        conn.close()


def handle_ai_message(message, conn):
    user_id = message.chat.id
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT mbti_answers FROM users WHERE user_id=?", (user_id,))
        result = cursor.fetchone()
        if not result:
            bot.send_message(user_id, "Пожалуйста, завершите тест (/start)")
            return
        mbti_type = result[0]
        bot.send_chat_action(user_id, 'typing')
        response = ai.generate_response(message.text, mbti_type)
        bot.send_message(user_id, response)
        
    except Exception as e:
        print(f"AI Error: {e}")
        bot.send_message(user_id, "Ошибка генерации ответа. Попробуйте позже.")

if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
