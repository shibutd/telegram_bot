import os
import requests


# Settings for access to the service Google Maps Distance Matrix API
URL = 'https://maps.googleapis.com/maps/api/distancematrix/json'
API_KEY = os.getenv('DISTANCEMATRIX_API_KEY', 'secret-api')


def find_closest_places(location, places):
    '''Finds out if there are any saved places that are closer
    than 500 meters to the given location.
    Using Google Maps Distance Matrix API to find distances.

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
        response = requests.get(URL, params=parameters, timeout=5)
        response.raise_for_status()
    except (requests.exceptions.Timeout, requests.HTTPError):
        return []

    try:
        distances = response.json()['rows'][0]['elements']
    except (KeyError, IndexError):
        return []

    # Determine saved places that are closer than 500 meters to location
    # given by user and return its indicies
    closer = []
    for idx, distance in enumerate(distances):
        if distance.get('status') == 'OK' and distance['distance']['value'] < 500:
            closer.append(idx)
    return closer
