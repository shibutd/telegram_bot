import os
import time
import requests
import telebot
from sqlalchemy import MetaData, Column, String, Integer, Float, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from collections import defaultdict


# telebot.apihelper.proxy = {'https':'socks5://127.0.0.1:9150'}
token = os.getenv('TOKEN')
bot = telebot.TeleBot(token)

url = 'https://maps.googleapis.com/maps/api/distancematrix/json'
API_KEY = os.getenv('API_KEY')

engine = create_engine(os.getenv('DATABASE_URL'))

Base = declarative_base()
class Places(Base):
    __tablename__ = 'places'
    id = Column(Integer, primary_key=True)
    user = Column(Integer)
    address = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    image = Column(String)

    def __init__(self, user=None, address=None, latitude=None, longitude=None, image=None):
        self.user = user
        self.address = address
        self.latitude = latitude
        self.longitude = longitude
        self.image = image

    def __repr__(self):
        return f'<Places({self.user}, {self.address})>'


Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()


START, ADDRESS, LOCATION, IMAGE, CONFIRMATION = range(5)
USER_STATE = defaultdict(lambda: START)
PLACES = defaultdict(lambda: {})


def find_closest_places(location, places):
    origins = [f'{location.latitude},{location.longitude}']
    origins = '|'.join(origins)
    destinations = [f'{place.latitude},{place.longitude}' for place in places]
    destinations = '|'.join(destinations)
    parameters = {'origins': origins, 'destinations': destinations, 'key': API_KEY}
    distances = requests.get(url, params=parameters).json()
    closest = []
    for num, d in enumerate(distances['rows'][0]['elements']):
        if d['status'] == 'OK':
            if d['distance']['value'] < 500:
                closest.append(num)
    return closest


def get_state(message):
    return USER_STATE[message.chat.id]


def update_state(message, state):
    USER_STATE[message.chat.id] = state


def get_place(message):
    return PLACES[message.chat.id]


def update_place(message, key, value):
    PLACES[message.chat.id][key] = value


def reset_place(message):
    PLACES[message.chat.id] = {}


def create_keyboard(buttons_list=[]):
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=len(buttons_list))
    buttons = [telebot.types.InlineKeyboardButton(text=button, callback_data=button) \
                for button in buttons_list]
    keyboard.add(*buttons)
    return keyboard


@bot.callback_query_handler(func=lambda x: True)
def callback_handler(callback_query):
    message = callback_query.message
    text = callback_query.data
    if text == 'Отмена':
        bot.edit_message_reply_markup(chat_id=message.chat.id, \
                                    message_id=message.message_id, reply_markup=None)
        bot.send_message(message.chat.id, text='Добавление нового места отменено.')
        reset_place(message)
        update_state(message, START)
    elif text == 'Пропустить':
        bot.edit_message_reply_markup(chat_id=message.chat.id, \
                                    message_id=message.message_id, reply_markup=None)
        bot.send_message(message.chat.id, text='Хорошо, давай без фото.')
        update_state(message, CONFIRMATION)
        time.sleep(1)
        confirmation(message)
    elif text == 'Да':
        bot.edit_message_reply_markup(chat_id=message.chat.id, \
                                    message_id=message.message_id, reply_markup=None)
        places = session.query(Places).filter_by(user=message.chat.id).order_by(Places.id).all()
        if len(places) == 10:
            session.delete(places[0])
        place_dict = get_place(message)
        place = Places(user=message.chat.id, address=place_dict.get('address'), latitude=place_dict.get('latitude'), \
                        longitude=place_dict.get('longitude'), image=place_dict.get('image'))
        session.add(place)
        session.commit()
        bot.send_message(message.chat.id, text="Новое место добалено!")
        reset_place(message)
        update_state(message, START)


@bot.message_handler(commands=['start', 'help'])
def command_help(message):
    text = ''' Привет! Я создан для того, чтобы запоминать места, которые ты возможно захочешь посетить позже. Доступные команды:
/add – запомнить место;
/list – показать сохраненные места (только последние 10);
/reset – удалить все сохраненные места.
            '''
    bot.send_message(message.chat.id, text=text)


@bot.message_handler(func=lambda message: get_state(message) == START, content_types=['location'])
def add_place(message):
    places = session.query(Places).filter_by(user=message.chat.id).all()
    if places:
        closest = find_closest_places(message.location, places)
        if closest:
            if len(closest) == 1:
                bot.send_message(message.chat.id, text='Найдено место в радиусе 500 метров!')
            else:
                bot.send_message(message.chat.id, text='Найдено несколько мест в радиусе 500 метров! Вот список:')
            for place_num in closest:
                place = places[place_num]
                bot.send_message(message.chat.id, text=f'{place_num+1}. {place.address}')
                bot.send_location(message.chat.id, place.latitude, place.longitude)
                if place.image:
                    bot.send_photo(message.chat.id, place.image)
        else:
            bot.send_message(message.chat.id, text='Cохраненных мест в радиусе 500 метров не найдено.')
    else:
        bot.send_message(message.chat.id, text="Список сохраненных мест пуст.")


@bot.message_handler(func=lambda message: get_state(message) == START, commands=['add'])
def add_place(message):
    keyboard = create_keyboard(['Отмена'])
    bot.send_message(message.chat.id, text='Введи название места, которое нужно запомнить.',\
                    reply_markup=keyboard)
    update_state(message, ADDRESS)


@bot.message_handler(func=lambda message: get_state(message) == ADDRESS, content_types=['text'])
def add_address(message):
    update_place(message, 'address', message.text)
    keyboard = create_keyboard(['Отмена'])
    bot.send_message(message.chat.id, text='Укажи место на карте.', reply_markup=keyboard)
    update_state(message, LOCATION)


@bot.message_handler(func=lambda message: get_state(message) == ADDRESS, content_types=['audio', \
                 'document', 'photo', 'sticker', 'video', 'location', 'contact', 'new_chat_participant', \
                'left_chat_participant', 'new_chat_title', 'new_chat_photo', 'delete_chat_photo', \
                'group_chat_created'])
def add_address_error(message):
    bot.send_message(message.chat.id, text='Нужно ввести название места.')


@bot.message_handler(func=lambda message: get_state(message) == LOCATION, content_types=['location'])
def add_location(message):
    update_place(message, 'latitude', message.location.latitude)
    update_place(message, 'longitude', message.location.longitude)
    keyboard = create_keyboard(['Пропустить', 'Отмена'])
    bot.send_message(message.chat.id, text='Можешь скинуть фото места, но это не обязательно.',\
                     reply_markup=keyboard)
    update_state(message, IMAGE)


@bot.message_handler(func=lambda message: get_state(message) == LOCATION, content_types=['text', 'audio', \
                 'document', 'photo', 'sticker', 'video', 'contact', 'new_chat_participant', \
                'left_chat_participant', 'new_chat_title', 'new_chat_photo', 'delete_chat_photo', \
                'group_chat_created'])
def add_location_error(message):
    bot.send_message(message.chat.id, text='Это не место на карте.')


@bot.message_handler(func=lambda message: get_state(message) == IMAGE, content_types=['photo'])
def add_image(message):
    update_place(message, 'image', message.json['photo'][0].get('file_id'))
    update_state(message, CONFIRMATION)
    confirmation(message)


@bot.message_handler(func=lambda message: get_state(message) == IMAGE, content_types=['text', 'audio', \
                 'document', 'sticker', 'video', 'location', 'contact', 'new_chat_participant', \
                'left_chat_participant', 'new_chat_title', 'new_chat_photo', 'delete_chat_photo', \
                'group_chat_created'])
def add_image_error(message):
    bot.send_message(message.chat.id, text='Это не фото.')


@bot.message_handler(func=lambda message: get_state(message) == CONFIRMATION)
def confirmation(message):
    keyboard = create_keyboard(['Да', 'Отмена'])
    text = get_place(message).get('address')
    bot.send_message(message.chat.id, text=f'Запомнить место "{text}"?', reply_markup=keyboard)


@bot.message_handler(commands=['reset'])
def remove_places(message):
    places = session.query(Places).filter_by(user=message.chat.id).all()
    if places:
        for place in places:
            session.delete(place)
        session.commit()
        bot.send_message(message.chat.id, text="Все сохраненные места удалены.")
    else:
        bot.send_message(message.chat.id, text="Список сохраненных мест пуст.")


@bot.message_handler(commands=['list'])
def list_places(message):
    places = session.query(Places).filter_by(user=message.chat.id).all()
    if places:
        enumerated_addresses = [f'{num}. {place.address}' for num, place in enumerate(places, 1)]
        text = 'Вот список сохраненных мест:\n' + ';\n'.join(enumerated_addresses) + '.'
        bot.send_message(message.chat.id, text=text+'\n Чтобы узнать больше о месте: /x, где x - номер места.')
    else:
        bot.send_message(message.chat.id, text="Список сохраненных мест пуст.")


@bot.message_handler(commands=list(map(str, range(1, 11))))
def show_place(message):
    places = session.query(Places).filter_by(user=message.chat.id).all()
    if places:
        num = int(message.json['text'][1:])
        if len(places) >= num:
            place = places[num-1]
            bot.send_message(message.chat.id, text=f'{num}. {place.address}')
            bot.send_location(message.chat.id, place.latitude, place.longitude)
            if place.image:
                bot.send_photo(message.chat.id, place.image)


if __name__ == '__main__':
    bot.polling()


