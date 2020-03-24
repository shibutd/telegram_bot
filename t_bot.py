import os
import time
import requests
import telebot
from collections import defaultdict
from models import session, Place

# Activate proxy to get access to telegram if it is blocked, requires
# running Tor Browser, typically Tor listens for SOCKS connections on port 9150
# telebot.apihelper.proxy = {'https': 'socks5://127.0.0.1:9150'}

# Creates a bot and gives it unique token
token = os.getenv('TELEGRAM_TOKEN', 'secret-token')
bot = telebot.TeleBot(token)

# Settings for access to the service Google Maps Distance Matrix API
url = 'https://maps.googleapis.com/maps/api/distancematrix/json'
API_KEY = os.getenv('DISTANCEMATRIX_API_KEY', 'secret-api')

message_data_types = ['text', 'audio', 'document', 'photo', 'sticker',
                      'video', 'location', 'contact', 'new_chat_participant',
                      'left_chat_participant', 'new_chat_title', 'new_chat_photo',
                      'delete_chat_photo', 'group_chat_created']

# Variables for state implementation while adding new data about place
START, ADDRESS, LOCATION, IMAGE, CONFIRMATION = range(5)
USER_STATE = defaultdict(lambda: START)

# Dictionary for storing data while survey before saving to database
PLACES = defaultdict(lambda: {})


def get_state(message):
    '''Returns current user's state'''
    return USER_STATE[message.chat.id]


def update_state(message, state):
    '''Updates current user's state'''
    USER_STATE[message.chat.id] = state


def get_place(message):
    '''Returns current user's place'''
    return PLACES[message.chat.id]


def update_place(message, key, value):
    '''Updates one of current user's place characteristic'''
    PLACES[message.chat.id][key] = value


def reset_place(message):
    '''Resets current user's place characteristic if he canceled
    adding new place
    '''
    PLACES[message.chat.id] = {}


def create_keyboard(buttons_list=[]):
    keyboard = telebot.types.InlineKeyboardMarkup(
        row_width=len(buttons_list))
    buttons = [telebot.types.InlineKeyboardButton(
        text=button,
        callback_data=button) for button in buttons_list]
    keyboard.add(*buttons)
    return keyboard


@bot.callback_query_handler(func=lambda x: True)
def callback_handler(callback_query):
    '''Handles user keystrokes'''
    message = callback_query.message
    text = callback_query.data

    # User presses "Cancel" button
    if text == 'Отмена':
        # Remove the buttons
        bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=None
        )
        bot.send_message(message.chat.id, text='Добавление нового места отменено.')
        reset_place(message)
        update_state(message, START)

    # User presses "Skip" button to skip adding image
    elif text == 'Пропустить':
        bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=None
        )
        bot.send_message(message.chat.id, text='Хорошо, давай без фото.')
        update_state(message, CONFIRMATION)
        time.sleep(1)
        confirmation(message)

    # User presses "Confirm" button to save new place into database
    elif text == 'Да':
        bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=None
        )
        # Check if user already have 10 saved places.
        # If he has delete one place, the first one that he saved
        places = session.query(Place).filter_by(
            user=message.chat.id).order_by(Place.id).all()
        if len(places) == 10:
            session.delete(places[0])
        # Save place from "PLACE ditionary" to database
        place_dict = get_place(message)
        place = Place(
            user=message.chat.id,
            address=place_dict.get('address'),
            latitude=place_dict.get('latitude'),
            longitude=place_dict.get('longitude'),
            image=place_dict.get('image')
        )
        session.add(place)
        session.commit()

        bot.send_message(message.chat.id, text="Новое место добалено!")
        reset_place(message)
        update_state(message, START)


@bot.message_handler(commands=['start', 'help'])
def command_help(message):
    '''Create initial and help messages'''
    text = '''Привет! Я создан для того, чтобы запоминать места, \
которые ты возможно захочешь посетить позже. Доступные команды:
/add – запомнить место;
/list – показать сохраненные места (только последние 10);
/reset – удалить все сохраненные места.
            '''
    bot.send_message(message.chat.id, text=text)


def find_closest_places(location, places):
    '''Using Google Maps Distance Matrix API to find distances
    between given location and user's saved in database places_numbers
    that are near than 500 meters of location.

    Arguments:
        location {JSON} -- location given by user
        places {SQLAlchemy objects} -- user's places from database

    Returns:
        Number of indicies of places that are closer than 500 meters to
        location given by user.
    '''
    # Format location given by user
    origins = [f'{location.latitude},{location.longitude}']
    origins = '|'.join(origins)
    # Format user's saved locations from database
    destinations = [f'{place.latitude},{place.longitude}' for place in places]
    destinations = '|'.join(destinations)
    # Making reqest to Distance Matrix API, requests to:
    # http://maps.googleapis.com/maps/api/distancematrix/outputFormat?parameters
    # parameters: origins = 41.43206,-81.38992, destinations = 41.43206,-81.38992
    parameters = {'origins': origins, 'destinations': destinations, 'key': API_KEY}
    try:
        response = requests.get(url, params=parameters, timeout=5)
        response.raise_for_status()
    except (requests.exceptions.Timeout, requests.HTTPError):
        return []
    distances = response.json()['rows'][0]['elements']

    # Determine saved places that are closer than 500 meters to location
    # given by user and return its indicies
    closer = []
    for idx, distance in enumerate(distances):
        if distance.get('status') == 'OK' and distance['distance']['value'] < 500:
            closer.append(idx)
    return closer


def print_places(chat_id, saved_places, places_numbers):
    '''Displays message with data (name, locationn, image) about user's places.

    Arguments:
        chat_id {int} -- chat's id
        saved_places {SQLAlchemy objects} -- user's places from database
        places_numbers {List[int]} -- number of indicies
    '''
    for place_number in places_numbers:
        place = saved_places[place_number]
        bot.send_message(chat_id, text=f'{place_number+1}. {place.address}')
        bot.send_location(chat_id, place.latitude, place.longitude)
        if place.image:
            bot.send_photo(chat_id, place.image)


@bot.message_handler(func=lambda message: get_state(message) == START,
                     content_types=['location'])
def check_closest_places(message):
    '''Handles user's message with given location and prints data (name,
    locationn, image) of user's saved locations if it is closer than 500 meters.
    '''
    saved_places = session.query(Place).filter_by(user=message.chat.id).all()
    if not saved_places:
        bot.send_message(message.chat.id, text='Список сохраненных мест пуст.')
    else:
        closest_places = find_closest_places(message.location, saved_places)
        if not closest_places:
            message_text = 'Cохраненных мест в радиусе 500 метров не найдено.'
        elif len(closest_places) == 1:
            message_text = 'Найдено место в радиусе 500 метров!'
        else:
            message_text = 'Найдено несколько мест в радиусе 500 метров! Вот список:'
        bot.send_message(message.chat.id, text=message_text)
        print_places(message.chat.id, saved_places, closest_places)


@bot.message_handler(func=lambda message: get_state(message) == START, commands=['add'])
def add_place(message):
    '''Handles "add" command, start survey user to add new place
    to database, changes state to ADDRESS
    '''
    keyboard = create_keyboard(['Отмена'])
    bot.send_message(
        message.chat.id,
        text='Введи название места, которое нужно запомнить.',
        reply_markup=keyboard
    )
    update_state(message, ADDRESS)


@bot.message_handler(func=lambda message: get_state(message) == ADDRESS,
                     content_types=['text'])
def add_address(message):
    '''Get address name from user, changes state to LOCATION'''
    update_place(message, 'address', message.text)
    keyboard = create_keyboard(['Отмена'])
    bot.send_message(message.chat.id, text='Укажи место на карте.', reply_markup=keyboard)
    update_state(message, LOCATION)


@bot.message_handler(func=lambda message: get_state(message) == ADDRESS,
                     content_types=[type for type in message_data_types
                                    if type != 'text'])
def add_address_error(message):
    '''Displays error message if user's input is not "Adress name"'''
    bot.send_message(message.chat.id, text='Нужно ввести название места.')


@bot.message_handler(func=lambda message: get_state(message) == LOCATION,
                     content_types=['location'])
def add_location(message):
    '''Get location from user, changes state to IMAGE'''
    update_place(message, 'latitude', message.location.latitude)
    update_place(message, 'longitude', message.location.longitude)
    keyboard = create_keyboard(['Пропустить', 'Отмена'])
    bot.send_message(
        message.chat.id,
        text='Можешь скинуть фото места, но это необязательно.',
        reply_markup=keyboard
    )
    update_state(message, IMAGE)


@bot.message_handler(func=lambda message: get_state(message) == LOCATION,
                     content_types=[type for type in message_data_types
                                    if type != 'location'])
def add_location_error(message):
    '''Displays error message if user's input is not "Location"'''
    bot.send_message(message.chat.id, text='Это не место на карте.')


@bot.message_handler(func=lambda message: get_state(message) == IMAGE,
                     content_types=['photo'])
def add_image(message):
    '''Get iamge from user, changes state to CONFIRMATION'''
    update_place(message, 'image', message.json['photo'][0].get('file_id'))
    update_state(message, CONFIRMATION)
    confirmation(message)


@bot.message_handler(func=lambda message: get_state(message) == IMAGE,
                     content_types=[type for type in message_data_types
                                    if type != 'photo'])
def add_image_error(message):
    '''Displays error message if user's input is not "Image"'''
    bot.send_message(message.chat.id, text='Это не фото.')


@bot.message_handler(func=lambda message: get_state(message) == CONFIRMATION)
def confirmation(message):
    '''Asks user if he is confident about adding place to database'''
    keyboard = create_keyboard(['Да', 'Отмена'])
    text = get_place(message).get('address')
    bot.send_message(
        message.chat.id,
        text=f'Запомнить место "{text}"?',
        reply_markup=keyboard
    )


@bot.message_handler(commands=['reset'])
def remove_places(message):
    '''Handles "reset" command, delete all user's places from database
    or displays message if there is no places
    '''
    places = session.query(Place).filter_by(user=message.chat.id).all()
    if places:
        for place in places:
            session.delete(place)
        session.commit()
        bot.send_message(message.chat.id, text="Все сохраненные места удалены.")
    else:
        bot.send_message(message.chat.id, text="Список сохраненных мест пуст.")


@bot.message_handler(commands=['list'])
def list_places(message):
    '''Handles "list" command, displays all user's places from database
    or message if there is no places
    '''
    places = session.query(Place).filter_by(user=message.chat.id).all()
    if places:
        enumerated_addresses = [f'{num}. {place.address}'
                                for num, place in enumerate(places, 1)]
        text = 'Вот список сохраненных мест:\n' + ';\n'.join(enumerated_addresses) + '.'
        bot.send_message(
            message.chat.id,
            text=text + '\nЧтобы узнать больше о месте: /x, где x - номер места.'
        )
    else:
        bot.send_message(message.chat.id, text="Список сохраненных мест пуст.")


@bot.message_handler(commands=list(map(str, range(1, 11))))
def show_place(message):
    '''Handles "1", "2", "3", ... "10" commands to show data (name, location, image)
    about particular user's place from database
    '''
    saved_places = session.query(Place).filter_by(user=message.chat.id).all()
    place_idx = int(message.json['text'][1:])
    if len(saved_places) >= place_idx:
        print_places(message.chat.id, saved_places, [place_idx - 1])


if __name__ == '__main__':
    bot.polling()
